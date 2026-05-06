import json
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from airflan.core import SequentialExecutor, TaskResult, TaskStatus, WorkflowContext
from airflan.orchestrator import WorkflowOrchestrator
from airflan.storage.backend import DagRun, DatabaseSession, TaskInstance, XCom
from airflan.workflow_loader import load_workflows


class WorkerDaemon:
    """Claims queued task instances from the metadata DB and executes them."""

    def __init__(
        self,
        workflows_dir: str = "workflows",
        poll_interval: int = 5,
        db_url: Optional[str] = None,
        worker_id: Optional[str] = None,
        heartbeat_interval: int = 5,
        heartbeat_timeout: int = 60,
    ):
        self.workflows_dir = Path(workflows_dir)
        self.poll_interval = poll_interval
        self.worker_id = worker_id or f"worker_{uuid.uuid4().hex[:12]}"
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_timeout = heartbeat_timeout
        self.known_workflows: Dict[str, WorkflowOrchestrator] = {}
        self.db = DatabaseSession(db_url)
        self.db.init_db()

    def _parse_workflows(self) -> None:
        self.known_workflows = load_workflows(self.workflows_dir)

    def _initialize_next_queued_run(self) -> bool:
        session = self.db.get_session()
        try:
            queued_run = session.query(DagRun).filter(
                DagRun.status == "queued"
            ).order_by(DagRun.start_time.asc())
            queued_run = self._with_claim_lock(queued_run).first()

            if not queued_run:
                return False

            orchestrator = self.known_workflows.get(queued_run.dag_id)
            if not orchestrator:
                queued_run.status = "failed"
                queued_run.end_time = datetime.utcnow()
                session.commit()
                logger.error(f"Queued workflow {queued_run.dag_id} was not found by this worker")
                return True

            updated = session.query(DagRun).filter(
                DagRun.id == queued_run.id,
                DagRun.status == "queued",
            ).update(
                {
                    "status": "running",
                    "start_time": datetime.utcnow(),
                    "end_time": None,
                },
                synchronize_session=False,
            )

            if updated != 1:
                session.rollback()
                return False

            for task_name in orchestrator.tasks:
                exists = session.query(TaskInstance).filter_by(
                    run_id=queued_run.run_id,
                    task_id=task_name,
                ).first()
                if exists:
                    continue

                session.add(
                    TaskInstance(
                        task_id=task_name,
                        dag_id=queued_run.dag_id,
                        run_id=queued_run.run_id,
                        status="pending",
                    )
                )

            run_id = queued_run.run_id
            dag_id = queued_run.dag_id
            session.commit()
            logger.info(f"Initialized workflow run: {dag_id} ({run_id})")
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _claim_next_ready_task(self) -> Optional[Tuple[str, str, str]]:
        session = self.db.get_session()
        try:
            runs = session.query(DagRun).filter(
                DagRun.status == "running"
            ).order_by(DagRun.start_time.asc())
            runs = self._with_claim_lock(runs).all()

            for dag_run in runs:
                orchestrator = self.known_workflows.get(dag_run.dag_id)
                if not orchestrator:
                    dag_run.status = "failed"
                    dag_run.end_time = datetime.utcnow()
                    session.commit()
                    logger.error(f"Running workflow {dag_run.dag_id} was not found by this worker")
                    return None

                task_instances = {
                    ti.task_id: ti
                    for ti in session.query(TaskInstance).filter_by(run_id=dag_run.run_id).all()
                }

                for task_name in self._ready_task_names(orchestrator, task_instances):
                    updated = session.query(TaskInstance).filter(
                        TaskInstance.run_id == dag_run.run_id,
                        TaskInstance.task_id == task_name,
                        TaskInstance.status == "pending",
                    ).update(
                        {
                            "status": "running",
                            "start_time": datetime.utcnow(),
                            "end_time": None,
                            "worker_id": self.worker_id,
                            "heartbeat_at": datetime.utcnow(),
                        },
                        synchronize_session=False,
                    )

                    if updated != 1:
                        session.rollback()
                        return None

                    session.commit()
                    logger.info(f"Claimed task: {dag_run.dag_id}.{task_name} ({dag_run.run_id})")
                    return dag_run.run_id, dag_run.dag_id, task_name

            return None
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _recover_stale_tasks(self) -> bool:
        cutoff = datetime.utcnow() - timedelta(seconds=self.heartbeat_timeout)
        session = self.db.get_session()
        try:
            stale_tasks = session.query(TaskInstance).filter(
                TaskInstance.status == "running",
                TaskInstance.start_time < cutoff,
            ).filter(
                (TaskInstance.heartbeat_at == None) | (TaskInstance.heartbeat_at < cutoff)
            ).all()

            for task_instance in stale_tasks:
                logger.warning(
                    f"Recovering stale task: {task_instance.dag_id}."
                    f"{task_instance.task_id} ({task_instance.run_id})"
                )
                task_instance.status = "pending"
                task_instance.worker_id = None
                task_instance.heartbeat_at = None
                task_instance.end_time = None

            if stale_tasks:
                session.commit()
                return True
            return False
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _ready_task_names(
        self,
        orchestrator: WorkflowOrchestrator,
        task_instances: Dict[str, TaskInstance],
    ) -> List[str]:
        ready = []
        for task_name, task in orchestrator.tasks.items():
            task_instance = task_instances.get(task_name)
            if not task_instance or task_instance.status != "pending":
                continue

            dependency_statuses = {
                dep: task_instances[dep].status
                for dep in task.depends_on
                if dep in task_instances
            }

            if len(dependency_statuses) != len(task.depends_on):
                continue

            blocked = any(
                status in {"failed", "timeout", "upstream_failed", "cancelled"}
                and not orchestrator.tasks[dep].skip_on_failure
                for dep, status in dependency_statuses.items()
            )
            if blocked:
                continue

            if all(status in {"completed", "skipped"} for status in dependency_statuses.values()):
                ready.append(task_name)

        return ready

    def _mark_upstream_failed_tasks(self) -> bool:
        changed = False
        session = self.db.get_session()
        try:
            runs = session.query(DagRun).filter(DagRun.status == "running").all()
            for dag_run in runs:
                orchestrator = self.known_workflows.get(dag_run.dag_id)
                if not orchestrator:
                    continue

                task_instances = {
                    ti.task_id: ti
                    for ti in session.query(TaskInstance).filter_by(run_id=dag_run.run_id).all()
                }

                for task_name, task in orchestrator.tasks.items():
                    task_instance = task_instances.get(task_name)
                    if not task_instance or task_instance.status != "pending":
                        continue

                    blocked = any(
                        dep in task_instances
                        and task_instances[dep].status in {
                            "failed",
                            "timeout",
                            "upstream_failed",
                            "cancelled",
                        }
                        and not orchestrator.tasks[dep].skip_on_failure
                        for dep in task.depends_on
                    )

                    if blocked:
                        task_instance.status = "upstream_failed"
                        task_instance.end_time = datetime.utcnow()
                        changed = True

            if changed:
                session.commit()
            return changed
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _execute_claimed_task(self, run_id: str, dag_id: str, task_name: str) -> None:
        orchestrator = self.known_workflows[dag_id]
        task = orchestrator.tasks[task_name]
        context = self._build_context(run_id, orchestrator)
        stop_heartbeat = threading.Event()
        heartbeat_thread = threading.Thread(
            target=self._heartbeat_task,
            args=(run_id, task_name, stop_heartbeat),
            daemon=True,
        )
        heartbeat_thread.start()

        try:
            if not orchestrator._check_condition(task):
                result = TaskResult(
                    status=TaskStatus.SKIPPED,
                    start_time=datetime.utcnow().isoformat(),
                    end_time=datetime.utcnow().isoformat(),
                    attempt_count=0,
                )
            else:
                executor = SequentialExecutor(
                    cache_enabled=orchestrator.cache.enabled,
                    cache_manager=orchestrator.cache,
                )
                result = executor._execute_task(task, context)
                context.set(f"result_{task.name}", result.output)
        finally:
            stop_heartbeat.set()
            heartbeat_thread.join(timeout=1)

        self._persist_task_result(run_id, dag_id, task_name, result)

    def _heartbeat_task(self, run_id: str, task_name: str, stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            self._write_task_heartbeat(run_id, task_name)
            stop_event.wait(self.heartbeat_interval)

    def _write_task_heartbeat(self, run_id: str, task_name: str) -> None:
        session = self.db.get_session()
        try:
            session.query(TaskInstance).filter(
                TaskInstance.run_id == run_id,
                TaskInstance.task_id == task_name,
                TaskInstance.status == "running",
                TaskInstance.worker_id == self.worker_id,
            ).update(
                {"heartbeat_at": datetime.utcnow()},
                synchronize_session=False,
            )
            session.commit()
        except Exception:
            session.rollback()
            logger.warning(f"Failed to heartbeat task {run_id}.{task_name}")
        finally:
            session.close()

    def _build_context(self, run_id: str, orchestrator: WorkflowOrchestrator) -> WorkflowContext:
        context = WorkflowContext(experiment_tracker=orchestrator.experiment_tracker)
        session = self.db.get_session()
        try:
            outputs = session.query(XCom).filter_by(run_id=run_id, key="return_value").all()
            for output in outputs:
                context.set(f"result_{output.task_id}", self._decode_xcom_value(output.value))
            return context
        finally:
            session.close()

    def _persist_task_result(
        self,
        run_id: str,
        dag_id: str,
        task_name: str,
        result: TaskResult,
    ) -> None:
        session = self.db.get_session()
        try:
            task_instance = session.query(TaskInstance).filter_by(
                run_id=run_id,
                task_id=task_name,
            ).first()
            if not task_instance:
                raise ValueError(f"TaskInstance not found: {run_id}.{task_name}")

            task_instance.status = result.status.value
            task_instance.execution_time = result.execution_time
            task_instance.attempt_count = result.attempt_count
            task_instance.error_trace = result.error_trace
            task_instance.worker_id = None
            task_instance.heartbeat_at = None
            if result.start_time:
                task_instance.start_time = datetime.fromisoformat(result.start_time)
            if result.end_time:
                task_instance.end_time = datetime.fromisoformat(result.end_time)

            if result.output is not None:
                self._upsert_xcom(session, run_id, dag_id, task_name, result.output)

            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _upsert_xcom(self, session, run_id: str, dag_id: str, task_name: str, output: Any) -> None:
        xcom = session.query(XCom).filter_by(
            run_id=run_id,
            task_id=task_name,
            key="return_value",
        ).first()

        if not xcom:
            xcom = XCom(
                task_id=task_name,
                dag_id=dag_id,
                run_id=run_id,
                key="return_value",
            )
            session.add(xcom)

        xcom.value = json.dumps(output, default=str)
        xcom.timestamp = datetime.utcnow()

    def _finalize_finished_runs(self) -> bool:
        changed = False
        terminal_statuses = {
            "completed",
            "failed",
            "skipped",
            "timeout",
            "upstream_failed",
            "cancelled",
        }
        failure_statuses = {"failed", "timeout", "upstream_failed", "cancelled"}

        session = self.db.get_session()
        try:
            runs = session.query(DagRun).filter(DagRun.status == "running").all()
            for dag_run in runs:
                task_instances = session.query(TaskInstance).filter_by(run_id=dag_run.run_id).all()
                if not task_instances:
                    continue

                statuses = {task_instance.status for task_instance in task_instances}
                if statuses and statuses.issubset(terminal_statuses):
                    dag_run.status = "failed" if statuses & failure_statuses else "completed"
                    dag_run.end_time = datetime.utcnow()
                    changed = True

            if changed:
                session.commit()
            return changed
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _decode_xcom_value(value: str) -> Any:
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return value

    def _with_claim_lock(self, query):
        if self._supports_skip_locked():
            return query.with_for_update(skip_locked=True)
        return query

    def _supports_skip_locked(self) -> bool:
        return self.db.engine.dialect.name in {"postgresql", "oracle"}

    def run_once(self) -> bool:
        self._parse_workflows()

        if self._recover_stale_tasks():
            return True

        if self._initialize_next_queued_run():
            return True

        if self._mark_upstream_failed_tasks():
            self._finalize_finished_runs()
            return True

        claimed = self._claim_next_ready_task()
        if claimed:
            run_id, dag_id, task_name = claimed
            self._execute_claimed_task(run_id, dag_id, task_name)
            self._mark_upstream_failed_tasks()
            self._finalize_finished_runs()
            return True

        return self._finalize_finished_runs()

    def run(self) -> None:
        import time

        logger.info("Worker Daemon starting...")
        logger.info("Press Ctrl+C to exit")

        try:
            while True:
                did_work = self.run_once()
                if not did_work:
                    time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            logger.info("Worker shutting down.")

import json
import threading
from datetime import datetime
from typing import Dict, Optional

from loguru import logger
from sqlalchemy import exc

from ..core.task import Task, TaskResult
from .backend import DatabaseSession, DagRun, TaskInstance, XCom

class StateManager:
    """
    Manages workflow state persistence
    
    Writes workflow state to SQLAlchemy Database for historical tracking
    and UI consumption.
    """
    
    def __init__(self, db_url: Optional[str] = None):
        """
        Initialize state manager with database connection
        
        Args:
            db_url: Optional database connection string (defaults to local SQLite)
        """
        self.db = DatabaseSession(db_url)
        self.db.init_db()
        self.run_id = None
        self._lock = threading.Lock()
        
    def start_run(self, workflow_name: str, run_id: str) -> None:
        """Initialize a new DAG run in the database"""
        self.run_id = run_id
        session = self.db.get_session()
        try:
            existing_run = session.query(DagRun).filter_by(run_id=run_id).first()
            if existing_run:
                existing_run.status = "running"
                existing_run.start_time = datetime.utcnow()
                existing_run.end_time = None
                session.commit()
                logger.debug(f"Started existing DagRun: {run_id}")
                return

            # Create a new DagRun entry
            dag_run = DagRun(
                dag_id=workflow_name,
                run_id=run_id,
                status="running",
                start_time=datetime.utcnow()
            )
            session.add(dag_run)
            session.commit()
            logger.debug(f"Started DagRun: {run_id}")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to start DagRun: {e}")
        finally:
            session.close()

    def update_state(
        self,
        workflow_name: str,
        tasks: Dict[str, Task],
        results: Dict[str, TaskResult]
    ) -> None:
        """
        Update workflow state in the database
        
        Args:
            workflow_name: Name of the workflow
            tasks: Dictionary of tasks
            results: Dictionary of task results
        """
        if not self.run_id:
            logger.warning("Attempted to update state before start_run()")
            return
            
        with self._lock:
            session = self.db.get_session()
            try:
                # Check if workflow is finished
                terminal_statuses = {
                    'completed',
                    'failed',
                    'skipped',
                    'timeout',
                    'upstream_failed',
                    'cancelled',
                }
                is_finished = (
                    len(results) == len(tasks)
                    and all(r.status.value in terminal_statuses for r in results.values())
                )
                has_failures = any(
                    r.status.value in {'failed', 'timeout', 'upstream_failed', 'cancelled'}
                    for r in results.values()
                )
                
                # Update DagRun terminal status
                if is_finished:
                    dag_run = session.query(DagRun).filter_by(run_id=self.run_id).first()
                    if dag_run:
                        dag_run.status = "failed" if has_failures else "completed"
                        dag_run.end_time = datetime.utcnow()
                
                # Upsert TaskInstance statuses
                for name, task in tasks.items():
                    ti = session.query(TaskInstance).filter_by(
                        run_id=self.run_id, task_id=name
                    ).order_by(TaskInstance.id.desc()).first()
                    
                    if not ti:
                        ti = TaskInstance(
                            task_id=name,
                            dag_id=workflow_name,
                            run_id=self.run_id
                        )
                        session.add(ti)
                    
                    if name in results:
                        result = results[name]
                        ti.status = result.status.value
                        ti.execution_time = result.execution_time
                        ti.attempt_count = result.attempt_count

                        if result.start_time:
                            ti.start_time = self._parse_timestamp(result.start_time)
                        
                        if result.error_trace:
                            ti.error_trace = result.error_trace
                            
                        if result.status.value in terminal_statuses and result.end_time:
                            ti.end_time = self._parse_timestamp(result.end_time)
                        elif result.status.value in terminal_statuses and not ti.end_time:
                            ti.end_time = datetime.utcnow()

                        self._upsert_task_output(
                            session=session,
                            workflow_name=workflow_name,
                            task_name=name,
                            result=result
                        )
                            
                session.commit()
                
                # Write fallback JSON state for UI to parse 'depends_on' edges
                try:
                    state_dict = {
                        "name": workflow_name,
                        "status": "completed" if is_finished and not has_failures else "failed" if is_finished else "running",
                        "tasks": {
                            name: {"depends_on": task.depends_on}
                            for name, task in tasks.items()
                        }
                    }
                    with open(f"{workflow_name}_structure.json", "w") as f:
                        json.dump(state_dict, f)
                except Exception as json_e:
                    logger.warning(f"Failed to write UI json state fallback: {json_e}")
                
            except exc.OperationalError as oe:
                session.rollback()
                logger.warning(f"DB lock delay - retrying update state next loop.")
            except Exception as e:
                session.rollback()
                import traceback
                logger.error(f"Failed to update state in DB: {e}\n{traceback.format_exc()}")
            finally:
                session.close()

    def _upsert_task_output(
        self,
        session,
        workflow_name: str,
        task_name: str,
        result: TaskResult
    ) -> None:
        """Persist task outputs as XCom-style records for later inspection."""
        if result.output is None or not self.run_id:
            return

        payload = json.dumps(result.output, default=str)
        xcom = session.query(XCom).filter_by(
            run_id=self.run_id,
            task_id=task_name,
            key="return_value"
        ).first()

        if not xcom:
            xcom = XCom(
                task_id=task_name,
                dag_id=workflow_name,
                run_id=self.run_id,
                key="return_value"
            )
            session.add(xcom)

        xcom.value = payload
        xcom.timestamp = datetime.utcnow()

    @staticmethod
    def _parse_timestamp(value: str) -> datetime:
        """Parse ISO timestamps emitted by TaskResult."""
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return datetime.utcnow()
            
    def load_state(self) -> Optional[Dict]:
        """
        [DEPRECATED] Loads state for UI compatibility layer.
        In the future, the UI will query the DB directly.
        """
        session = self.db.get_session()
        try:
            runs = session.query(DagRun).order_by(DagRun.start_time.desc()).limit(1).all()
            if not runs:
                return None
                
            latest_run = runs[0]
            tasks = session.query(TaskInstance).filter_by(run_id=latest_run.run_id).all()
            
            return {
                "name": latest_run.dag_id,
                "timestamp": latest_run.start_time.isoformat(),
                "status": latest_run.status,
                "results": {
                    t.task_id: {
                        "status": t.status,
                        "execution_time": t.execution_time
                    } for t in tasks
                }
            }
        except Exception as e:
            logger.warning(f"Failed to load state from DB: {e}")
            return None
        finally:
            session.close()

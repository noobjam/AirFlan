import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner

from airflan import WorkflowOrchestrator
from airflan.cli import cli
from airflan.core.task import TaskStatus
from airflan.mlops.artifact_store import ArtifactStore
from airflan.scheduler_daemon import SchedulerDaemon
from airflan.storage.backend import TaskInstance
from airflan.worker import WorkerDaemon


def build_orchestrator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **kwargs) -> WorkflowOrchestrator:
    monkeypatch.chdir(tmp_path)
    orchestrator = WorkflowOrchestrator(**kwargs)
    orchestrator._print_banner = lambda: None
    return orchestrator


def test_database_url_can_come_from_environment(tmp_path, monkeypatch):
    db_path = tmp_path / "custom_metadata.db"
    monkeypatch.setenv("AIRFLAN_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.chdir(tmp_path)

    wf = WorkflowOrchestrator(name="env_db_url", enable_cache=False)
    wf._print_banner = lambda: None

    @wf.task(name="start")
    def start():
        return "ok"

    wf.run(parallel=False, enable_ui=False)

    assert db_path.exists()
    assert not (tmp_path / "airflan_metadata.db").exists()


def test_cli_initdb_accepts_explicit_db_url(tmp_path):
    db_path = tmp_path / "cli_metadata.db"
    runner = CliRunner()

    result = runner.invoke(cli, ["initdb", "--db-url", f"sqlite:///{db_path}"])

    assert result.exit_code == 0
    assert db_path.exists()


def test_parallel_execution_with_dependencies_retries_and_conditions(tmp_path, monkeypatch):
    wf = build_orchestrator(tmp_path, monkeypatch, name="integration_parallel", enable_cache=False)

    counters = {"left": 0, "right": 0, "flaky": 0}
    task_starts = {}
    timeline_lock = threading.Lock()

    @wf.task(name="left_extract", cache_result=False)
    def left_extract():
        with timeline_lock:
            task_starts["left_extract"] = time.perf_counter()
        counters["left"] += 1
        time.sleep(0.25)
        return {"left": 1}

    @wf.task(name="right_extract", cache_result=False)
    def right_extract():
        with timeline_lock:
            task_starts["right_extract"] = time.perf_counter()
        counters["right"] += 1
        time.sleep(0.25)
        return {"right": 2}

    @wf.task(name="flaky_transform", depends_on=["left_extract"], retry_count=1, retry_delay=0.01)
    def flaky_transform(context):
        counters["flaky"] += 1
        if counters["flaky"] == 1:
            raise ValueError("transient failure")
        payload = context.get("result_left_extract")
        return {"left_twice": payload["left"] * 2}

    @wf.task(name="conditional_skip", condition=lambda context: False)
    def conditional_skip():
        raise AssertionError("condition should have skipped execution")

    @wf.task(name="merge", depends_on=["right_extract", "flaky_transform"])
    def merge(context):
        return {
            "left": context.get("result_flaky_transform")["left_twice"],
            "right": context.get("result_right_extract")["right"],
        }

    started = time.perf_counter()
    results = wf.run(parallel=True, enable_ui=False)
    elapsed = time.perf_counter() - started

    assert elapsed < 0.7, elapsed
    assert abs(task_starts["left_extract"] - task_starts["right_extract"]) < 0.12
    assert counters == {"left": 1, "right": 1, "flaky": 2}
    assert results["left_extract"].status == TaskStatus.COMPLETED
    assert results["right_extract"].status == TaskStatus.COMPLETED
    assert results["flaky_transform"].status == TaskStatus.COMPLETED
    assert results["conditional_skip"].status == TaskStatus.SKIPPED
    assert results["merge"].output == {"left": 2, "right": 2}


def test_cache_and_state_persistence_across_runs(tmp_path, monkeypatch):
    wf = build_orchestrator(tmp_path, monkeypatch, name="integration_cache", enable_cache=True)
    calls = {"extract": 0}

    @wf.task(name="extract", cache_result=True)
    def extract():
        calls["extract"] += 1
        return {"rows": 3}

    @wf.task(name="transform", depends_on=["extract"])
    def transform(context):
        return context.get("result_extract")

    wf.run(parallel=False, enable_ui=False)
    wf.run(parallel=False, enable_ui=False)

    assert calls["extract"] == 1

    conn = sqlite3.connect(tmp_path / "airflan_metadata.db")
    cur = conn.cursor()
    cur.execute(
        "select count(*) from xcom where dag_id = ? and key = ?",
        ("integration_cache", "return_value"),
    )
    xcom_count = cur.fetchone()[0]
    cur.execute(
        "select count(*) from task_instances where dag_id = ? and start_time is not null and end_time is not null",
        ("integration_cache",),
    )
    task_timestamps = cur.fetchone()[0]
    conn.close()

    assert xcom_count >= 2
    assert task_timestamps >= 2


def test_timeout_stops_downstream_execution(tmp_path, monkeypatch):
    wf = build_orchestrator(tmp_path, monkeypatch, name="integration_timeout", enable_cache=False)

    @wf.task(name="slow", timeout=0.05)
    def slow():
        time.sleep(0.2)
        return "late"

    @wf.task(name="downstream", depends_on=["slow"])
    def downstream(context):
        return "should-not-run"

    with pytest.raises(Exception, match="Critical task slow failed"):
        wf.run(parallel=False, enable_ui=False)

    assert wf.results["slow"].status == TaskStatus.TIMEOUT
    assert wf.results["downstream"].status == TaskStatus.UPSTREAM_FAILED

    conn = sqlite3.connect(tmp_path / "airflan_metadata.db")
    cur = conn.cursor()
    cur.execute(
        "select status from dag_runs where dag_id = ? order by id desc limit 1",
        ("integration_timeout",),
    )
    assert cur.fetchone()[0] == "failed"
    cur.execute(
        "select status from task_instances where dag_id = ? and task_id = ?",
        ("integration_timeout", "downstream"),
    )
    assert cur.fetchone()[0] == "upstream_failed"
    conn.close()


def test_run_results_are_isolated_between_attempts(tmp_path, monkeypatch):
    wf = build_orchestrator(tmp_path, monkeypatch, name="integration_rerun", enable_cache=False)
    calls = {"flaky": 0, "downstream": 0}

    @wf.task(name="flaky")
    def flaky():
        calls["flaky"] += 1
        if calls["flaky"] == 1:
            raise ValueError("first run fails")
        return "ok"

    @wf.task(name="downstream", depends_on=["flaky"])
    def downstream(context):
        calls["downstream"] += 1
        return context.get("result_flaky")

    with pytest.raises(Exception, match="Critical task flaky failed"):
        wf.run(parallel=False, enable_ui=False)

    assert wf.results["downstream"].status == TaskStatus.UPSTREAM_FAILED

    results = wf.run(parallel=False, enable_ui=False)

    assert results["flaky"].status == TaskStatus.COMPLETED
    assert results["downstream"].status == TaskStatus.COMPLETED
    assert results["downstream"].output == "ok"
    assert calls == {"flaky": 2, "downstream": 1}


def test_scheduler_enqueues_runs_without_executing_them(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    daemon = SchedulerDaemon(workflows_dir="workflows", parse_interval=1)
    orchestrator = WorkflowOrchestrator(name="scheduled_workflow", schedule="* * * * *")
    run_id = daemon._enqueue_workflow(orchestrator)

    conn = sqlite3.connect(tmp_path / "airflan_metadata.db")
    cur = conn.cursor()
    cur.execute(
        "select status from dag_runs where run_id = ?",
        (run_id,),
    )
    assert cur.fetchone()[0] == "queued"
    conn.close()

    assert daemon._should_run_workflow("scheduled_workflow", "* * * * *") is False


def test_worker_claims_and_executes_queued_workflow_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir()
    workflow_file = workflows_dir / "queued_workflow.py"
    workflow_file.write_text(
        """
from airflan import WorkflowOrchestrator

orchestrator = WorkflowOrchestrator(
    name="queued_workflow",
    schedule="* * * * *",
    enable_cache=False,
)
orchestrator._print_banner = lambda: None

@orchestrator.task(name="start")
def start():
    return "done"

@orchestrator.task(name="finish", depends_on=["start"])
def finish(context):
    return context.get("result_start") + "-finished"
"""
    )

    scheduler = SchedulerDaemon(workflows_dir=str(workflows_dir), parse_interval=1)
    scheduler._parse_workflows()
    run_id = scheduler._enqueue_workflow(scheduler.known_workflows["queued_workflow"])

    worker = WorkerDaemon(workflows_dir=str(workflows_dir), poll_interval=1)
    assert worker.run_once() is True

    conn = sqlite3.connect(tmp_path / "airflan_metadata.db")
    cur = conn.cursor()
    cur.execute(
        "select status from dag_runs where run_id = ?",
        (run_id,),
    )
    assert cur.fetchone()[0] == "running"
    cur.execute(
        "select task_id, status from task_instances where run_id = ? order by task_id",
        (run_id,),
    )
    assert cur.fetchall() == [("finish", "pending"), ("start", "pending")]
    conn.close()

    assert worker.run_once() is True

    conn = sqlite3.connect(tmp_path / "airflan_metadata.db")
    cur = conn.cursor()
    cur.execute(
        "select status from task_instances where run_id = ? and task_id = ?",
        (run_id, "start"),
    )
    assert cur.fetchone()[0] == "completed"
    cur.execute(
        "select worker_id, heartbeat_at from task_instances where run_id = ? and task_id = ?",
        (run_id, "start"),
    )
    assert cur.fetchone() == (None, None)
    cur.execute(
        "select status from task_instances where run_id = ? and task_id = ?",
        (run_id, "finish"),
    )
    assert cur.fetchone()[0] == "pending"
    cur.execute(
        "select status from dag_runs where run_id = ?",
        (run_id,),
    )
    assert cur.fetchone()[0] == "running"
    conn.close()

    assert worker.run_once() is True

    conn = sqlite3.connect(tmp_path / "airflan_metadata.db")
    cur = conn.cursor()
    cur.execute(
        "select status from dag_runs where run_id = ?",
        (run_id,),
    )
    assert cur.fetchone()[0] == "completed"
    cur.execute(
        "select status from task_instances where run_id = ? and task_id = ?",
        (run_id, "finish"),
    )
    assert cur.fetchone()[0] == "completed"
    cur.execute(
        "select value from xcom where run_id = ? and task_id = ? and key = ?",
        (run_id, "finish", "return_value"),
    )
    assert cur.fetchone()[0] == '"done-finished"'
    conn.close()


def test_worker_recovers_stale_claimed_task(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir()
    workflow_file = workflows_dir / "stale_workflow.py"
    workflow_file.write_text(
        """
from airflan import WorkflowOrchestrator

orchestrator = WorkflowOrchestrator(
    name="stale_workflow",
    schedule="* * * * *",
    enable_cache=False,
)
orchestrator._print_banner = lambda: None

@orchestrator.task(name="start")
def start():
    return "recovered"
"""
    )

    scheduler = SchedulerDaemon(workflows_dir=str(workflows_dir), parse_interval=1)
    scheduler._parse_workflows()
    run_id = scheduler._enqueue_workflow(scheduler.known_workflows["stale_workflow"])

    first_worker = WorkerDaemon(
        workflows_dir=str(workflows_dir),
        worker_id="worker-one",
        heartbeat_timeout=1,
    )
    first_worker._parse_workflows()
    assert first_worker._initialize_next_queued_run() is True
    assert first_worker._claim_next_ready_task() == (run_id, "stale_workflow", "start")

    stale_time = datetime.utcnow() - timedelta(seconds=120)
    session = first_worker.db.get_session()
    try:
        task_instance = session.query(TaskInstance).filter_by(
            run_id=run_id,
            task_id="start",
        ).first()
        task_instance.start_time = stale_time
        task_instance.heartbeat_at = stale_time
        session.commit()
    finally:
        session.close()

    second_worker = WorkerDaemon(
        workflows_dir=str(workflows_dir),
        worker_id="worker-two",
        heartbeat_timeout=1,
    )
    assert second_worker.run_once() is True

    conn = sqlite3.connect(tmp_path / "airflan_metadata.db")
    cur = conn.cursor()
    cur.execute(
        "select status, worker_id, heartbeat_at from task_instances where run_id = ? and task_id = ?",
        (run_id, "start"),
    )
    assert cur.fetchone() == ("pending", None, None)
    conn.close()

    assert second_worker.run_once() is True

    conn = sqlite3.connect(tmp_path / "airflan_metadata.db")
    cur = conn.cursor()
    cur.execute(
        "select status from task_instances where run_id = ? and task_id = ?",
        (run_id, "start"),
    )
    assert cur.fetchone()[0] == "completed"
    cur.execute(
        "select status from dag_runs where run_id = ?",
        (run_id,),
    )
    assert cur.fetchone()[0] == "completed"
    conn.close()


def test_artifact_store_uses_shared_object_storage(tmp_path):
    store = ArtifactStore(str(tmp_path / "artifacts"))

    source = tmp_path / "model.bin"
    source.write_bytes(b"same-model-contents")

    first_path, first_size = store.store_artifact(str(source), "model.bin", "run_a")
    second_path, second_size = store.store_artifact(str(source), "model.bin", "run_b")

    objects = list((tmp_path / "artifacts" / "objects").iterdir())

    assert first_size == second_size == len(b"same-model-contents")
    assert Path(first_path).exists()
    assert Path(second_path).exists()
    assert len(objects) == 1

import sqlite3
import threading
import time
from pathlib import Path

import pytest

from airflan import WorkflowOrchestrator
from airflan.core.task import TaskStatus
from airflan.mlops.artifact_store import ArtifactStore
from airflan.scheduler_daemon import SchedulerDaemon


def build_orchestrator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **kwargs) -> WorkflowOrchestrator:
    monkeypatch.chdir(tmp_path)
    orchestrator = WorkflowOrchestrator(**kwargs)
    orchestrator._print_banner = lambda: None
    return orchestrator


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
    assert "downstream" not in wf.results


def test_scheduler_prevents_overlapping_runs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    daemon = SchedulerDaemon(workflows_dir="workflows", parse_interval=1)
    started = threading.Event()
    release = threading.Event()
    calls = {"count": 0}

    orchestrator = WorkflowOrchestrator(name="scheduled_workflow")
    orchestrator._print_banner = lambda: None

    def fake_run(*args, **kwargs):
        calls["count"] += 1
        started.set()
        release.wait(timeout=2)

    orchestrator.run = fake_run

    daemon._trigger_workflow(orchestrator)
    assert started.wait(timeout=1)
    daemon._trigger_workflow(orchestrator)
    time.sleep(0.1)
    assert calls["count"] == 1

    release.set()
    time.sleep(0.1)
    assert "scheduled_workflow" not in daemon._active_runs


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

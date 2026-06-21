import json
from pathlib import Path

from contig.progress import read_progress

TRACE = (
    "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\n"
    "1\tab/cd\t1\tFASTQC (S1)\tCOMPLETED\t0\t-\t-\t-\n"
    "2\tef/gh\t2\tSTAR_ALIGN (S1)\tRUNNING\t-\t-\t-\t-\n"
    "3\tij/kl\t3\tSALMON (S1)\tCOMPLETED\t0\t-\t-\t-\n"
)

# A reordered header (status/name not in the default positions) must still parse:
# columns are resolved by header name, never by index.
TRACE_REORDERED = (
    "status\tname\ttask_id\thash\texit\n"
    "COMPLETED\tFASTQC (S1)\t1\tab/cd\t0\n"
    "RUNNING\tSTAR_ALIGN (S1)\t2\tef/gh\t-\n"
)


def _write_status(run_dir, state, started_at="2026-06-22T00:00:00+00:00", finished_at=None):
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "status.json").write_text(
        json.dumps({"run_id": run_dir.name, "state": state, "started_at": started_at, "finished_at": finished_at})
    )


def test_read_progress_counts_completed_and_running_tasks(tmp_path):
    run_dir = tmp_path / "r"
    _write_status(run_dir, "running")
    (run_dir / "trace.txt").write_text(TRACE)
    snap = read_progress(tmp_path, "r")
    assert snap.tasks_completed == 2
    assert len(snap.tasks_running) == 1
    assert snap.tasks_running[0].process == "STAR_ALIGN (S1)"
    assert snap.submitted == 3


def test_read_progress_resolves_columns_by_header_not_index(tmp_path):
    run_dir = tmp_path / "r"
    _write_status(run_dir, "running")
    (run_dir / "trace.txt").write_text(TRACE_REORDERED)
    snap = read_progress(tmp_path, "r")
    assert snap.tasks_completed == 1
    assert snap.tasks_running[0].process == "STAR_ALIGN (S1)"


def test_read_progress_reports_state_from_status_json(tmp_path):
    run_dir = tmp_path / "r"
    _write_status(run_dir, "finished", finished_at="2026-06-22T00:01:00+00:00")
    (run_dir / "trace.txt").write_text(TRACE)
    snap = read_progress(tmp_path, "r")
    assert snap.state == "finished"
    assert snap.elapsed_sec == 60.0


def test_read_progress_state_is_missing_for_unknown_run(tmp_path):
    snap = read_progress(tmp_path, "ghost")
    assert snap.state == "missing"
    assert snap.tasks_completed == 0
    assert snap.tasks_running == []


def test_read_progress_reads_repair_attempts_from_jsonl(tmp_path):
    run_dir = tmp_path / "r"
    _write_status(run_dir, "running")
    (run_dir / "trace.txt").write_text(TRACE)
    step = {
        "attempt": 1,
        "diagnosis": {"failure_class": "oom", "root_cause": "OOM", "evidence": [], "confidence": 0.9},
        "patch": None,
        "outcome": "patched_and_retried",
    }
    (run_dir / "repair_progress.jsonl").write_text(json.dumps(step) + "\n")
    snap = read_progress(tmp_path, "r")
    assert len(snap.repairs) == 1
    assert snap.repairs[0].attempt == 1
    assert snap.repairs[0].failure_class == "oom"
    assert snap.repairs[0].outcome == "patched_and_retried"


def test_read_progress_tolerates_absent_trace_and_repair_files(tmp_path):
    run_dir = tmp_path / "r"
    _write_status(run_dir, "running")
    snap = read_progress(tmp_path, "r")
    assert snap.state == "running"
    assert snap.tasks_completed == 0
    assert snap.repairs == []
    assert snap.submitted is None

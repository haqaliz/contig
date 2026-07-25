"""Tests for in-run lifecycle controls: cancel and resume (PRD contracts A, B).

These never spawn real Nextflow. cancel is tested against a fixture status.json
with the process-group kill monkeypatched (or a real short-lived child), and
resume is tested by rebuilding the invocation from a fixture launch.json and
asserting the command an injected executor captures.
"""

import json
import os
import signal
from pathlib import Path

import pytest

from contig.lifecycle import (
    CancelError,
    ResumeError,
    cancel_run,
    resumable_state,
)


def _write_status(runs_dir, run_id, state, pid, child_pgid=None):
    d = Path(runs_dir) / run_id
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "state": state,
        "pid": pid,
        "started_at": "2026-06-22T00:00:00+00:00",
        "finished_at": None,
    }
    # Only set the key when a caller actually wants one: a status.json with no
    # child_pgid key at all (not a null one) is the shape we pin. That is not
    # only a pre-watchdog/non-watchdog run -- self_heal._write_status writes a
    # fresh dict rather than merging, so a *current* watchdog run also has no
    # child_pgid key in the window between a state-transition write and the
    # next attempt's executor republishing it (see cancel_run's comment).
    if child_pgid is not None:
        payload["child_pgid"] = child_pgid
    (d / "status.json").write_text(json.dumps(payload))
    return d


def test_cancel_kills_process_group_and_writes_cancelled(tmp_path, monkeypatch):
    _write_status(tmp_path, "r", "running", pid=4321)
    killed = []

    def fake_killpg(pgid, sig):
        killed.append((pgid, sig))

    def fake_getpgid(pid):
        return pid

    def fake_kill(pid, sig):
        # liveness probe (signal 0) says alive once, then dead after SIGTERM
        if sig == 0 and (4321, signal.SIGTERM) in killed:
            raise ProcessLookupError
        if sig == 0:
            return None
        raise ProcessLookupError

    monkeypatch.setattr(os, "killpg", fake_killpg)
    monkeypatch.setattr(os, "getpgid", fake_getpgid)
    monkeypatch.setattr(os, "kill", fake_kill)

    cancel_run(tmp_path, "r")

    assert (4321, signal.SIGTERM) in killed
    status = json.loads((tmp_path / "r" / "status.json").read_text())
    assert status["state"] == "cancelled"
    assert status["finished_at"] is not None


def test_cancel_escalates_to_sigkill_when_still_alive(tmp_path, monkeypatch):
    _write_status(tmp_path, "r", "running", pid=999)
    killed = []
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: killed.append(sig))
    monkeypatch.setattr(os, "getpgid", lambda pid: pid)
    # the process stays alive through the liveness probe so SIGKILL must follow
    monkeypatch.setattr(os, "kill", lambda pid, sig: None)

    cancel_run(tmp_path, "r", wait_seconds=0.0)

    assert signal.SIGTERM in killed
    assert signal.SIGKILL in killed


def test_cancel_works_on_awaiting_approval_run(tmp_path, monkeypatch):
    _write_status(tmp_path, "r", "awaiting_approval", pid=4321)
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: None)
    monkeypatch.setattr(os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(os, "kill", lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError()))

    cancel_run(tmp_path, "r")

    status = json.loads((tmp_path / "r" / "status.json").read_text())
    assert status["state"] == "cancelled"


def test_cancel_emits_cancelled_notification(tmp_path, monkeypatch):
    _write_status(tmp_path, "r", "running", pid=4321)
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: None)
    monkeypatch.setattr(os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(os, "kill", lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError()))

    cancel_run(tmp_path, "r")

    feed = (tmp_path / "notifications.jsonl").read_text().splitlines()
    rows = [json.loads(line) for line in feed]
    assert rows[-1]["kind"] == "cancelled"
    assert rows[-1]["run_id"] == "r"


def test_cancel_does_not_emit_when_refused(tmp_path):
    # A run that cannot be cancelled (already finished) writes no notification.
    _write_status(tmp_path, "r", "finished", pid=4321)
    with pytest.raises(CancelError):
        cancel_run(tmp_path, "r")
    assert not (tmp_path / "notifications.jsonl").exists()


def test_cancel_refuses_a_finished_run(tmp_path):
    _write_status(tmp_path, "r", "finished", pid=4321)
    with pytest.raises(CancelError):
        cancel_run(tmp_path, "r")


def test_cancel_refuses_a_run_with_no_status(tmp_path):
    with pytest.raises(CancelError):
        cancel_run(tmp_path, "ghost")


def test_cancel_marks_cancelled_even_if_pid_already_dead(tmp_path, monkeypatch):
    # The run says running but the process is already gone. Cancel still writes
    # the terminal cancelled state (a dead-but-running run is what the user wants
    # cleared) rather than failing.
    _write_status(tmp_path, "r", "running", pid=4321)
    monkeypatch.setattr(os, "getpgid", lambda pid: (_ for _ in ()).throw(ProcessLookupError()))

    cancel_run(tmp_path, "r")

    status = json.loads((tmp_path / "r" / "status.json").read_text())
    assert status["state"] == "cancelled"
    assert status["finished_at"] is not None


def test_cancel_reaps_child_group_before_run_group(tmp_path, monkeypatch):
    # D2: the watchdog's child lives in its own detached group (child_pgid);
    # it must die before contig's own group so the pipeline never outlives its
    # supervisor.
    _write_status(tmp_path, "r", "running", pid=100, child_pgid=200)
    order = []

    def fake_killpg(pgid, sig):
        if sig == signal.SIGTERM:
            order.append(pgid)

    monkeypatch.setattr(os, "killpg", fake_killpg)
    monkeypatch.setattr(os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(os, "kill", lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError()))

    cancel_run(tmp_path, "r", wait_seconds=0.0)

    assert order == [200, 100]


def test_cancel_without_child_pgid_behaves_as_before(tmp_path, monkeypatch):
    # Back-compat: a status.json with no child_pgid key reaps only the run's
    # own group, exactly as it did before this feature existed. This is not
    # only "a run from before the watchdog existed" -- self_heal._write_status
    # writes a fresh dict rather than merging, so a live watchdog run's own
    # state-transition writes (between attempts, after run_pipeline has
    # already returned and no child is alive) also clobber the key. Either
    # way there is nothing beyond pid's group to reap, so one code path
    # covering both is correct, not a coincidence.
    _write_status(tmp_path, "r", "running", pid=4321)
    killed = []
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: killed.append(pgid))
    monkeypatch.setattr(os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(os, "kill", lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError()))

    cancel_run(tmp_path, "r")

    assert killed == [4321]


def test_cancel_with_dead_child_pgid_still_reaps_run_group(tmp_path, monkeypatch):
    # A child_pgid whose process is already gone (os.getpgid -> ProcessLookupError)
    # must not be an error, and must not block reaping the run's own group.
    _write_status(tmp_path, "r", "running", pid=100, child_pgid=200)
    killed = []

    def fake_getpgid(pid):
        if pid == 200:
            raise ProcessLookupError
        return pid

    monkeypatch.setattr(os, "getpgid", fake_getpgid)
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: killed.append(pgid))
    monkeypatch.setattr(os, "kill", lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError()))

    cancel_run(tmp_path, "r")

    assert killed == [100]
    status = json.loads((tmp_path / "r" / "status.json").read_text())
    assert status["state"] == "cancelled"


@pytest.mark.parametrize("bad_child_pgid", ["not-a-pid", None, 12.5])
def test_cancel_ignores_malformed_child_pgid(tmp_path, monkeypatch, bad_child_pgid):
    d = tmp_path / "r"
    d.mkdir(parents=True)
    (d / "status.json").write_text(
        json.dumps(
            {
                "run_id": "r",
                "state": "running",
                "pid": 4321,
                "child_pgid": bad_child_pgid,
                "started_at": "2026-06-22T00:00:00+00:00",
                "finished_at": None,
            }
        )
    )
    killed = []
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: killed.append(pgid))
    monkeypatch.setattr(os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(os, "kill", lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError()))

    cancel_run(tmp_path, "r")

    assert killed == [4321]
    status = json.loads((tmp_path / "r" / "status.json").read_text())
    assert status["state"] == "cancelled"


def test_resumable_state_accepts_cancelled_run(tmp_path, monkeypatch):
    _write_status(tmp_path, "r", "cancelled", pid=4321)
    # state alone qualifies; liveness is irrelevant for a cancelled run
    resumable_state(tmp_path, "r")


def test_resumable_state_accepts_interrupted_run(tmp_path, monkeypatch):
    # status says running but the pid is dead -> interrupted -> resumable
    _write_status(tmp_path, "r", "running", pid=4321)
    monkeypatch.setattr(os, "kill", lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError()))
    resumable_state(tmp_path, "r")


def test_resumable_state_refuses_a_live_running_run(tmp_path, monkeypatch):
    _write_status(tmp_path, "r", "running", pid=4321)
    monkeypatch.setattr(os, "kill", lambda pid, sig: None)  # alive
    with pytest.raises(ResumeError):
        resumable_state(tmp_path, "r")


def test_resumable_state_refuses_a_finished_run(tmp_path):
    _write_status(tmp_path, "r", "finished", pid=4321)
    with pytest.raises(ResumeError):
        resumable_state(tmp_path, "r")


def test_resumable_state_refuses_a_run_with_no_status(tmp_path):
    with pytest.raises(ResumeError):
        resumable_state(tmp_path, "ghost")


def test_write_approval_records_approve_decision(tmp_path):
    from contig.lifecycle import write_approval

    d = tmp_path / "r"
    d.mkdir()
    write_approval(tmp_path, "r", approve=True)
    data = json.loads((d / "approval.json").read_text())
    assert data["decision"] == "approve"
    assert data["decided_at"]


def test_write_approval_records_reject_decision(tmp_path):
    from contig.lifecycle import write_approval

    d = tmp_path / "r"
    d.mkdir()
    write_approval(tmp_path, "r", approve=False)
    data = json.loads((d / "approval.json").read_text())
    assert data["decision"] == "reject"


def test_write_approval_records_choice_index(tmp_path):
    from contig.lifecycle import write_approval

    d = tmp_path / "r"
    d.mkdir()
    write_approval(tmp_path, "r", approve=True, choice=1)
    data = json.loads((d / "approval.json").read_text())
    assert data["decision"] == "approve"
    assert data["choice"] == 1


def test_write_approval_omits_choice_when_not_a_choice_gate(tmp_path):
    from contig.lifecycle import write_approval

    d = tmp_path / "r"
    d.mkdir()
    write_approval(tmp_path, "r", approve=True)
    data = json.loads((d / "approval.json").read_text())
    assert "choice" not in data

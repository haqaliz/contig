"""Phase 1 of auto-approve attendance: persist `--auto-approve` on launch.json.

`contig repair-stats` (repair_stats.py) computes the unattended-completion rate
that gates a roadmap phase, but it cannot tell whether a human was in the loop
unless that fact is recorded somewhere durable. This module is Phase 1 only:
it persists `auto_approve` on `LaunchManifest` (runs/<id>/launch.json). Later
phases read it; nothing here changes `RunRecord`, `signing.py`, or `bundle.py`.
"""

import json

from typer.testing import CliRunner

from contig.cli import app
from contig.models import LaunchManifest
from tests.test_cli import GOOD_MQC, TRACE_OK, TRACE_RUN_OK, _fake_run_executor, _make_sheet

runner = CliRunner()


def test_launch_manifest_round_trips_auto_approve_true():
    # AC#1: auto_approve is a real field that survives a dump/parse round trip,
    # not silently dropped when set.
    base_kwargs = dict(
        run_id="r1",
        pipeline="nf-core/rnaseq",
        revision="3.14.0",
        profiles=["docker"],
        backend="local",
        container_runtime="docker",
        created_at="2026-09-06T00:00:00+00:00",
    )
    manifest_true = LaunchManifest(**base_kwargs, auto_approve=True)
    assert json.loads(manifest_true.model_dump_json())["auto_approve"] is True
    round_tripped = LaunchManifest.model_validate_json(manifest_true.model_dump_json())
    assert round_tripped.auto_approve is True


def test_launch_manifest_serializes_auto_approve_false_explicitly():
    # AC#1: `False` is falsy in Python, so a naive `exclude_none`-style dump could
    # collapse it to "absent" the way it does for other optional fields. It must be
    # written out explicitly rather than dropped, since Phase 2+ distinguishes a
    # recorded `False` from an absent field (see the legacy-manifest test below).
    base_kwargs = dict(
        run_id="r1",
        pipeline="nf-core/rnaseq",
        revision="3.14.0",
        profiles=["docker"],
        backend="local",
        container_runtime="docker",
        created_at="2026-09-06T00:00:00+00:00",
    )
    manifest_false = LaunchManifest(**base_kwargs, auto_approve=False)
    assert json.loads(manifest_false.model_dump_json())["auto_approve"] is False


def test_launch_manifest_without_auto_approve_key_validates_to_none_not_false():
    # AC#2: a legacy launch.json (written before this field existed) must not
    # be silently reinterpreted as "no human was ever in the loop" (False).
    # Absent must stay distinguishable from a recorded False -- the same
    # patch_applied-style defect noted at models.py:317-322 for other fields.
    legacy_json = json.dumps(
        {
            "run_id": "legacy",
            "pipeline": "nf-core/rnaseq",
            "revision": "3.14.0",
            "profiles": ["docker"],
            "backend": "local",
            "container_runtime": "docker",
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    )
    manifest = LaunchManifest.model_validate_json(legacy_json)
    assert manifest.auto_approve is None
    assert manifest.auto_approve is not False


def test_run_with_auto_approve_flag_writes_true_to_launch_manifest(tmp_path, monkeypatch):
    # AC#3 (flag present).
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_OK, GOOD_MQC))
    runner.invoke(
        app,
        ["run", "--run-id", "aa-true", "--runs-dir", str(tmp_path), "--auto-approve"],
    )
    manifest = json.loads((tmp_path / "aa-true" / "launch.json").read_text())
    assert manifest["auto_approve"] is True


def test_run_without_auto_approve_flag_writes_false_to_launch_manifest(tmp_path, monkeypatch):
    # AC#3 (flag absent) -- `run`'s own default is False, not None: an actual
    # `run` invocation always makes an attended/unattended decision.
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_OK, GOOD_MQC))
    runner.invoke(app, ["run", "--run-id", "aa-false", "--runs-dir", str(tmp_path)])
    manifest = json.loads((tmp_path / "aa-false" / "launch.json").read_text())
    assert manifest["auto_approve"] is False


def test_rerun_of_auto_approved_manifest_writes_false_not_replayed(tmp_path, monkeypatch):
    # AC#4: TRIPWIRE. `rerun` has no `--auto-approve` flag of its own (cli.py:836-843)
    # and must NOT replay the original manifest's `auto_approve` out of symmetry
    # with the other replayed fields (pipeline, revision, caps, ...). If a future
    # editor wires `auto_approve=manifest.auto_approve` into the rerun dispatch
    # mapping at cli.py:878-901, this test goes red: the reproduced run's own
    # manifest would then read `auto_approve: true` with no human ever having
    # passed `--auto-approve` to the `rerun` command itself.
    sheet = _make_sheet(tmp_path)
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_RUN_OK, GOOD_MQC))
    runner.invoke(
        app,
        ["run", "--run-id", "orig-aa", "--runs-dir", str(tmp_path / "runs"),
         "--input", str(sheet), "--genome", "GRCh38", "--auto-approve"],
    )
    orig_manifest = json.loads((tmp_path / "runs" / "orig-aa" / "launch.json").read_text())
    assert orig_manifest["auto_approve"] is True  # sanity: the fixture set up what we think it did

    result = runner.invoke(
        app,
        ["rerun", "orig-aa", "--runs-dir", str(tmp_path / "runs"), "--new-run-id", "copy-aa"],
    )
    assert result.exit_code == 0
    new_manifest = json.loads((tmp_path / "runs" / "copy-aa" / "launch.json").read_text())
    assert new_manifest["auto_approve"] is False


def test_resume_after_auto_approved_run_leaves_manifest_auto_approve_false(tmp_path, monkeypatch):
    # AC#14: `resume` (cli.py:2508-2514) has no `--auto-approve` flag either, and it
    # re-decides the manifest as False for the LAST invocation (the unattended resume),
    # not the original `run --auto-approve` that preceded it. Named for that reasoning
    # because a naive reader could otherwise expect resume to "inherit" attendance the
    # way it inherits pipeline/revision/caps.
    #
    # This does NOT mean the manifest and record always describe the same invocation:
    # `launch.json` is written before the run starts (cli.py:791) but `run_record.json`
    # only at the end (self_heal.py:239), so a resume that dies before finishing would
    # leave this invocation's `auto_approve: false` sitting beside the *previous*
    # invocation's `repair_history`. That failure mode is conservative -- it can only
    # relabel a truly unattended gated step as attended, understating the unattended
    # rate -- and is untested here; this test only covers the resume-completes case.
    sheet = _make_sheet(tmp_path)
    monkeypatch.setattr("contig.cli.default_executor", _fake_run_executor(TRACE_RUN_OK, GOOD_MQC))
    runner.invoke(
        app,
        ["run", "--run-id", "resume-aa", "--runs-dir", str(tmp_path / "runs"),
         "--input", str(sheet), "--genome", "GRCh38", "--auto-approve"],
    )
    orig_manifest = json.loads((tmp_path / "runs" / "resume-aa" / "launch.json").read_text())
    assert orig_manifest["auto_approve"] is True

    # mark it cancelled so resumable_state (cli.py) accepts it (mirrors
    # tests/test_cli.py::test_resume_reruns_same_run_id_with_resume_flag)
    (tmp_path / "runs" / "resume-aa" / "status.json").write_text(
        json.dumps({"run_id": "resume-aa", "state": "cancelled", "pid": 4321,
                    "started_at": "2026-06-22T00:00:00+00:00", "finished_at": "2026-06-22T00:01:00+00:00"})
    )

    result = runner.invoke(app, ["resume", "resume-aa", "--runs-dir", str(tmp_path / "runs")])
    assert result.exit_code == 0, result.output
    resumed_manifest = json.loads(
        (tmp_path / "runs" / "resume-aa" / "launch.json").read_text()
    )
    assert resumed_manifest["auto_approve"] is False

"""CLI tests for `contig repair-stats` (repair-success-analytics, cli-surface).

The numbers are `stats-core`'s; this surface is judged on whether a reader can
tell what they count and can discard what they distrust. So the assertions here
are about disclosure — the rate carrying its denominator, the exclusions naming
their reasons, and the legacy-derived count being stated rather than left to be
inferred by subtraction.
"""

import json
from pathlib import Path

from typer.testing import CliRunner

from contig.bundle import write_bundle
from contig.cli import app
from contig.models import ExecutionTarget, RepairStep, RunRecord, TaskEvent

runner = CliRunner()

_OMIT = object()

_COMPLETED = TaskEvent(process="X", status="COMPLETED", exit=0)
_FAILED = TaskEvent(process="X", status="FAILED", exit=1)


def _raw_step(outcome, *, failure_class="tool_crash", attempt=1, patch_applied=_OMIT):
    """A raw `repair_history` dict. `patch_applied` is OMITTED unless asked for.

    Omission is the legacy shape and therefore the default: a helper that always
    emitted the key would make every legacy assertion pass vacuously.
    """
    raw = {
        "attempt": attempt,
        "diagnosis": {
            "failure_class": failure_class,
            "root_cause": "rc",
            "evidence": [],
            "confidence": 0.5,
        },
        "patch": None,
        "outcome": outcome,
        "detail": None,
    }
    if patch_applied is not _OMIT:
        raw["patch_applied"] = patch_applied
    return raw


def _write_run(runs_dir, run_id, *, raw_steps=(), events=(_COMPLETED,), legacy=False):
    """Write a real bundle, optionally stripped back to the pre-v0.49.0 shape.

    `model_dump_json` ALWAYS emits `patch_applied`, so a bundle written straight
    from the model can never be a legacy fixture. The post-write edit on disk is
    the only way to produce a record that genuinely omits the key.
    """
    raw_steps = list(raw_steps)
    record = RunRecord(
        run_id=run_id,
        pipeline="nf-core/rnaseq",
        pipeline_revision="3.26.0",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="w"),
        input_checksums={},
        events=list(events),
        repair_history=[RepairStep.model_validate(raw) for raw in raw_steps],
    )
    write_bundle(record, Path(runs_dir) / run_id)
    if legacy:
        path = Path(runs_dir) / run_id / "run_record.json"
        data = json.loads(path.read_text())
        for step in data["repair_history"]:
            del step["patch_applied"]
        path.write_text(json.dumps(data, indent=2))


# --- JSON mode and the empty path ----------------------------------------------


def test_json_carries_the_documented_top_level_keys(tmp_path):
    _write_run(tmp_path, "r1")
    result = runner.invoke(app, ["repair-stats", "--runs-dir", str(tmp_path), "--json"])
    assert result.exit_code == 0
    report = json.loads(result.output)
    assert set(report) == {"runs", "steps", "thin", "unmapped_outcomes"}


def test_json_counts_the_steps_of_every_bundle_in_the_dir(tmp_path):
    _write_run(tmp_path, "r1", raw_steps=[_raw_step("patched_and_retried")])
    _write_run(tmp_path, "r2", raw_steps=[_raw_step("gave_up"), _raw_step("gave_up", attempt=2)], events=(_FAILED,))
    result = runner.invoke(app, ["repair-stats", "--runs-dir", str(tmp_path), "--json"])
    assert result.exit_code == 0
    report = json.loads(result.output)
    assert report["steps"]["total"] == 3
    assert report["steps"]["by_family"] == {"applied": 1, "gave_up": 2}


def test_a_missing_runs_dir_reports_no_runs_rather_than_a_zero_rate(tmp_path):
    # A rate of 0% would be a claim about repairs; "no runs" is the honest one.
    missing = tmp_path / "absent"
    result = runner.invoke(app, ["repair-stats", "--runs-dir", str(missing)])
    assert result.exit_code == 0
    assert f"No runs found in {missing}." in result.output
    assert "%" not in result.output

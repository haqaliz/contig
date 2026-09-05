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


# --- text rendering: the disclosures -------------------------------------------


def test_the_totals_line_labels_both_runs_and_steps(tmp_path):
    _write_run(tmp_path, "r1", raw_steps=[_raw_step("gave_up")], events=(_FAILED,))
    result = runner.invoke(app, ["repair-stats", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "Repair stats: 1 run(s), 1 repair step(s)." in result.output


def test_the_rate_carries_its_denominator_on_the_same_line(tmp_path):
    # A bare percentage invites the reader to take 66.7% as a field measurement.
    _write_run(tmp_path, "r1")
    _write_run(tmp_path, "r2")
    _write_run(tmp_path, "r3", raw_steps=[_raw_step("gave_up")], events=(_FAILED,))
    result = runner.invoke(app, ["repair-stats", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    percent_lines = [line for line in result.output.splitlines() if "%" in line]
    assert percent_lines == ["  unattended completion: 2/3 scored run(s) (66.7%)"]


def test_a_zero_event_run_is_excluded_and_the_reason_is_stated(tmp_path):
    _write_run(tmp_path, "r1")
    _write_run(tmp_path, "empty", events=())
    result = runner.invoke(app, ["repair-stats", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "1 run(s) not analyzable (no task events) -- excluded from both sides" in result.output


def test_the_not_analyzable_line_is_absent_when_every_run_is_analyzable(tmp_path):
    _write_run(tmp_path, "r1")
    result = runner.invoke(app, ["repair-stats", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "not analyzable" not in result.output


def test_an_attendance_unknown_run_is_excluded_and_the_line_says_why(tmp_path):
    # `approved_and_retried` fires on a human approval AND under `--auto-approve`,
    # and the flag is never persisted, so the record cannot tell the two apart.
    _write_run(tmp_path, "r1")
    _write_run(tmp_path, "r2", raw_steps=[_raw_step("approved_and_retried")])
    result = runner.invoke(app, ["repair-stats", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert (
        "    1 run(s) attendance unknown (a human, or --auto-approve, which is never"
        " recorded) -- excluded from both sides"
    ) in result.output


def test_the_rate_is_qualified_as_a_completion_rate_not_a_recovery_rate(tmp_path):
    # "64.3%" otherwise reads as "the self-heal loop works two thirds of the time".
    # It is high mostly because most runs never failed at all.
    _write_run(tmp_path, "r1")
    result = runner.invoke(app, ["repair-stats", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "    a completion rate, not a recovery rate: it counts runs that never failed" in result.output


def test_the_family_block_states_that_it_counts_steps(tmp_path):
    _write_run(
        tmp_path,
        "r1",
        raw_steps=[_raw_step("patched_and_retried"), _raw_step("gave_up", attempt=2)],
        events=(_FAILED,),
    )
    result = runner.invoke(app, ["repair-stats", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "  by outcome family (per step):\n    applied: 1\n    gave_up: 1\n" in result.output


def _thin_and_thick(tmp_path):
    _write_run(
        tmp_path,
        "r1",
        raw_steps=[
            _raw_step("gave_up", failure_class="tool_crash", attempt=1),
            _raw_step("gave_up", failure_class="tool_crash", attempt=2),
            _raw_step("gave_up", failure_class="tool_crash", attempt=3),
            _raw_step("gave_up", failure_class="oom", attempt=4),
        ],
        events=(_FAILED,),
    )
    return runner.invoke(app, ["repair-stats", "--runs-dir", str(tmp_path)])


def test_a_failure_class_below_the_thin_threshold_is_suffixed_thin(tmp_path):
    result = _thin_and_thick(tmp_path)
    assert result.exit_code == 0
    assert "    oom: 1  THIN" in result.output


def test_a_failure_class_at_the_thin_threshold_is_not_suffixed(tmp_path):
    # At n=3 the flag already discriminates, which is the whole reason it earns space.
    result = _thin_and_thick(tmp_path)
    assert result.exit_code == 0
    assert "    tool_crash: 3\n" in result.output


def test_the_read_count_is_stated_outright_when_it_is_zero(tmp_path):
    # "read 0" is the sharpest fact in the report: not one step in this corpus says
    # for itself whether its patch was enacted. It must not need subtraction to see.
    _write_run(
        tmp_path,
        "r1",
        raw_steps=[_raw_step("patched_and_retried"), _raw_step("gave_up", attempt=2)],
        events=(_FAILED,),
        legacy=True,
    )
    result = runner.invoke(app, ["repair-stats", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "  patch enacted (per step): read 0, legacy-derived 2, unknown 0" in result.output


def test_the_legacy_derivation_is_broken_out_from_the_counts_read(tmp_path):
    # Derived numbers are kept apart so a reader can discard all of them at once.
    _write_run(
        tmp_path,
        "r1",
        raw_steps=[_raw_step("patched_and_retried"), _raw_step("gave_up", attempt=2)],
        events=(_FAILED,),
        legacy=True,
    )
    result = runner.invoke(app, ["repair-stats", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "    of the 2 legacy-derived: applied 1, not applied 1" in result.output


def test_a_step_that_records_the_field_is_counted_as_read(tmp_path):
    _write_run(
        tmp_path,
        "r1",
        raw_steps=[_raw_step("patched_and_retried", patch_applied=True)],
        events=(_FAILED,),
    )
    result = runner.invoke(app, ["repair-stats", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "    of the 1 read: applied 1, not applied 0" in result.output


def test_an_outcome_outside_the_taxonomy_is_surfaced_by_name(tmp_path):
    # An out-of-date map is a finding, not a rounding error, so the literal is named.
    _write_run(
        tmp_path,
        "r1",
        raw_steps=[_raw_step("stopped_for_confirmation")],
        events=(_FAILED,),
    )
    result = runner.invoke(app, ["repair-stats", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "  unmapped outcome(s): stopped_for_confirmation=1" in result.output


def test_the_note_distinguishing_this_from_heal_guard_is_always_printed(tmp_path):
    # Two numbers named "recovery" over two different populations is the confusion
    # this report is most likely to cause, so the note is unconditional.
    _write_run(tmp_path, "r1")
    result = runner.invoke(app, ["repair-stats", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert (
        "  note: over real runs -- not `heal-guard`'s recovery_rate,"
        " which scores synthetic scenarios."
    ) in result.output


def test_a_rate_with_nothing_to_divide_by_is_not_computable_not_zero(tmp_path):
    # "0%" would say every run failed unattended; the truth is that none was scorable.
    _write_run(tmp_path, "empty", events=())
    result = runner.invoke(app, ["repair-stats", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "  unattended completion: not computable (0 scored run(s))" in result.output
    assert "%" not in result.output


def test_the_qualifier_is_omitted_when_there_is_no_rate_to_qualify(tmp_path):
    _write_run(tmp_path, "empty", events=())
    result = runner.invoke(app, ["repair-stats", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "recovery rate" not in result.output


def test_a_corpus_with_no_repair_steps_omits_the_per_step_blocks(tmp_path):
    _write_run(tmp_path, "r1")
    result = runner.invoke(app, ["repair-stats", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "per step" not in result.output


def test_two_invocations_over_one_fixture_render_identical_output(tmp_path):
    _write_run(
        tmp_path,
        "r1",
        raw_steps=[
            _raw_step("patched_and_retried", failure_class="oom"),
            _raw_step("gave_up", failure_class="tool_crash", attempt=2),
            _raw_step("stopped_for_confirmation", failure_class="unknown", attempt=3),
        ],
        events=(_FAILED,),
        legacy=True,
    )
    _write_run(tmp_path, "r2")
    args = ["repair-stats", "--runs-dir", str(tmp_path)]
    first = runner.invoke(app, args)
    second = runner.invoke(app, args)
    assert first.exit_code == 0
    assert first.output == second.output

"""Tests for repair-success statistics over run records (stats-core).

The record under-determines two questions — was the patch enacted, and was a
human in the loop — so the classifiers answer in three states rather than
inventing a second. These tests pin the 19-literal taxonomy against the shipped
dashboard families and hold the three-state answers honest.
"""

import json
from pathlib import Path

from contig.bundle import write_bundle
from contig.corpus import _THIN_THRESHOLD as _CORPUS_THIN_THRESHOLD
from contig.models import ExecutionTarget, RepairStep, RunRecord, TaskEvent
from contig.repair_stats import (
    LoadedRun,
    _THIN_THRESHOLD,
    ACKNOWLEDGED_OUTCOMES,
    APPLIED_OUTCOMES,
    ATTENDANCE_UNKNOWN_OUTCOMES,
    ATTENDED_OUTCOMES,
    DECLINED_OUTCOMES,
    FLAGGED_OUTCOMES,
    GAVE_UP_OUTCOMES,
    OUTCOME_FAMILY,
    classify_applied,
    classify_attendance,
    collect_runs,
    derived_applied,
    repair_stats_report,
)

# The taxonomy as documented, restated independently of the module so the pin is
# a real comparison rather than a tautology
# (dashboard/components/run/repair-timeline.tsx:86-192).
_DOCUMENTED_LITERALS = {
    "patched_and_retried",
    "approved_and_retried",
    "chose_and_retried",
    "built_index_and_retried",
    "recompressed_reference_and_retried",
    "installed_and_retried",
    "retry_failed",
    "rejected_by_user",
    "approval_timed_out",
    "invalid_choice_rejected",
    "gave_up",
    "gave_up_at_ceiling",
    "index_build_failed",
    "index_unresolvable",
    "reference_recompress_failed",
    "reference_recompress_unresolvable",
    "install_failed",
    "qc_verdict_flagged",
    "advisory_acknowledged_and_retried",
}

_FAMILY_SETS = {
    "applied": APPLIED_OUTCOMES,
    "declined": DECLINED_OUTCOMES,
    "gave_up": GAVE_UP_OUTCOMES,
    "flagged": FLAGGED_OUTCOMES,
    "acknowledged": ACKNOWLEDGED_OUTCOMES,
}


# --- the taxonomy pins (AC-9, AC-10) -------------------------------------------


def test_families_together_cover_exactly_the_nineteen_shipped_literals():
    union = set().union(*_FAMILY_SETS.values())
    assert union == _DOCUMENTED_LITERALS


def test_no_literal_belongs_to_two_families():
    seen: set[str] = set()
    for literals in _FAMILY_SETS.values():
        assert not (seen & literals)
        seen |= literals


def test_derived_applied_is_true_for_exactly_the_applied_family():
    for literal in OUTCOME_FAMILY:
        assert derived_applied(literal) is (literal in APPLIED_OUTCOMES)


def test_derived_applied_is_none_for_an_unmapped_literal():
    assert derived_applied("stopped_for_confirmation") is None


def test_the_attendance_sets_name_only_literals_the_taxonomy_knows():
    assert (ATTENDED_OUTCOMES | ATTENDANCE_UNKNOWN_OUTCOMES) <= _DOCUMENTED_LITERALS


def test_the_thin_threshold_matches_the_corpus_one():
    assert _THIN_THRESHOLD == _CORPUS_THIN_THRESHOLD


# --- the applied classifier (AC-1, AC-2, AC-3, AC-4) ---------------------------
# The fixtures below are load-bearing: the legacy ones OMIT the `patch_applied`
# key entirely, the others SET it. A fixture that always emits the key would make
# the legacy case pass vacuously, which is the whole guarantee under test.


def test_a_step_written_before_the_field_existed_is_legacy_derived():
    legacy_step = {"outcome": "patched_and_retried"}
    assert classify_applied("patched_and_retried", legacy_step) == "legacy_derived"


def test_a_step_recording_the_field_as_false_is_not_applied():
    recorded_step = {"outcome": "patched_and_retried", "patch_applied": False}
    assert classify_applied("patched_and_retried", recorded_step) == "not_applied"


def test_a_step_recording_the_field_as_true_is_applied():
    recorded_step = {"outcome": "patched_and_retried", "patch_applied": True}
    assert classify_applied("patched_and_retried", recorded_step) == "applied"


def test_a_recorded_field_outranks_an_unmapped_outcome():
    # Replaces an earlier pin that returned `unknown` here. Key presence WINS: when the
    # record states that the patch was enacted, that is a fact about this step. The map
    # exists only to reconstruct what an ABSENT key must have meant, so leaning on it
    # over a stated value would discard information the record actually carries.
    unmapped_step = {"outcome": "stopped_for_confirmation", "patch_applied": True}
    assert classify_applied("stopped_for_confirmation", unmapped_step) == "applied"


def test_an_unmapped_literal_with_no_recorded_field_is_unknown():
    # The surviving half of that older pin: nothing stated, and the map — the only
    # evidence for an absent key — does not know this literal.
    unmapped_step = {"outcome": "stopped_for_confirmation"}
    assert classify_applied("stopped_for_confirmation", unmapped_step) == "unknown"


# --- the attendance classifier (AC-4, AC-5, AC-6) ------------------------------


def test_an_unmapped_literal_has_unknown_attendance():
    assert classify_attendance("stopped_for_confirmation") == "unknown"


def test_an_acknowledged_advisory_is_attended():
    assert classify_attendance("advisory_acknowledged_and_retried") == "attended"


def test_an_approved_patch_has_unknown_attendance():
    # `--auto-approve` reaches this literal with no human involved, and the flag is
    # not persisted, so the record genuinely cannot say (PRD Addendum 2).
    assert classify_attendance("approved_and_retried") == "attendance_unknown"


def test_a_machine_only_outcome_is_unattended():
    assert classify_attendance("patched_and_retried") == "unattended"


def test_an_acknowledged_advisory_enacted_nothing_despite_its_suffix():
    # The tempting heuristic "the literal ends in _and_retried, so a patch ran" is
    # wrong exactly here: a human acknowledged guidance outside Contig and asked
    # the loop to retry; no patch was enacted (self_heal.py:1411-1423).
    assert derived_applied("advisory_acknowledged_and_retried") is False


# --- aggregation: the guarded rate (AC-11) -------------------------------------


def test_an_empty_report_has_a_none_rate_rather_than_zero():
    # `None` and `0.0` mean different things: "no run could be measured" is not
    # "no run completed". A 0% would be a claim the corpus does not support.
    report = repair_stats_report([])
    assert report["runs"]["unattended_completion_rate"] is None


def test_an_empty_report_is_well_formed_with_zero_counts():
    # Every bucket the CLI aspect will render exists even with nothing to count, so
    # a downstream renderer never has to guard a missing key.
    assert repair_stats_report([]) == {
        "runs": {
            "total": 0,
            "analyzable": 0,
            "not_analyzable": 0,
            "attendance_unknown": 0,
            "rate_denominator": 0,
            "unattended_completed": 0,
            "unattended_completion_rate": None,
        },
        "steps": {
            "total": 0,
            "by_family": {},
            "by_failure_class": {},
            "by_applied": {
                "applied": 0,
                "not_applied": 0,
                "legacy_derived": 0,
                "unknown": 0,
            },
            "by_attendance": {
                "attended": 0,
                "unattended": 0,
                "attendance_unknown": 0,
                "unknown": 0,
            },
            "legacy_derived_applied": {"applied": 0, "not_applied": 0},
        },
        "thin": [],
        "unmapped_outcomes": {},
    }


# --- aggregation fixtures ------------------------------------------------------
# The raw dict is the fixture and the model is derived FROM it, exactly as on disk:
# both halves of a `LoadedRun` come from the same JSON, so a fixture cannot make the
# model and the raw dict disagree about anything but key presence.

_OMIT = object()

_COMPLETED = TaskEvent(process="X", status="COMPLETED", exit=0)
_FAILED = TaskEvent(process="X", status="FAILED", exit=1)


def _raw_step(outcome, *, failure_class="tool_crash", attempt=1, patch_applied=_OMIT):
    """A raw `repair_history` dict. `patch_applied` is OMITTED unless asked for.

    Omission is the default deliberately: it is the legacy shape, and a helper that
    always emitted the key would make every legacy assertion pass vacuously (spec
    RISK). Passing `patch_applied=False` is a genuinely different fixture.
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


def _loaded_run(run_id, *, raw_steps=(), events=(_COMPLETED,)):
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
    return LoadedRun(run_id=run_id, record=record, raw_steps=raw_steps)


# --- aggregation: run-level rules (AC-5, AC-7, AC-8) ---------------------------


def test_a_run_with_events_is_analyzable():
    report = repair_stats_report([_loaded_run("r1")])
    assert report["runs"]["analyzable"] == 1


def test_a_zero_event_run_is_not_analyzable():
    # A run with no events derives succeeded=True vacuously (`models.py:156-158`:
    # failed_tasks == 0), so it must never be read as a completion.
    report = repair_stats_report([_loaded_run("r1", events=())])
    assert report["runs"]["analyzable"] == 0
    assert report["runs"]["not_analyzable"] == 1


def test_a_succeeded_run_with_no_attended_step_is_an_unattended_completion():
    report = repair_stats_report(
        [_loaded_run("r1", raw_steps=[_raw_step("patched_and_retried")])]
    )
    assert report["runs"]["rate_denominator"] == 1
    assert report["runs"]["unattended_completed"] == 1
    assert report["runs"]["unattended_completion_rate"] == 1.0


def test_a_failed_run_scores_a_zero_rate_which_is_not_the_none_of_no_data():
    report = repair_stats_report(
        [_loaded_run("r1", events=(_FAILED,), raw_steps=[_raw_step("gave_up")])]
    )
    assert report["runs"]["rate_denominator"] == 1
    assert report["runs"]["unattended_completed"] == 0
    assert report["runs"]["unattended_completion_rate"] == 0.0


def test_a_run_is_attended_when_any_step_is_attended_not_only_the_last():
    # Last-step-wins would read this run as unattended and inflate the rate: the
    # human who rejected attempt 1 is still in the loop for the whole run.
    steps = [
        _raw_step("rejected_by_user", attempt=1),
        _raw_step("patched_and_retried", attempt=2),
    ]
    report = repair_stats_report([_loaded_run("r1", raw_steps=steps)])
    assert report["runs"]["rate_denominator"] == 1
    assert report["runs"]["unattended_completed"] == 0


def test_a_succeeded_run_whose_only_step_is_approved_is_in_neither_side_of_the_rate():
    # AC-5. `--auto-approve` reaches `approved_and_retried` with no human involved and
    # the flag is not persisted, so counting the run either way would be a guess.
    report = repair_stats_report(
        [_loaded_run("r1", raw_steps=[_raw_step("approved_and_retried")])]
    )
    assert report["runs"]["attendance_unknown"] == 1
    assert report["runs"]["rate_denominator"] == 0
    assert report["runs"]["unattended_completed"] == 0
    assert report["runs"]["unattended_completion_rate"] is None


def test_a_zero_event_run_is_in_neither_side_of_the_rate():
    # AC-7. Alongside a real run, so the assertion cannot pass merely because the
    # report is empty: if the zero-event run were scored it would count as a
    # vacuous success and push both sides to 2.
    runs = [
        _loaded_run("ok", raw_steps=[_raw_step("patched_and_retried")]),
        _loaded_run("empty", events=(), raw_steps=[_raw_step("patched_and_retried")]),
    ]
    report = repair_stats_report(runs)
    assert report["runs"]["rate_denominator"] == 1
    assert report["runs"]["unattended_completed"] == 1


# --- aggregation: the per-step / per-run split (AC-8) ---------------------------


def test_a_two_step_run_yields_two_family_rows_and_one_run_in_the_rate():
    # AC-8. Families are counted per STEP, the rate per RUN; the split is the point.
    steps = [
        _raw_step("patched_and_retried", attempt=1),
        _raw_step("gave_up", attempt=2),
    ]
    report = repair_stats_report([_loaded_run("r1", events=(_FAILED,), raw_steps=steps)])
    assert report["steps"]["total"] == 2
    assert report["steps"]["by_family"] == {"applied": 1, "gave_up": 1}
    assert report["runs"]["rate_denominator"] == 1


# --- aggregation: the per-step buckets -----------------------------------------


def test_an_unmapped_literal_is_bucketed_rather_than_folded_into_a_family():
    report = repair_stats_report(
        [_loaded_run("r1", raw_steps=[_raw_step("stopped_for_confirmation")])]
    )
    assert report["unmapped_outcomes"] == {"stopped_for_confirmation": 1}
    assert report["steps"]["by_family"] == {}


def test_failure_classes_are_counted_per_step_from_the_diagnosis():
    # The class lives on `step.diagnosis.failure_class`; `step.failure_class` does not
    # exist on the model and is never read.
    steps = [
        _raw_step("gave_up", failure_class="oom", attempt=1),
        _raw_step("patched_and_retried", failure_class="oom", attempt=2),
        _raw_step("gave_up", failure_class="tool_crash", attempt=3),
    ]
    report = repair_stats_report([_loaded_run("r1", events=(_FAILED,), raw_steps=steps)])
    assert report["steps"]["by_failure_class"] == {"oom": 2, "tool_crash": 1}


def test_the_applied_axis_separates_an_omitted_key_from_a_recorded_false():
    # The three read states, side by side in one run: only the raw dict can tell the
    # first two apart, which is why `LoadedRun` carries it.
    steps = [
        _raw_step("patched_and_retried", attempt=1),
        _raw_step("patched_and_retried", attempt=2, patch_applied=False),
        _raw_step("patched_and_retried", attempt=3, patch_applied=True),
    ]
    report = repair_stats_report([_loaded_run("r1", raw_steps=steps)])
    assert report["steps"]["by_applied"] == {
        "applied": 1,
        "not_applied": 1,
        "legacy_derived": 1,
        "unknown": 0,
    }


def test_an_unmapped_step_still_counts_on_the_applied_axis_as_unknown():
    # It must not fall out of the totals: every step is on the axis somewhere, so
    # `by_applied` always sums to `steps.total`.
    report = repair_stats_report(
        [_loaded_run("r1", raw_steps=[_raw_step("stopped_for_confirmation")])]
    )
    assert report["steps"]["by_applied"]["unknown"] == 1
    assert sum(report["steps"]["by_applied"].values()) == report["steps"]["total"]


def test_the_attendance_axis_counts_every_step_including_the_unknown_ones():
    steps = [
        _raw_step("rejected_by_user", attempt=1),
        _raw_step("patched_and_retried", attempt=2),
        _raw_step("approved_and_retried", attempt=3),
        _raw_step("stopped_for_confirmation", attempt=4),
    ]
    report = repair_stats_report([_loaded_run("r1", raw_steps=steps)])
    assert report["steps"]["by_attendance"] == {
        "attended": 1,
        "unattended": 1,
        "attendance_unknown": 1,
        "unknown": 1,
    }


def test_the_legacy_derivation_is_reported_apart_from_the_read_counts():
    # Both steps are `legacy_derived` on the read axis; the derivation splits them.
    # Keeping the split in its own bucket is what lets a reader discard every derived
    # number without disturbing anything actually read from the record.
    steps = [
        _raw_step("patched_and_retried", attempt=1),
        _raw_step("gave_up", attempt=2),
    ]
    report = repair_stats_report([_loaded_run("r1", events=(_FAILED,), raw_steps=steps)])
    assert report["steps"]["by_applied"]["legacy_derived"] == 2
    assert report["steps"]["by_applied"]["applied"] == 0
    assert report["steps"]["legacy_derived_applied"] == {"applied": 1, "not_applied": 1}


def test_a_step_that_recorded_the_field_never_enters_the_derived_split():
    report = repair_stats_report(
        [_loaded_run("r1", raw_steps=[_raw_step("patched_and_retried", patch_applied=True)])]
    )
    assert report["steps"]["by_applied"]["applied"] == 1
    assert report["steps"]["legacy_derived_applied"] == {"applied": 0, "not_applied": 0}


def test_a_failure_class_below_the_threshold_is_flagged_thin():
    # `oom` reaches the threshold exactly and is therefore NOT thin; `disk_full` has
    # one step and is too thin to read anything from.
    steps = [
        _raw_step("gave_up", failure_class="oom", attempt=n)
        for n in range(1, _THIN_THRESHOLD + 1)
    ] + [_raw_step("gave_up", failure_class="disk_full", attempt=99)]
    report = repair_stats_report([_loaded_run("r1", events=(_FAILED,), raw_steps=steps)])
    assert report["thin"] == ["disk_full"]


def test_every_count_map_is_ordered_by_key_for_a_deterministic_render():
    # House rule (cf. `cli.py:3732`): a renderer walking these maps must produce the
    # same output every time, so ordering is the module's job, not the caller's.
    steps = [
        _raw_step("gave_up", failure_class="oom", attempt=1),
        _raw_step("patched_and_retried", failure_class="tool_crash", attempt=2),
        _raw_step("approved_and_retried", failure_class="bad_param", attempt=3),
        _raw_step("stopped_for_confirmation", failure_class="unknown", attempt=4),
        _raw_step("advisory_acknowledged_and_retried", failure_class="disk_full", attempt=5),
    ]
    report = repair_stats_report([_loaded_run("r1", raw_steps=steps)])
    maps = [
        report["steps"]["by_family"],
        report["steps"]["by_failure_class"],
        report["steps"]["by_applied"],
        report["steps"]["by_attendance"],
        report["steps"]["legacy_derived_applied"],
        report["unmapped_outcomes"],
    ]
    for count_map in maps:
        assert list(count_map) == sorted(count_map)


# --- loading (AC-11's I/O half) ------------------------------------------------


def test_a_missing_runs_dir_has_no_runs_rather_than_raising():
    assert collect_runs(Path("/nonexistent/runs")) == []


def _write_run_bundle(
    runs_dir, run_id, *, raw_steps=(), events=(_COMPLETED,), drop_patch_applied=False
):
    """Write a real bundle, optionally stripped back to the pre-v0.49.0 shape.

    `model_dump_json` ALWAYS emits `patch_applied`, so a bundle written straight from
    the model can never be a legacy fixture. The post-write edit is the only way to
    produce a record that genuinely omits the key on disk.
    """
    loaded = _loaded_run(run_id, raw_steps=raw_steps, events=events)
    write_bundle(loaded.record, Path(runs_dir) / run_id)
    if drop_patch_applied:
        path = Path(runs_dir) / run_id / "run_record.json"
        data = json.loads(path.read_text())
        for step in data["repair_history"]:
            del step["patch_applied"]
        path.write_text(json.dumps(data, indent=2))


def test_every_bundled_run_under_the_dir_is_loaded(tmp_path):
    _write_run_bundle(tmp_path, "r2", raw_steps=[_raw_step("gave_up")], events=(_FAILED,))
    _write_run_bundle(tmp_path, "r1")
    loaded = collect_runs(tmp_path)
    assert [run.run_id for run in loaded] == ["r1", "r2"]
    assert loaded[1].record.repair_history[0].outcome == "gave_up"


def test_a_bundle_written_before_the_field_existed_loads_as_legacy(tmp_path):
    # The whole reason `collect_runs` reads each bundle twice: going through the model
    # alone would resurrect the key as `False` and silently reclassify this step.
    _write_run_bundle(
        tmp_path,
        "r1",
        raw_steps=[_raw_step("patched_and_retried")],
        drop_patch_applied=True,
    )
    [run] = collect_runs(tmp_path)
    assert "patch_applied" not in run.raw_steps[0]
    assert repair_stats_report([run])["steps"]["by_applied"]["legacy_derived"] == 1


def test_a_bundle_carrying_the_field_loads_it_as_read(tmp_path):
    _write_run_bundle(
        tmp_path,
        "r1",
        raw_steps=[_raw_step("patched_and_retried", patch_applied=True)],
    )
    [run] = collect_runs(tmp_path)
    assert run.raw_steps[0]["patch_applied"] is True
    assert repair_stats_report([run])["steps"]["by_applied"]["applied"] == 1


def test_a_bundle_that_fails_to_validate_is_skipped_not_raised(tmp_path):
    # A runs dir is user data. `load_corpus` may raise over one curated file, but one
    # unreadable bundle here must not blind the report to every other run.
    _write_run_bundle(tmp_path, "good")
    _write_run_bundle(tmp_path, "bad")
    (tmp_path / "bad" / "run_record.json").write_text('{"run_id": "bad"}')
    assert [run.run_id for run in collect_runs(tmp_path)] == ["good"]


def test_a_bundle_whose_json_omits_repair_history_loads_with_no_steps(tmp_path):
    # `repair_history` is a defaulted field, so a record written before it existed can
    # be absent from the JSON while still validating into an empty list on the model.
    _write_run_bundle(tmp_path, "r1")
    path = tmp_path / "r1" / "run_record.json"
    data = json.loads(path.read_text())
    del data["repair_history"]
    path.write_text(json.dumps(data))
    [run] = collect_runs(tmp_path)
    assert run.raw_steps == []

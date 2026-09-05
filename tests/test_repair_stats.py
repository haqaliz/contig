"""Tests for repair-success statistics over run records (stats-core).

The record under-determines two questions — was the patch enacted, and was a
human in the loop — so the classifiers answer in three states rather than
inventing a second. The second question now has a recorded answer for runs that
bundled a `launch.json` carrying `--auto-approve`; the third state survives for
the runs that did not record it. These tests pin the 19-literal taxonomy against
the shipped dashboard families and hold the three-state answers honest.
"""

import json
from pathlib import Path

from contig.bundle import write_bundle
from contig.corpus import _THIN_THRESHOLD as _CORPUS_THIN_THRESHOLD
from contig.models import ExecutionTarget, LaunchManifest, RepairStep, RunRecord, TaskEvent
from contig.workspace import load_launch_manifest
from contig.repair_stats import (
    LoadedRun,
    _THIN_THRESHOLD,
    ACKNOWLEDGED_OUTCOMES,
    APPLIED_OUTCOMES,
    GATED_OUTCOMES,
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
    # `ATTENDANCE_UNKNOWN_OUTCOMES` was renamed to `GATED_OUTCOMES` when attendance
    # became flag-derived: the set is the same KIND of thing (attendance literals the
    # taxonomy must know), so the subset semantics are unchanged and only the name and
    # the membership grew. Deliberate rename, not an expectation edited to fit output.
    assert (ATTENDED_OUTCOMES | GATED_OUTCOMES) <= _DOCUMENTED_LITERALS


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


def test_a_chosen_patch_is_attended():
    # Unlike `approved_and_retried`, `--auto-approve` can never produce this literal:
    # the `if auto_approve:` block (self_heal.py:1442) always `return`s (:1464-1468)
    # or `continue`s (:1469-1470) before the ambiguous-choice gate that assigns
    # `chose_and_retried` (:1497), which sits below it at :1472. So every
    # `chose_and_retried` step came from a human picking among ranked candidates.
    assert classify_attendance("chose_and_retried") == "attended"


def test_the_auto_approve_block_never_reaches_the_ambiguous_choice_gate():
    # Pins the reachability premise `test_a_chosen_patch_is_attended` relies on,
    # independent of the classifier: `if auto_approve:` (self_heal.py:1442) is
    # unconditionally terminal for the loop iteration (return or continue,
    # :1463-1470), and the ambiguous-choice gate that produces `chose_and_retried`
    # (:1472) sits below it, so the two branches can never both fire for one step.
    #
    # The exclusion now reads against `GATED_OUTCOMES` (renamed from
    # `ATTENDANCE_UNKNOWN_OUTCOMES`) and needs its reason restated, because the rename
    # changed what membership MEANS: `chose_and_retried` IS produced from a gated call
    # site (:1492), so it is excluded not for being ungated but for being
    # interactive-ONLY -- the flag has nothing to disambiguate about it.
    assert "chose_and_retried" not in GATED_OUTCOMES
    assert "chose_and_retried" in ATTENDED_OUTCOMES


def test_a_machine_only_outcome_is_unattended():
    assert classify_attendance("patched_and_retried") == "unattended"


def test_an_acknowledged_advisory_enacted_nothing_despite_its_suffix():
    # The tempting heuristic "the literal ends in _and_retried, so a patch ran" is
    # wrong exactly here: a human acknowledged guidance outside Contig and asked
    # the loop to retry; no patch was enacted (self_heal.py:1411-1423).
    assert derived_applied("advisory_acknowledged_and_retried") is False


# --- the attendance classifier reads the persisted flag (AC-5..AC-9, AC-15) -----
# `--auto-approve` is now persisted on the launch manifest (`models.py:443`) and
# carried onto `LoadedRun.auto_approve`, so the one question the record could not
# answer -- was a human in the loop -- has a recorded answer for runs that bundled
# one. These pin the derivation, not the plumbing.


def test_an_approved_step_under_a_recorded_auto_approve_is_unattended():
    # AC-5. The engine took the best-ranked gated fix on policy; no human approved
    # it, so the run stays eligible for the unattended-completion numerator.
    assert classify_attendance("approved_and_retried", auto_approve=True) == "unattended"


def test_an_approved_step_under_a_recorded_interactive_run_is_attended():
    # AC-6. `auto_approve=False` is a positive record that the approval gate was
    # interactive, so this literal can only have come from a human pressing approve.
    assert classify_attendance("approved_and_retried", auto_approve=False) == "attended"


def test_a_built_index_step_under_a_recorded_interactive_run_is_attended():
    # AC-7, the over-claim this slice exists to close. `built_index_and_retried` is
    # only reachable through `_apply_patch_and_maybe_build` (self_heal.py:1157), whose
    # only call sites are the three GATED ones (:1444, :1492, :1548). On an interactive
    # run a human had to approve that gate first, so scoring the step `unattended` --
    # which is what the pre-flag classifier did -- credited a human's approval to the
    # machine and inflated the gate metric in our own favour.
    assert classify_attendance("built_index_and_retried", auto_approve=False) == "attended"


def test_a_built_index_step_with_no_recorded_flag_is_attendance_unknown():
    # AC-8. A run bundled before the flag was persisted cannot say who opened the
    # gate, and the gated literal alone does not decide it, so the honest answer is
    # the third state rather than the pre-flag guess of `unattended`.
    assert classify_attendance("built_index_and_retried") == "attendance_unknown"


def test_an_approved_step_with_no_recorded_flag_is_attendance_unknown():
    # AC-8, the default-argument path stated directly: every pre-flag call site passes
    # one argument, and the ambiguity they relied on must survive unchanged.
    assert classify_attendance("approved_and_retried", auto_approve=None) == "attendance_unknown"
    assert classify_attendance("approved_and_retried") == "attendance_unknown"


def test_a_chosen_patch_stays_attended_under_every_flag_value():
    # AC-9. Phase 0's ruling -- `chose_and_retried` is strictly attended -- must not be
    # re-opened by the flag. It IS produced from a gated call site (self_heal.py:1497),
    # but only from the ambiguous-choice branch that `--auto-approve` returns or
    # continues past (:1463-1470), so no recorded flag value can make it machine work.
    for flag in (True, False, None):
        assert classify_attendance("chose_and_retried", auto_approve=flag) == "attended"


def test_an_interactive_only_literal_beats_a_contradicting_auto_approve_flag():
    # AC-15. A bundle claiming `auto_approve: true` while carrying an interactive-only
    # literal is impossible by construction, so one of the two is wrong. The LITERAL
    # wins, deliberately and asymmetrically: relabelling a human's rejection as
    # "unattended" would inflate the very gate metric this slice exists to make honest,
    # while the reverse error only understates it.
    for literal in ATTENDED_OUTCOMES:
        assert classify_attendance(literal, auto_approve=True) == "attended"

def test_every_gated_literal_is_read_from_the_flag_in_all_three_states():
    # Pins ALL SEVEN members of `GATED_OUTCOMES` by name. The list is written out
    # VERBATIM rather than iterated from the constant, deliberately: a test that reads
    # the set it is pinning passes just as happily over a shortened set, so deleting
    # a literal would silently restore the F2 over-claim that literal exists to close.
    # Five of these were previously pinned by nothing but a one-way subset assertion.
    gated = [
        "approved_and_retried",
        "built_index_and_retried",
        "index_build_failed",
        "index_unresolvable",
        "recompressed_reference_and_retried",
        "reference_recompress_failed",
        "reference_recompress_unresolvable",
    ]
    for literal in gated:
        # No recorded flag: the run cannot say who opened the gate.
        assert classify_attendance(literal, None) == "attendance_unknown"
        # `--auto-approve`: the engine took the gated fix on policy, nobody watching.
        assert classify_attendance(literal, True) == "unattended"
        # Interactive: a human had to approve the gate for this literal to exist, so
        # crediting it to the machine would inflate the unattended-completion rate.
        assert classify_attendance(literal, False) == "attended"


def test_every_attended_literal_is_attended_under_every_flag_value():
    # Pins ALL FIVE members of `ATTENDED_OUTCOMES` by name. The list is written out
    # VERBATIM rather than iterated from the constant, deliberately: a test that reads
    # the set it is pinning passes just as happily over a shortened set, so deleting
    # a literal would silently restore a hole in attendance classification that the
    # literal exists to close.
    attended = [
        "rejected_by_user",
        "approval_timed_out",
        "invalid_choice_rejected",
        "advisory_acknowledged_and_retried",
        "chose_and_retried",
    ]
    for literal in attended:
        # The literal alone is decisive: only a human can produce it, so no recorded
        # flag value -- not even a contradicting one -- can reclassify it (R5a).
        assert classify_attendance(literal, None) == "attended"
        assert classify_attendance(literal, True) == "attended"
        assert classify_attendance(literal, False) == "attended"


def test_a_machine_only_literal_is_unattended_under_every_flag_value():
    # The safe-patch path calls `apply_patch` directly (self_heal.py:1619) and records
    # `patched_and_retried` (:1643) without ever passing an approval gate, so the flag
    # has nothing to disambiguate here.
    for flag in (True, False, None):
        assert classify_attendance("patched_and_retried", auto_approve=flag) == "unattended"


def test_an_unmapped_literal_has_unknown_attendance_under_every_flag_value():
    # The taxonomy check stays first: a literal the map does not know is unknown on
    # this axis whatever the launch manifest recorded, because the flag says who was
    # at the keyboard, not what the outcome means.
    for flag in (True, False, None):
        assert classify_attendance("stopped_for_confirmation", auto_approve=flag) == "unknown"

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


def _loaded_run(run_id, *, raw_steps=(), events=(_COMPLETED,), auto_approve=None):
    """A `LoadedRun` fixture. `auto_approve` DEFAULTS to `None`, deliberately.

    `None` is the pre-flag shape -- a bundle with no `launch.json`, or one written
    before `LaunchManifest.auto_approve` existed -- so every fixture that does not
    care keeps exercising the ambiguous path it always exercised. A helper that
    defaulted to `False` would silently reclassify every gated step in this file as
    attended and make the flag-aware assertions pass without the flag being read.
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
    return LoadedRun(
        run_id=run_id, record=record, raw_steps=raw_steps, auto_approve=auto_approve
    )


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
    # The EXPECTATIONS below are unchanged; only this reason is, and deliberately so.
    # It used to say "the flag is not persisted", which is now false. What this run
    # actually shows is the narrower surviving case: `_loaded_run` leaves
    # `auto_approve=None`, i.e. a bundle that did not RECORD the flag, and for those
    # `approved_and_retried` is still reachable with or without a human, so counting
    # the run either way would be a guess.
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


# --- aggregation: the rate reads the persisted flag (AC-5, AC-6, AC-12) --------


def test_an_auto_approved_run_is_scored_as_an_unattended_completion():
    # AC-5 at the run level. With the flag recorded, the run that used to fall out of
    # BOTH sides of the rate is now a measurable unattended completion -- which is the
    # whole point of persisting the flag: the metric gates a roadmap phase, and a run
    # nobody touched is exactly what it is supposed to be counting.
    report = repair_stats_report(
        [_loaded_run("r1", raw_steps=[_raw_step("approved_and_retried")], auto_approve=True)]
    )
    assert report["runs"]["attendance_unknown"] == 0
    assert report["runs"]["rate_denominator"] == 1
    assert report["runs"]["unattended_completed"] == 1
    assert report["runs"]["unattended_completion_rate"] == 1.0


def test_an_interactive_run_is_scored_but_excluded_from_the_numerator():
    # AC-6. `auto_approve=False` makes the run measurable AND attended: it belongs in
    # the denominator, because we know the answer, but never in the numerator, because
    # a human pressed approve.
    report = repair_stats_report(
        [_loaded_run("r1", raw_steps=[_raw_step("approved_and_retried")], auto_approve=False)]
    )
    assert report["runs"]["attendance_unknown"] == 0
    assert report["runs"]["rate_denominator"] == 1
    assert report["runs"]["unattended_completed"] == 0
    assert report["runs"]["unattended_completion_rate"] == 0.0


def test_a_gated_machine_step_makes_an_interactive_run_attended():
    # AC-7 at the run level, and the reason the F2 over-claim mattered: this run
    # contains no obviously human literal at all, yet a human had to open the gate for
    # `built_index_and_retried` to exist. Before the flag it scored as an unattended
    # completion outright.
    report = repair_stats_report(
        [
            _loaded_run(
                "r1", raw_steps=[_raw_step("built_index_and_retried")], auto_approve=False
            )
        ]
    )
    assert report["runs"]["rate_denominator"] == 1
    assert report["runs"]["unattended_completed"] == 0


def test_a_human_step_still_wins_over_a_recorded_auto_approve_flag():
    # R8 under the flag: the any-step-wins contract is not weakened by the manifest.
    # `--auto-approve` skips the approval PROMPT, not every interaction, and a bundle
    # asserting both is contradictory anyway -- the literal is the harder evidence.
    steps = [
        _raw_step("rejected_by_user", attempt=1),
        _raw_step("approved_and_retried", attempt=2),
    ]
    report = repair_stats_report([_loaded_run("r1", raw_steps=steps, auto_approve=True)])
    assert report["runs"]["rate_denominator"] == 1
    assert report["runs"]["unattended_completed"] == 0


def test_the_attendance_axis_reads_the_flag_of_the_run_each_step_belongs_to():
    # The per-STEP axis is derived from the OWNING RUN's flag, not from a report-wide
    # setting: two runs in one report may disagree about the flag, and each step has to
    # be read against its own run's manifest.
    auto = _loaded_run(
        "auto", raw_steps=[_raw_step("approved_and_retried")], auto_approve=True
    )
    interactive = _loaded_run(
        "interactive", raw_steps=[_raw_step("approved_and_retried")], auto_approve=False
    )
    unrecorded = _loaded_run("legacy", raw_steps=[_raw_step("approved_and_retried")])
    report = repair_stats_report([auto, interactive, unrecorded])
    assert report["steps"]["by_attendance"] == {
        "attended": 1,
        "unattended": 1,
        "attendance_unknown": 1,
        "unknown": 0,
    }


def test_the_recorded_corpus_composition_reports_the_same_rate_as_before_the_flag():
    # AC-12. Stands in for the real corpus, which CI can never read: `/runs/` is
    # gitignored (`.gitignore:9`) and lives outside the repo. This fixture reproduces
    # its outcome composition exactly -- `patched_and_retried` x2, `gave_up` x4,
    # `stopped_for_confirmation` x1, plus one zero-event run -- so it answers the
    # question the real corpus would: does making attendance flag-derived move the
    # number we have already published? It must not. None of those literals is gated,
    # so no recorded flag value can touch them, and the rate is identical whether the
    # runs recorded the flag or not.
    def corpus(auto_approve):
        return [
            _loaded_run(
                "c1",
                raw_steps=[_raw_step("patched_and_retried", attempt=1)],
                auto_approve=auto_approve,
            ),
            _loaded_run(
                "c2",
                raw_steps=[_raw_step("patched_and_retried", attempt=1)],
                auto_approve=auto_approve,
            ),
            _loaded_run(
                "c3",
                events=(_FAILED,),
                raw_steps=[_raw_step("gave_up", attempt=n) for n in range(1, 5)],
                auto_approve=auto_approve,
            ),
            _loaded_run(
                "c4",
                raw_steps=[_raw_step("stopped_for_confirmation", attempt=1)],
                auto_approve=auto_approve,
            ),
            _loaded_run("c5", events=(), auto_approve=auto_approve),
        ]

    unrecorded = repair_stats_report(corpus(None))
    assert unrecorded["runs"]["rate_denominator"] == 4
    assert unrecorded["runs"]["unattended_completed"] == 3
    assert unrecorded["runs"]["unattended_completion_rate"] == 0.75
    for flag in (True, False):
        assert repair_stats_report(corpus(flag))["runs"] == unrecorded["runs"]

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
    # Expectations unchanged, and that is the assertion: this run records no flag
    # (`_loaded_run` defaults `auto_approve=None`), so making attendance flag-derived
    # must leave the pre-flag reading of an unrecorded run exactly where it was.
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


# --- auto_approve carriage (Phase 2, R3) ---------------------------------------


def _write_launch_manifest(runs_dir, run_id, *, auto_approve=None):
    """Write a real `launch.json` sidecar next to a bundled run.

    Mirrors `_write_run_bundle`'s "write the model, then edit the file on disk"
    shape where a raw/corrupt fixture is needed, but a `LaunchManifest` has no
    field whose presence-vs-value distinction matters here, so the model-written
    JSON is used directly.
    """
    manifest = LaunchManifest(
        run_id=run_id,
        pipeline="nf-core/rnaseq",
        revision="3.26.0",
        profiles=["docker"],
        backend="local",
        container_runtime="docker",
        auto_approve=auto_approve,
        created_at="2026-01-01T00:00:00+00:00",
    )
    (Path(runs_dir) / run_id / "launch.json").write_text(manifest.model_dump_json(indent=2))


def test_load_launch_manifest_is_none_when_no_launch_json_exists(tmp_path):
    _write_run_bundle(tmp_path, "r1")
    assert load_launch_manifest(tmp_path, "r1") is None


def test_load_launch_manifest_is_none_for_corrupt_json(tmp_path):
    _write_run_bundle(tmp_path, "r1")
    (tmp_path / "r1" / "launch.json").write_text("{not valid json")
    assert load_launch_manifest(tmp_path, "r1") is None


def test_load_launch_manifest_is_none_for_json_that_fails_validation(tmp_path):
    _write_run_bundle(tmp_path, "r1")
    (tmp_path / "r1" / "launch.json").write_text('{"run_id": "r1"}')
    assert load_launch_manifest(tmp_path, "r1") is None


def test_load_launch_manifest_returns_the_recorded_auto_approve_flag(tmp_path):
    _write_run_bundle(tmp_path, "r1")
    _write_launch_manifest(tmp_path, "r1", auto_approve=True)
    assert load_launch_manifest(tmp_path, "r1").auto_approve is True


def test_a_bundle_with_no_launch_manifest_has_auto_approve_unknown(tmp_path):
    _write_run_bundle(tmp_path, "r1")
    [run] = collect_runs(tmp_path)
    assert run.auto_approve is None


def test_a_bundle_with_a_launch_manifest_carries_its_auto_approve_flag(tmp_path):
    _write_run_bundle(tmp_path, "r1")
    _write_launch_manifest(tmp_path, "r1", auto_approve=True)
    [run] = collect_runs(tmp_path)
    assert run.auto_approve is True

def test_a_recorded_interactive_run_carries_false_rather_than_none(tmp_path):
    # `False` end to end -- launch.json on disk -> `load_launch_manifest` ->
    # `collect_runs` -> `LoadedRun.auto_approve`. Pinned separately from the `True`
    # case because it is the value at risk: `False` and `None` are both falsey, so any
    # truthiness shortcut anywhere on this path (`manifest.auto_approve or None`, a
    # `if manifest.auto_approve:` guard) would flatten a positively recorded
    # interactive run into "did not record it" and quietly drop it from the rate's
    # denominator. `is False` is asserted, not `== False`, so `None` cannot satisfy it.
    _write_run_bundle(tmp_path, "r1")
    _write_launch_manifest(tmp_path, "r1", auto_approve=False)
    [run] = collect_runs(tmp_path)
    assert run.auto_approve is False



def test_a_corrupt_launch_manifest_does_not_blind_the_report_to_the_run(tmp_path):
    # Unlike a corrupt run_record.json (which skips the whole run), a corrupt
    # launch.json only costs the one derived fact -- the run itself still loads.
    _write_run_bundle(tmp_path, "r1")
    (tmp_path / "r1" / "launch.json").write_text("{not valid json")
    [run] = collect_runs(tmp_path)
    assert run.run_id == "r1"
    assert run.auto_approve is None


def test_a_bundled_run_with_a_recorded_flag_is_scored_from_disk(tmp_path):
    # The wiring end to end: bundle -> `collect_runs` -> report. Every hop is unit-pinned
    # above, but nothing yet proved they are connected, and a `LoadedRun` built by hand
    # in a fixture cannot show that `collect_runs` actually puts the manifest's value
    # where `classify_attendance` reads it.
    _write_run_bundle(tmp_path, "r1", raw_steps=[_raw_step("approved_and_retried")])
    _write_launch_manifest(tmp_path, "r1", auto_approve=True)
    report = repair_stats_report(collect_runs(tmp_path))
    assert report["runs"]["rate_denominator"] == 1
    assert report["runs"]["unattended_completed"] == 1

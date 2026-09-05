"""Tests for repair-success statistics over run records (stats-core).

The record under-determines two questions — was the patch enacted, and was a
human in the loop — so the classifiers answer in three states rather than
inventing a second. These tests pin the 19-literal taxonomy against the shipped
dashboard families and hold the three-state answers honest.
"""

from contig.corpus import _THIN_THRESHOLD as _CORPUS_THIN_THRESHOLD
from contig.repair_stats import (
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
    derived_applied,
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


def test_an_unmapped_literal_is_unknown_even_when_the_field_is_recorded():
    # Key presence does not rescue a literal the taxonomy does not know: if the
    # map is out of date, nothing about the step is reported confidently.
    unmapped_step = {"outcome": "stopped_for_confirmation", "patch_applied": True}
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

"""Repair-success statistics over run records.

The record under-determines two questions and this module answers both in three
states rather than inventing a second:

1. *Was the patch enacted?* `RepairStep.patch_applied` is `bool = False`
   (`models.py:322`), so a record written before the field existed validates with
   `False` and is indistinguishable, on the model, from one that genuinely
   recorded `False`.
2. *Was a human in the loop?* `auto_approve` is a CLI flag that is never
   persisted on `RunRecord`, so `approved_and_retried` may be a human approval or
   a policy decision under `--auto-approve`.

**Why a hand-maintained derived map is acceptable here, when
`CHANGELOG.md:869-876` rejected one.** That rejection was for the *model field*:
a derived `outcome -> applied` map would have to stay correct for every literal
added at a recording site in the future, and a new literal would silently default
to "not applied" — wrong by construction rather than by review. The map below
answers a different question: what a **pre-v0.49.0** record, written before
`patch_applied` existed, must have meant. That record set is **frozen** — no new
record can ever land in it — so unlike the live outcome vocabulary this map
cannot rot. Records that carry the key are read from the field and never touched
by the map at all.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from contig.models import RunRecord, RunSummary
from contig.workspace import bundle_dir_for, list_run_ids, load_run

# The five families, mirroring the shipped dashboard taxonomy 1:1
# (`dashboard/components/run/repair-timeline.tsx:86-192`). 19 literals; the
# equivalence "applied <=> APPLIED family" holds only because that taxonomy split
# ACKNOWLEDGED and FLAGGED out of APPLIED, so it is pinned by a test.

APPLIED_OUTCOMES: frozenset[str] = frozenset(
    {
        "patched_and_retried",
        "approved_and_retried",
        "chose_and_retried",
        "built_index_and_retried",
        "recompressed_reference_and_retried",
        "installed_and_retried",
        # The install ran, so the fix WAS enacted; the retry then failed anyway.
        # The family means "enacted", not "worked".
        "retry_failed",
    }
)

DECLINED_OUTCOMES: frozenset[str] = frozenset(
    {
        "rejected_by_user",
        "approval_timed_out",
        "invalid_choice_rejected",
    }
)

GAVE_UP_OUTCOMES: frozenset[str] = frozenset(
    {
        "gave_up",
        "gave_up_at_ceiling",
        "index_build_failed",
        "index_unresolvable",
        "reference_recompress_failed",
        "reference_recompress_unresolvable",
        "install_failed",
    }
)

FLAGGED_OUTCOMES: frozenset[str] = frozenset({"qc_verdict_flagged"})

ACKNOWLEDGED_OUTCOMES: frozenset[str] = frozenset({"advisory_acknowledged_and_retried"})

# Attendance is a separate axis from the family (PRD Addendum 2). These are the
# outcomes that only a human can produce: a rejection, a lapsed approval window, a
# choice outside the offered options, and an advisory a human acknowledged.
ATTENDED_OUTCOMES: frozenset[str] = frozenset(
    {
        "rejected_by_user",
        "approval_timed_out",
        "invalid_choice_rejected",
        "advisory_acknowledged_and_retried",
    }
)

# Under-determined, and deliberately not guessed: both literals fire on a real human
# approval AND under `--auto-approve`, where the engine decides per policy and no
# human is involved. `auto_approve` is a CLI flag that is never persisted on
# `RunRecord`, so the record cannot tell the two apart.
ATTENDANCE_UNKNOWN_OUTCOMES: frozenset[str] = frozenset(
    {
        "approved_and_retried",
        "chose_and_retried",
    }
)

# Derived from the family sets above, never hand-written a second time: a literal
# can only be in one family, so the map cannot disagree with the sets it came from.
OUTCOME_FAMILY: dict[str, str] = {
    literal: family
    for family, literals in (
        ("applied", APPLIED_OUTCOMES),
        ("declined", DECLINED_OUTCOMES),
        ("gave_up", GAVE_UP_OUTCOMES),
        ("flagged", FLAGGED_OUTCOMES),
        ("acknowledged", ACKNOWLEDGED_OUTCOMES),
    )
    for literal in literals
}


# Fewer than this many steps in a failure class is too thin to read a rate from.
# Mirrors the corpus coverage threshold (`corpus.py:279`) so the two surfaces call
# the same amount of data thin.
_THIN_THRESHOLD = 3


def derived_applied(outcome: str) -> bool | None:
    """Whether a legacy step with this outcome enacted its patch.

    For a record written before `patch_applied` existed, family membership is the
    only evidence: APPLIED means enacted, every other family means it was not.
    `None` for a literal outside the map — an unmapped outcome is unknown, and
    must not be derived or folded into a family it does not belong to.
    """
    family = OUTCOME_FAMILY.get(outcome)
    if family is None:
        return None
    return family == "applied"



def classify_applied(outcome: str, raw_step: dict) -> str:
    """Whether this step enacted its patch: applied / not_applied / legacy_derived.

    Takes the **raw JSON dict** alongside the outcome, deliberately, and this is
    the only place in the codebase that reads a step twice. `RepairStep` declares
    `patch_applied: bool = False` (`models.py:322`), not `bool | None`, so pydantic
    fills `False` for a record written before the field existed: on the validated
    model an absent key and an explicit `False` are the same value. The raw dict is
    the only source of key presence, and therefore the only way to tell "we did not
    record this" from "we recorded that nothing was enacted".

    An outcome the taxonomy does not know is `unknown` on this axis whether or not
    the key is present: an out-of-date map is not a basis for a confident answer,
    and the unmapped literal is surfaced in its own bucket instead.
    """
    if outcome not in OUTCOME_FAMILY:
        return "unknown"
    if "patch_applied" not in raw_step:
        return "legacy_derived"
    return "applied" if raw_step["patch_applied"] else "not_applied"


def classify_attendance(outcome: str) -> str:
    """Whether a human was in the loop for this step.

    Three states, because the record under-determines the answer for two literals:
    `approved_and_retried` and `chose_and_retried` fire both on a real approval and
    under `--auto-approve`, and the flag is never persisted. Those are
    `attendance_unknown` rather than a guess in either direction.
    """
    if outcome not in OUTCOME_FAMILY:
        return "unknown"
    if outcome in ATTENDANCE_UNKNOWN_OUTCOMES:
        return "attendance_unknown"
    if outcome in ATTENDED_OUTCOMES:
        return "attended"
    return "unattended"


@dataclass(frozen=True)
class LoadedRun:
    """One run as the stats need it: the validated model AND its raw step dicts.

    Both halves come from the same `run_record.json`. The model is what every other
    caller uses; `raw_steps` exists only because key presence is invisible on the
    model (see `classify_applied`).
    """

    run_id: str
    record: RunRecord
    raw_steps: list[dict]


def _bump(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def _run_is_attended(run: LoadedRun) -> bool:
    """Whether a human was in the loop for ANY step of this run.

    Not last-step-wins: a human who rejected attempt 1 was in the loop for the run,
    whatever the machine did afterwards.
    """
    return any(
        classify_attendance(step.outcome) == "attended"
        for step in run.record.repair_history
    )


def _run_attendance_is_unknown(run: LoadedRun) -> bool:
    return any(
        classify_attendance(step.outcome) == "attendance_unknown"
        for step in run.record.repair_history
    )


def repair_stats_report(runs: list[LoadedRun]) -> dict:
    """Per-step and per-run repair statistics, as a plain dict.

    Mirrors `corpus.py:291 coverage_report`: pure, deterministic, and rendered by
    somebody else. Two axes are counted per **step** (which family the outcome is in,
    what its failure class was) and the completion rate is computed per **run**.

    The rate is deliberately narrow. A run is scored only when the record can actually
    answer both questions the rate asks:

    - A zero-event run is `not_analyzable`. It derives `succeeded=True` vacuously
      (`models.py:156-158`: `succeeded = failed_tasks == 0`), so scoring it would
      invent a completion out of an absence of evidence.
    - A run with any `attendance_unknown` step cannot be placed on the attended axis
      at all, so it is excluded rather than guessed in either direction.

    Both sit outside numerator AND denominator, and the rate is `None` — never `0.0` —
    when nothing is left to divide by. Completion comes from
    `RunSummary.from_events`, never `RunRecord.verdict`, which is a QC judgement and
    not a statement about whether the run finished.
    """
    by_applied = {"applied": 0, "not_applied": 0, "legacy_derived": 0, "unknown": 0}
    by_attendance = {
        "attended": 0,
        "unattended": 0,
        "attendance_unknown": 0,
        "unknown": 0,
    }
    legacy_derived_applied = {"applied": 0, "not_applied": 0}
    by_family: dict[str, int] = {}
    by_failure_class: dict[str, int] = {}
    unmapped_outcomes: dict[str, int] = {}
    total_steps = 0

    for run in runs:
        # strict: both halves come from the same JSON array, so a length mismatch is
        # corruption rather than a shape worth tolerating silently.
        for step, raw in zip(run.record.repair_history, run.raw_steps, strict=True):
            total_steps += 1
            applied_state = classify_applied(step.outcome, raw)
            by_applied[applied_state] += 1
            if applied_state == "legacy_derived":
                # Kept apart from `by_applied` on purpose: this is inference over a
                # frozen record set, not something the record says, so a reader must
                # be able to discard every derived number without touching the rest.
                derived = "applied" if derived_applied(step.outcome) else "not_applied"
                legacy_derived_applied[derived] += 1
            by_attendance[classify_attendance(step.outcome)] += 1
            _bump(by_failure_class, step.diagnosis.failure_class)
            family = OUTCOME_FAMILY.get(step.outcome)
            if family is None:
                # Surfaced by name rather than folded into a family it may not belong
                # to: an out-of-date map is a finding, not a rounding error.
                _bump(unmapped_outcomes, step.outcome)
            else:
                _bump(by_family, family)

    analyzable = [run for run in runs if run.record.events]
    scorable = [run for run in analyzable if not _run_attendance_is_unknown(run)]
    unattended_completed = sum(
        1
        for run in scorable
        if RunSummary.from_events(run.record.events).succeeded
        and not _run_is_attended(run)
    )
    rate_denominator = len(scorable)

    return {
        "runs": {
            "total": len(runs),
            "analyzable": len(analyzable),
            "not_analyzable": len(runs) - len(analyzable),
            "attendance_unknown": len(analyzable) - len(scorable),
            "rate_denominator": rate_denominator,
            "unattended_completed": unattended_completed,
            "unattended_completion_rate": (
                unattended_completed / rate_denominator if rate_denominator else None
            ),
        },
        "steps": {
            "total": total_steps,
            "by_family": dict(sorted(by_family.items())),
            "by_failure_class": dict(sorted(by_failure_class.items())),
            "by_applied": dict(sorted(by_applied.items())),
            "by_attendance": dict(sorted(by_attendance.items())),
            "legacy_derived_applied": dict(sorted(legacy_derived_applied.items())),
        },
        "thin": sorted(
            cls for cls, count in by_failure_class.items() if count < _THIN_THRESHOLD
        ),
        "unmapped_outcomes": dict(sorted(unmapped_outcomes.items())),
    }


def collect_runs(runs_dir: str | Path) -> list[LoadedRun]:
    """Load every bundled run under `runs_dir` as a `LoadedRun`.

    Reads each bundle TWICE, deliberately: once through `load_run` for the validated
    model, and once as raw JSON for `repair_history`. `RepairStep.patch_applied` is
    `bool = False` (`models.py:322`), so on the model an absent key and an explicit
    `False` are the same value — the raw dicts are the only evidence of key presence
    and therefore the only way to tell a pre-v0.49.0 record from one that recorded
    nothing was enacted.

    A missing runs directory simply has no runs (`workspace.list_run_ids`).
    """
    runs: list[LoadedRun] = []
    for run_id in list_run_ids(runs_dir):
        record_path = bundle_dir_for(runs_dir, run_id) / "run_record.json"
        try:
            record = load_run(runs_dir, run_id)
            raw = json.loads(record_path.read_text())
        # pydantic's ValidationError and json's JSONDecodeError are both
        # ValueError; OSError covers an unreadable file.
        except (ValueError, OSError):
            # Skipped, not raised: a runs dir is user data, and one bundle that will
            # not load must not blind the report to every other run in it. (Defensive
            # — every record in the real corpus loads cleanly today.)
            continue
        runs.append(
            LoadedRun(
                run_id=run_id,
                record=record,
                raw_steps=raw.get("repair_history", []),
            )
        )
    return runs

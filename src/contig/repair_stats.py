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


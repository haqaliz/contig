# Aspect spec — `stats-core`

The pure half: the outcome taxonomy, the two three-state classifiers, and the aggregation
over a runs directory. No Typer, no rendering, no I/O beyond reading the bundle files.

## Problem slice

Everything subtle in this feature lives here. The record **under-determines** two
questions, and the core's whole job is to answer them in three states instead of
inventing a second:

1. *Was the patch enacted?* — `patch_applied` is `bool = False` (`models.py:322`), so
   pydantic cannot distinguish an absent key from an explicit `False`.
2. *Was a human in the loop?* — `auto_approve` is never persisted (the only such field is
   `HealScenario.auto_approve`, `models.py:569`), so `approved_and_retried` is ambiguous.

## In scope

- **New module `src/contig/repair_stats.py`.** `corpus.py` is the wrong home — it operates
  on `FailureCase` corpora (`corpus.py:40,107,247,291`), not `RunRecord`s.
- **The literal tables**, as module constants, exactly mirroring the shipped dashboard
  (`dashboard/components/run/repair-timeline.tsx:86-192`), 19 literals over five families:
  `APPLIED` (7), `DECLINED` (3), `GAVE_UP` (7), `FLAGGED` (1), `ACKNOWLEDGED` (1).
- **`applied` classifier (three-state)** — `applied` / `not_applied` / `legacy_derived`.
  Requires **raw-JSON key presence**, so the core takes the raw step dicts alongside the
  validated model. For a legacy step, derive from family membership; PRD Addendum A
  verified the equivalence **applied ⟺ APPLIED-family**.
- **`attendance` classifier (three-state)** — `attended` / `attendance_unknown` /
  `unattended`, per PRD Addendum 2's table. `approved_and_retried` and
  `chose_and_retried` are `attendance_unknown`.
- **Unknown bucket** for unmapped literals (`stopped_for_confirmation`): neither derived
  nor folded into `GAVE_UP`.
- **Aggregation** returning a plain `dict`, mirroring `corpus.py:291 coverage_report`:
  per-family and per-failure-class counts **per step**; the unattended-completion rate
  **per run**; `not_analyzable` and `attendance_unknown` run buckets; a `thin` list.
- **Run-level rules**: analyzable ⟺ `len(record.events) > 0`; completion signal is
  `RunSummary.from_events(record.events).succeeded` (`models.py:156-158`), mirroring
  `heal.py:249-252`; a run is attended if **any** step is attended (not last-step-wins);
  failure class from `step.diagnosis.failure_class`, never `step.failure_class`.

## Out of scope

- Any Typer command, rendering, or `--json` (that is `cli-surface`).
- Any change to `models.py`, the signed payload, or `patch_applied`'s default.
- Persisting `auto_approve` (filed as a follow-on in the PRD).
- Trend/snapshot history.

## Acceptance criteria (testable) — `tests/test_repair_stats.py`

1. A step whose raw JSON **omits** `patch_applied`, outcome `patched_and_retried` →
   `legacy_derived` with derived applied = true. **Not** `not_applied`.
2. A step **carrying** `patch_applied: false` → `not_applied`, distinct from (1).
   *The anti-regression pin for R1.*
3. A step carrying `patch_applied: true` → `applied`.
4. `stopped_for_confirmation` → family `unknown`, applied `unknown`, attendance
   `unknown`; never `GAVE_UP`, never derived.
5. `approved_and_retried` → `attendance_unknown`; a succeeded run whose only step is
   `approved_and_retried` is in **neither** the numerator nor the denominator of the rate.
   *Pin for PRD Addendum 2.*
6. `advisory_acknowledged_and_retried` → `attended` **and** not applied — it ends in
   `_and_retried` but enacts nothing (`self_heal.py:1411-1423`).
7. A zero-event run → `not_analyzable`, excluded from both sides of the rate.
8. A 2-step run (`patched_and_retried`, then `gave_up`) contributes **two** rows to the
   per-family counts and **one** run to the rate. *Pin for the per-step/per-run split.*
9. **Family-map enumeration pin**: the union of the five family constants equals the
   documented 19-literal set, and the sets are pairwise disjoint. Fails loudly if a
   literal is added to two families or dropped.
10. **Equivalence pin**: for every literal in the map, `derived_applied` is true ⟺ the
    literal is in `APPLIED`. Reddens if a future literal joins `APPLIED` with
    `patch_applied=False`.
11. Empty runs dir → an empty report, not a division-by-zero or a `0%`.

## Dependencies and sequencing

None — this aspect is first and standalone. `cli-surface` depends on it.

## Risks specific to this aspect

- **Reading the same file twice** (validated model + raw dict) is unusual for this
  codebase and will look like a mistake to a reviewer. Comment the reason at the site.
- The derived map is a hand-maintained mapping — the exact thing `CHANGELOG.md:869-876`
  rejected for the *model field*. It is acceptable here only because the legacy record set
  is **frozen**; state that reasoning in the module docstring, or the next reader will
  reasonably object.
- Fixtures must set `patch_applied` **explicitly** where they mean it, and **omit the key
  entirely** where they mean legacy. An omitted key in a fixture that meant `false` makes
  test (2) pass vacuously — the same RISK-5 the dashboard-repair-surface spec flagged.

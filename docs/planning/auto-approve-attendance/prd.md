# PRD — `auto-approve-attendance`

**Status:** for review. **Slug:** `auto-approve-attendance`. **Owner:** aliz.
**Branch:** `feat/auto-approve-attendance/aliz`.
**Inputs:** `docs/planning/_card/issue.md` (brief), `understanding.md` (Phase-2 dig).
**Follow-on to:** `repair-success-analytics` (v0.57.0), which filed this gap against
itself at `CHANGELOG.md:82-86`.

---

## Problem Statement

`contig repair-stats` computes the unattended-completion rate that gates Phase 1 → 2
(`docs/ROADMAP.md:109`, "≥70% unattended completion on the core pipeline"). It cannot
determine whether a human was in the loop, because `--auto-approve` (`cli.py:414`) is
threaded into the engine (`cli.py:815` → `self_heal.py:1177`) and **persisted nowhere**.

Two consequences, and the second is the serious one:

1. **Ambiguity.** `approved_and_retried` is recorded at two mutually exclusive sites —
   `self_heal.py:1449` (auto-approve only) and `self_heal.py:1553` (interactive only,
   gated on a human `decision == "approve"`). The record cannot tell them apart, so
   `repair_stats.py:92-97` files it as `attendance_unknown`, excluding the run from
   **both** sides of the rate (`repair_stats.py:274-282`).

2. **A silent over-claim in our own favour.** `_apply_patch_and_maybe_build` discards its
   `default_outcome` for index-build and recompress patches and returns its own
   (`self_heal.py:1085-1088`, `:1157`). A human who approves a gated index build therefore
   records `built_index_and_retried`, which falls to the else branch of
   `classify_attendance` (`repair_stats.py:177`) and is classified **`unattended`** —
   counting an attended run in the **numerator** of the gate metric.

**Evidence it is real, stated against our own interest.** The corpus contains **zero**
`approved_and_retried` steps today (only `patched_and_retried` ×2, `gave_up` ×4,
`stopped_for_confirmation` ×1 across 15 bundles), so `attendance_unknown` is **0** and
problem (1) has never once fired in the field. The card's "empty the bucket" framing
overstates it: this **stops a currently-empty bucket from ever filling**, and fixes an
over-claim (2) that is latent rather than observed. Push, not demand-pull — no design
partner asked.

## Goals & Success Metrics

- **G1.** A run recorded after this slice answers "was a human in the loop?" from its own
  bundle, with no inference.
- **G2.** The over-claim in problem (2) is closed: a human-approved index build is never
  counted as an unattended completion.
- **G3.** Legacy bundles are never *guessed* into a state they do not assert.

**Measured by:** `contig repair-stats` over a fixture corpus resolves attendance for every
gated literal when the fact is present, and reports `attendance_unknown` when it is not.
**Not measured by:** any movement in the real corpus's 64.3% — see NG1.

**Non-goal metric (NG1).** The reported rate **will not move**. All 15 real bundles predate
`LaunchManifest` (introduced `a4b4b66`, 2026-06-22; bundles dated 2026-06-21..23) and carry
no `launch.json` at all — verified by `find`, 0 hits. Any writeup claiming this improves the
gate number is false.

## Users & Scenarios

Not an end-user feature. The consumer is the **founder reading `contig repair-stats`** to
decide whether the Phase-2 gate is met, and any future reader of a run bundle asking
whether a result was produced with a human in the loop — a provenance question, which is
on-thesis for the reproduce layer.

## Requirements

### Must-have

- **R1 — Persist the fact on `LaunchManifest`.** Add `auto_approve: bool | None = None`
  to `LaunchManifest` (`models.py:411-447`), set at `cli.py:769-787` from the
  `auto_approve` value already in scope 25 lines below at `cli.py:815`.
  - **`bool | None`, not `bool`.** A plain `bool = False` makes pydantic resurrect an
    absent key as `False`, so every legacy bundle would silently read as "a human was
    there" — emptying the bucket by **fiction**. That is exactly the `patch_applied`
    defect (`models.py:317-322`), whose cost `repair_stats` still pays as the only
    double-read in the codebase (`repair_stats.py:138-147`, `:313-318`).
  - **A dividend of that choice:** because absent → `None` on the validated model, this
    slice needs **no raw-JSON key-presence read**. The `patch_applied` lesson is applied,
    not repeated.
  - Precedent for the tri-state: `HealScenario.expected_patch_applied` (`models.py:602-605`).
- **R2 — Write-only provenance; never replayed.** The field must not be added to the
  replay mappings at `cli.py:878-901` (rerun) or `cli.py:2548-2571` (resume). Precedent:
  `harmonized_reference` (`models.py:436`, written `cli.py:785`, read by no replay path).
  The docstring must say so in the `models.py:433-434` voice, because replay is a
  hand-written per-field mapping and the failure mode is a future editor adding the line
  out of symmetry — the way `assay` was wired into `rerun` (`cli.py:881`) but forgotten in
  `resume`.
- **R3 — A tolerant loader.** Read `bundle_dir_for(runs_dir, run_id) / "launch.json"` —
  already the correct path, already computed at `repair_stats.py:325`. A missing,
  unreadable, or invalid manifest yields `None`, never an exception, matching
  `collect_runs`'s skip-don't-raise posture (`repair_stats.py:329-335`). Carried on
  `LoadedRun` (`repair_stats.py:180-191`) as a **defaulted** field — the dataclass is
  frozen and 20+ aggregation tests construct it (`tests/test_repair_stats.py:245-256`).
- **R4 — Correct `chose_and_retried` to strictly attended.** It is **unreachable** under
  `--auto-approve`: the `if auto_approve:` block at `self_heal.py:1442` always returns
  (`:1466-1471`) or `continue`s (`:1469-1470`) before the ambiguous-choice gate at
  `:1472`, as `self_heal.py:1440-1441` states outright. Move it from
  `ATTENDANCE_UNKNOWN_OUTCOMES` to `ATTENDED_OUTCOMES` and correct the now-false comment
  at `repair_stats.py:88-91`. **Independent of persistence** — a real defect in shipped
  output either way. The predecessor PRD carries the same error
  (`docs/planning/repair-success-analytics/prd.md:344`) and must be annotated, not
  silently contradicted.
- **R5 — Attendance derives from the flag for every gated literal.** The gated set is
  provable, not guessed: `_apply_patch_and_maybe_build` has **exactly three call sites**
  (`self_heal.py:1444`, `:1492`, `:1548`), all behind a gate; the safe path calls
  `apply_patch` directly (`:1618`) and records `patched_and_retried` (`:1643`). So
  `built_index_and_retried`, `index_build_failed`, `index_unresolvable`,
  `recompressed_reference_and_retried`, `reference_recompress_failed`,
  `reference_recompress_unresolvable` and `approved_and_retried` occur **only** on the
  gated path, and the run-level flag disambiguates each of them **completely**:
  - `auto_approve is True` → the machine decided → **unattended**.
  - `auto_approve is False` → a human decided → **attended**.
  - `auto_approve is None` (not recorded) → **`attendance_unknown`**.
- **R5a — Precedence on a contradictory bundle: the literal wins.**
  `rejected_by_user`, `approval_timed_out`, `invalid_choice_rejected`,
  `advisory_acknowledged_and_retried` and `chose_and_retried` are **interactive-only** —
  unreachable when `auto_approve is True`, because the poll never runs and an advisory
  `gave_up`s instead (`self_heal.py:1379-1394`). A bundle carrying `auto_approve: true`
  **and** one of them is therefore impossible-by-construction: corrupt, hand-edited, or
  evidence the engine changed. The rule is that **the step literal wins and the run is
  attended**, mirroring `repair_stats.py:156-157`, where a recorded fact outranks a
  derivation. Rationale: the failure directions are not symmetric — relabelling a human's
  rejection as "unattended" inflates the gate metric in our own favour, which is the exact
  error class this slice exists to close. Pinned by a test, not left to whichever branch
  happens to evaluate first.
- **R6 — Legacy honesty, and its cost stated.** Under `None`, gated literals that today
  classify `unattended` (the `built_index_*` / recompress family) become
  `attendance_unknown`. This **widens** the unknown bucket for legacy bundles, which is
  the honest reading — we do not know who approved them. It is **provably a no-op on the
  real corpus**: zero of the 15 bundles contain any gated literal (verified by counting
  `repair_history` outcomes). The claim must be pinned by a test, not asserted in prose.
- **R6a — `attendance_unknown` now has two distinct causes; name them.** After R6 the
  bucket holds both "the run recorded no flag" (legacy) and, previously, "the literal was
  ambiguous". A reader cannot tell them apart from a single count. The CLI line must
  attribute the cause rather than merge them, on the `repair_stats.py:1-24` precedent of
  stating *why* a state is unknown instead of only that it is.
- **R7 — Correct the CLI string.** `cli.py:3787-3788` reads *"(a human, or
  `--auto-approve`, which is never recorded)"*. That becomes **factually false** and must
  change. The `attendance_unknown` line itself stays — the bucket still exists, for
  bundles that did not record the fact.
- **R8 — Preserve `_run_is_attended`'s any-step-wins contract** (`repair_stats.py:198-207`,
  pinned by `tests/test_repair_stats.py:293-302`). A human who intervened once was in the
  loop for the run, whatever the machine did after.

### Should-have

- **R9 — Pin the resume overwrite as reasoned, not accidental.** `resume` re-enters
  `_dispatch_run` with the same run id (`cli.py:2549`) and rewrites
  `runs/<id>/launch.json` (`cli.py:788-790`) with `auto_approve` falling to
  `_dispatch_run`'s default `False` (`cli.py:542`), because neither `rerun`
  (`cli.py:836-843`) nor `resume` (`cli.py:2508-2514`) accepts the flag. This is
  **self-consistent** — the resume regenerates the `RunRecord` too, so manifest and record
  both describe the last invocation — and deserves a test rather than a footnote.

### Nice-to-have (explicitly deferred)

- Adding `--auto-approve` to `rerun`/`resume`. The D4 precedent (`CHANGELOG.md:1286-1291`)
  says a runtime-only knob is passed per invocation; and a rerun recording `false` is
  **true**, not a gap.
- A `repair-stats` dashboard card or `--snapshot`/`--history` trend — deferred with a
  stated reason at `CHANGELOG.md:86-90` (it reads a mutable runs dir, so a trend point is
  not reproducible from committed data).

## Technical Considerations

**Why `LaunchManifest` and not `RunRecord`.** The card framed these as a balanced trade;
the dig showed they are not.

| | `LaunchManifest` | `RunRecord` |
|---|---|---|
| Signing cost | **Zero** — absent from `signing.py`, `bundle.py`, and the attested payload list (`bundle.py:104-113`) | **Fifth disclosed break, widest class** |
| Blast radius | none | **100% of signed bundles** |
| Precedent | `harmonized_reference` (`models.py:436`) | `sex_inference` (`models.py:359-363`) |

`canonical_record_bytes` is a full `record.model_dump(mode="json")` with no exclusions
(`signing.py:63-64`), so a **top-level** `RunRecord` field is emitted for every record —
none of the empty-list narrowing that made the `patch_applied` break defensible
(`CHANGELOG.md:1002-1004`), and the `exclude_none` fix is explicitly foreclosed
(`CHANGELOG.md:1606-1609`). The D4 counter-precedent argues against persisting
*host-dependent* knobs; `auto_approve` is a property of how the run was **decided**, the
same category as `allow_reference_mismatch` ("faithful to the original's intent",
`models.py:433`).

**Reproducibility impact.** None to the signed surface: no model change to `RunRecord`, no
canonical-payload change, **no signature break**. The reproduce/replay contract is
unchanged by construction (R2).

**Change surface.** CLI + Python tests only. No dashboard file references attendance or
the unattended rate; the dashboard consumes the outcome *taxonomy*
(`dashboard/components/run/repair-timeline.tsx:86-192`), which this slice does not alter.

**Tests that must change deliberately (6, the complete set):**
`tests/test_repair_stats.py:147` (`approved_and_retried` → `attendance_unknown`), `:174-207`
(whole-report dict equality), `:305-314`, `:395-408` (`by_attendance` equality);
`tests/test_cli_repair_stats.py:116-124` (the sole `%` line), `:142-152` (the "never
recorded" string).

**Invariants that must be preserved:** missing runs dir → `[]`
(`tests/test_repair_stats.py:470`); corrupt bundle → skipped, not raised (`:526`); every
existing fixture writes only `run_record.json` and no `launch.json`
(`tests/test_repair_stats.py:474-490`, `tests/test_cli_repair_stats.py:50-73`), so a
missing manifest **must** mean unknown.

## Acceptance Criteria (test-first)

1. A `LaunchManifest` round-trips `auto_approve` `True` / `False` / absent-as-`None`.
2. A pre-slice `launch.json` with no `auto_approve` key validates and yields `None` — not
   `False`.
3. `contig run --auto-approve` writes `auto_approve: true`; without it, `false`.
4. Neither `rerun` nor `resume` passes the field into `_dispatch_run` — asserted against
   the replay call sites, so a future editor adding it turns this test red.
5. A run with `auto_approve=True` and an `approved_and_retried` step is **unattended** and
   counted in the rate.
6. The same run with `auto_approve=False` is **attended** and excluded from the numerator.
7. A run with `auto_approve=False` and a `built_index_and_retried` step is **attended** —
   the R5/problem-(2) fix; it fails on today's code.
8. The same run with `auto_approve=None` is `attendance_unknown` (R6).
9. `classify_attendance("chose_and_retried") == "attended"` regardless of the flag (R4).
10. A bundle with **no** `launch.json` yields `None` and reproduces today's attendance for
    non-gated literals exactly.
11. A corrupt/unreadable `launch.json` yields `None` rather than raising, and does not
    blind the report for other runs.
12. R6's no-op claim is pinned by a **synthetic fixture reproducing the real corpus's
    outcome composition** (`patched_and_retried` ×2, `gave_up` ×4,
    `stopped_for_confirmation` ×1, one zero-event run): the rate is identical before and
    after. **The real corpus itself cannot be a test** — `/runs/` is gitignored
    (`.gitignore:9`) and lives outside the repo, so CI can never read it. The real-directory
    check is a **one-off manual gate**, run once and its number recorded in the writeup,
    following the DOI slice's manual-gate idiom. An acceptance criterion that cannot run
    would be worse than none, because it reads as coverage.
13. The CLI no longer prints "which is never recorded"; the `attendance_unknown` line still
    appears when the bucket is non-empty.
14. `resume` after `run --auto-approve` leaves `auto_approve: false`, with the
    self-consistency reasoning in the test name (R9).
15. A contradictory bundle (`auto_approve: true` + `rejected_by_user`) classifies
    **attended** — the literal wins (R5a).
16. The CLI attributes `attendance_unknown` to its cause rather than merging legacy and
    ambiguous into one count (R6a).

## Risks & Open Questions

- **RISK-1 — The over-claim fix (R5) is self-graded and unobserved.** No real run has ever
  produced a gated literal, so problem (2) is reasoned from control flow, not seen. The
  fix is provable by construction (three call sites, all gated) but its field frequency is
  **unmeasured and is not claimed**.
- **RISK-2 — R2 is a convention, not a mechanism.** Nothing structurally prevents a future
  editor from wiring the field into replay. AC#4 is the tripwire; it is a test, not a type.
- **RISK-3 — Widening the unknown bucket (R6) could later exclude real runs from the gate
  denominator.** If a future corpus has many legacy gated steps, the denominator shrinks
  and the rate gets *less* computable. Accepted: a smaller honest denominator beats a
  larger invented one, and it is a no-op today (AC#12).
- **RISK-4 — Correcting the predecessor PRD (R4) touches a shipped planning doc.** Annotate
  with a dated correction; do not rewrite history.
- **RISK-5 — A run-level fact may be the wrong shape.** R5 lets a *run-level* flag override
  *step-level* evidence, while `_run_is_attended` is any-step-wins precisely because
  attendance is a property of moments. `--auto-approve` is process-wide today
  (`self_heal.py:1177`, fixed for the life of the call), so the shapes agree. If it ever
  becomes per-attempt or mid-run toggleable — the approval gate already writes per-attempt
  files — the right home becomes `RepairStep`, at the cost of the signed payload. Accepted
  deliberately; **revisit trigger:** the first change that makes approval policy vary
  within a single run.
- **Effort / sequencing.** One aspect, no external dependency, no new package. Roughly:
  model + write (small), tolerant loader + `LoadedRun` (small), the attendance rule and its
  precedence (the substance), 6 deliberate test updates + ~10 new tests, CLI strings, docs.
  R4 is separable and could land first as its own commit.
- **Open:** whether `approval_timed_out` should stay attended. A lapsed window means a
  human did *not* respond, though the run did pause for one. Inherited from the
  predecessor's table unchanged; flagged, not re-litigated here.

## Out of Scope

- Any change to `RunRecord`, the canonical signed payload, or the signing machinery.
- `--auto-approve` on `rerun`/`resume`; dashboard surfaces; `--snapshot`/`--history`.
- Retroactively attributing attendance to the 15 existing bundles.
- Re-opening the `patch_applied` axis (`classify_applied`), which is deliberately
  asymmetric with attendance and says so (`repair_stats.py:152-154`).

## Guardrails (CLAUDE.md)

Layer 2 — provenance capture and eval instrumentation on the self-heal loop. No Layer 1,
no wet-lab/clinical dependency, no proprietary data. Honesty posture: push not demand-pull,
recovers nothing for a user, moves no reported number; it makes the loop's field
performance legible and closes a latent over-claim that ran in our own favour.

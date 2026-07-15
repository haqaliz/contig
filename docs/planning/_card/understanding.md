# Phase 2 — Understanding: sibling-plausibility-fail-severity

Dug by four parallel read-only agents (chokepoint/plumbing, somatic metrics, RNA-seq metrics,
germline test pattern). Every claim below is file:line-grounded.

## Headline: the brief's premise holds, but its scope collapses from three packs to one line

The brief proposed extending gross-implausibility FAIL severity to `SOMATIC_PLAUSIBILITY_PACK`,
`RNASEQ_PLAUSIBILITY_PACK`, and possibly `RNASEQ_COMPOSITION_PACK`. The dig says:

| Pack / metric | Universal gross floor? | Honest outcome |
|---|---|---|
| `somatic_variant_count` | **YES (floor only)** | **`fail_below: 1`** — the whole slice |
| `median_vaf` (Mutect2) | No | Stay WARN-only |
| `strelka_median_vaf` | No | Stay WARN-only |
| `pon_applied` | N/A (not a numeric metric) | Stay WARN, unbandable |
| `duplication_rate` | No | Stay WARN-only |
| `rrna_contamination` | No | Stay WARN-only |
| `exonic_fraction` | Marginal (exact-0 only) | Stay WARN-only |
| `intronic_fraction` | No | Stay WARN-only |
| `unassigned_fraction` | No (redundant with `assignment_rate fail_below 40`) | Stay WARN-only |

**The slice is one line of production code** (`"fail_below": 1` on `rule_pack.py:320-325`) plus its
tests and docstring/roadmap honesty updates. That is the honest success case the card predicted;
it is not a failure of the dig.

## 1. It IS a pure data edit (confirmed)

- `_status_for` (`rule_pack.py:447-466`) reads all four band keys via `.get()`; the docstring at
  `:450-452` says any subset is legal. **The WARN cap is enforced only by the absence of `fail_*`
  keys in the pack data — no code clamps FAIL→WARN anywhere.** (Agent grepped
  `src/contig/verification/`, `runner.py`, `models.py` for clamp patterns; every hit is a
  hand-built check or a docstring.)
- Every plausibility evaluator funnels through the shared `evaluate()` (`rule_pack.py:480-499`);
  `evaluate_somatic_plausibility` (`somatic_plausibility.py:252`) passes status straight through.
- `overall_verdict` (`models.py:78-96`): a single `fail` dominates; `unverified` carries no
  severity and can never become a pass. `RunRecord.verdict` (`models.py:358-369`) consumes it.
- So a new `fail` QCResult reaches `record.verdict == "fail"` with **zero code change**, and
  v0.36.0's `--fail-on-verdict` then exits 1. The chain is proven end to end.

## 2. Why `somatic_variant_count fail_below: 1` is defensible without calibration

- **It is the direct structural mirror of shipped germline `variant_count`**
  (`rule_pack.py:84-90`: `fail_below: 1`, `warn_below: 10`, `warn_above: 20_000_000`, and
  deliberately **no `fail_above`**). The germline comment (`:77-83`) is the precedent verbatim:
  *"fail_below 1 is a hard floor: an empty/near-empty call set (0 sites) is a broken run and
  FAILs, same tier as mean_coverage's fail_below."*
- **The floor actually fires.** `count` is initialized to `0` (`somatic_plausibility.py:133`) and
  incremented at `:155` — *before* the tumor-column guard at `:156` — so it is always a real int,
  independent of tumor identification. The `computable` filter is `if value is not None`
  (`:248-250`), so **0 survives into `evaluate()` and rides the band** rather than routing to
  UNVERIFIED. The docstring already states this (`:233-234`): *"variant_count is always an int, so
  it is always computable."*
- **It needs no cohort.** An empty call set is broken regardless of target type — which is exactly
  why it escapes the "deferred until calibrated" blocker that legitimately still binds the VAF
  metrics.

## 3. Why everything else is honestly out (this is the load-bearing finding)

**The VAF metrics have no universal floor.** Germline Ti/Tv could ship a FAIL band because it has a
*physically constrained* expected value (~2.0 WGS, ~3.0-3.3 WES) with noise at a *distinguishable*
~0.5. Tumor VAF has no such structure: its expected value is a function of **purity and clonality,
which the code never observes** (no purity estimate, no ploidy, no copy-number, no target type). A
low median VAF is legitimate science (low-purity tumor, subclonal population). Any `fail_below`
here would FAIL a real sample — the worst outcome in the brief.

- `strelka_median_vaf` is **arithmetically bounded to [0,1] by construction**
  (`strelka_vaf.py:95-98`, `:121-124` reject `denom <= 0`), so a `fail_above: 1.0` is **provably
  dead code**. Do not add it.
- `pon_applied` is a 3-state string from a header search (`somatic_plausibility.py:199-221`)
  emitted with `value=None` (`:279-287`); it never enters `evaluate()`. `_status_for` would
  `TypeError` on `None < fail_below`. It is **structurally unbandable** — and PON absence is a
  legitimate configuration Contig itself does not wire (`somatic-vaf-plausibility/prd.md:196-198`).

**The RNA-seq metrics fail on biology AND engineering.**

- *Biology:* every one has a legitimate protocol occupying the extreme — deep/high-input libraries
  legitimately exceed 90% duplication; total-RNA/ribo-depletion legitimately retains rRNA;
  nuclear/FFPE/3' libraries are legitimately intron-dominated; non-model annotation legitimately
  leaves most tags unassigned. "Extreme" and "unusual protocol" are the same number.
- *Engineering:* **both `RNASEQ_PLAUSIBILITY_PACK` slugs are dormant on real output.**
  `percent_duplication` / `percent_rRNA` (`rule_pack.py:288`, `:294`, both commented "slug
  unverified") are **absent from the repo's only real-shaped MultiQC**
  (`demo/sample-run/results/multiqc/multiqc_data.json` carries only `uniquely_mapped_percent`,
  `percent_assigned`, `total_reads` — verified directly). A FAIL band there is severity on
  code that has never once fired. There is also a live unit ambiguity: the pack declares 0-100
  (`rule_pack.py:283-284`) while Picard's native `PERCENT_DUPLICATION` is a 0-1 fraction, and
  `qc_ingest.py:5-23` does a bare `float()` with no normalization.
- `unassigned_fraction == 1.0` is genuinely broken but **already caught more honestly** by
  `RNASEQ_RULE_PACK`'s `assignment_rate fail_below: 40` (`rule_pack.py:24-30`) on the did-it-run
  tier. A second FAIL is redundant, not new signal.

**Annotation pack is out of scope**: `ANNOTATION_PLAUSIBILITY_PACK` (`rule_pack.py:351-373`) is
deliberately loose (`warn_below 0.10`, `warn_above 0.95`) and belongs to the separate C7 M-track
with its own deferral trail (M5 eval fold-in blocked on labeling design).

## 4. The one real risk to decide (R3, inherited)

Unlike germline, **a somatic zero can be legitimate**: a small hotspot/targeted panel on a tumor
with no mutation in the assayed regions genuinely calls zero. Already logged as R3 in
`somatic-vaf-plausibility/prd.md:174-177` (*"band is assay/target-dependent … revisit when
target-type is known to the engine"*).

Mitigating facts:
- The escalation is **the narrowest possible**: `warn_below: 10` already catches near-zero as WARN,
  so `fail_below: 1` moves **only the exactly-zero case**. 1-9 records stay WARN, unchanged.
- sarek's Mutect2 emits unfiltered-plus-FILTER-annotated records, and the count is **not**
  PASS-filtered (`somatic_plausibility.py:81-83,155`), so a genuinely 0-record VCF from a real run
  is a truncation/crash artifact, not a biological result.
- `--fail-on-verdict` is opt-in (v0.36.0), so the blast radius is callers who asked for teeth.

This is a judgement call the PRD must state explicitly, not bury.

## 5. Test pattern to mirror (correction to the card)

**The card's acceptance criteria were slightly wrong.** The germline slice's tests do **not** build a
`RunRecord` or assert `record.verdict`. They assert `QCResult.status == "fail"` on the individual
check, and call the free function `overall_verdict(results)` exactly once
(`test_variant_metrics.py:388-419`). Shipping commit `69b6385` touched exactly 4 files (2 source,
2 test), with **no CLI test and no `run_qc` gate test**.

The mirror for this slice:
- `tests/verification/test_rule_pack.py` — add a `fail_below`-only assertion (mirroring
  `test_variant_count_has_fail_below_only:186-192`) and a `bands_are_well_ordered` invariant loop
  over the somatic pack (mirroring `:196-206`).
- `tests/verification/test_somatic_plausibility.py` — extend the existing inline tumor-normal VCF
  helpers (`:22-40`); invert `test_variant_count_out_of_band_warns` (`:246-256`).
- Bodies to add: 0-record VCF → `status == "fail"`, `value == 0`, **`status != "unverified"`**
  (the anti-confusion guard, mirroring `test_variant_count_zero_fails_not_unverified:376-386`),
  closed with `overall_verdict(results) == "fail"`; a legitimate small count (e.g. 5) still WARN,
  **not** FAIL; `median_vaf`/`strelka_median_vaf` extremes still `!= "fail"` (the WARN-cap tests
  must STAY green — they are now a deliberate guarantee, not an accident).
- Conventions: `uv run pytest`; flat `tests/` + `tests/verification/`; **no conftest.py anywhere**,
  each file defines local helpers; real files via `tmp_path`, never mocks; every non-obvious test
  opens with a 2-4 line why-comment citing the PRD requirement id.

**A CLI exit-code test is out of scope**: `--fail-on-verdict` is already proven generically against
`QCResult(status="fail")` (`test_cli.py:217+`); the check that produced the fail is irrelevant to
the gate.

## 6. Tests that will go RED

- `test_somatic_plausibility.py:246-256` `test_variant_count_out_of_band_warns` — **must change**
  (this is the RED).
- `test_rule_pack.py:558-565` / `:636-644` (`..._have_no_fail_keys` for the RNA-seq packs) —
  **stay green** under the recommended scope; RNA-seq is untouched.
- No `no_fail_keys` guard test exists for `SOMATIC_PLAUSIBILITY_PACK` itself — only behavioral
  WARN assertions.

Docstrings stating the cap as design intent also need updating: `rule_pack.py:302`, `:311`, `:329`;
`somatic_plausibility.py:6`, `:227`, `:230-234`.

## 7. Guardrail check (CLAUDE.md)

- **Layer 2 only** — verify axis. On-thesis. ✅
- **No over-claiming** — the floor is an engineering tripwire ("an empty call set is a broken
  run"), explicitly not a biological/clinical claim. The dig actively *refused* the bands that
  would have over-claimed. ✅
- **UNVERIFIED never becomes FAIL** — preserved; the anti-confusion test names the failure mode. ✅
- No new dependency, no raw-read egress, test-first. ✅

## 8. Open question for the interview (needs a human decision)

The slice is honestly one line. Three ways to spend this branch:

- **(A) Ship the narrow floor only.** Closes part of the named deferral; somatic verdict gains
  teeth for the empty-call-set case.
- **(B) Narrow floor + convert the rest from vague "deferred until calibrated" into a decided
  "will-not-do, and here is why."** The dig proved the VAF/RNA-seq FAIL bands are not a
  calibration problem — they are *structurally impossible to do honestly*. Recording that stops
  the item from being re-picked forever. Same code, better roadmap honesty.
- **(C) Pivot/extend to the dormant-slug bug the dig surfaced.** `percent_duplication` /
  `percent_rRNA` never resolve on real nf-core/rnaseq output, so `RNASEQ_PLAUSIBILITY_PACK` is a
  **silent no-op today** — the same class of defect as the shipped single-cell ingestion slice
  (`CAPABILITY_ROADMAP.md:482-497`), which fixed a pack that "silently no-oped". Arguably higher
  user value than any FAIL band, but it is a different unit of work.

Recommendation: **B**, with **C** filed as the next `contig-next` candidate.

# PRD — assay-qc-verdict-fires

**Feature slug:** `assay-qc-verdict-fires`
**Branch:** `feat/assay-qc-verdict-fires/aliz`
**Capability:** C3 (biological-plausibility verification) — the methylation / 16S /
shotgun-metagenomics analogue of the shipped single-cell v0.21.0 slice.
**Status:** PRD (pre-plan). Research-use verification only.

---

## Problem Statement

Contig wires seven assays, each with an "assay-aware QC pack," but three of
them — `methylseq`, `ampliseq`, `mag` — carry biological QC packs
(`METHYLSEQ_RULE_PACK`, `AMPLISEQ_RULE_PACK`, `MAG_RULE_PACK`,
`rule_pack.py:131-226`) that **silently no-op on every real run**. Their metrics
arrive only through the generic MultiQC general-stats path
(`runner.py:115-124` → `run_qc.py` → `qc_ingest.py`), keyed on slugs the source
itself annotates as **"slug unverified."** When a slug does not match,
`evaluate()` does `if check["metric"] not in sample_metrics: continue`
(`rule_pack.py:368`) — it emits **nothing**: no PASS, no FAIL, and critically **no
UNVERIFIED**. So the biological verdict for these assays is invisible-hollow: it
"reads as wired" while never actually checking biology.

This is the exact latent no-op that hollowed the single-cell verdict until v0.21.0
made it fire by ingesting the aligner's own on-disk artifact. Three of seven assays
still sit in the pre-fix state.

**Evidence it's real:** confirmed by code (`rule_pack.py:368-369`,
`run_qc.py:34-35`, the "slug unverified" docstrings at `rule_pack.py:117-203`), and
by the shipped scrnaseq precedent (`CHANGELOG.md` v0.21.0) which fixed the identical
pattern.

## Goals & Success Metrics

- **G1 — the methylseq biological verdict fires.** On a run whose Bismark report
  artifacts are present, `methylseq` biological checks emit real PASS/WARN/FAIL
  results (not an empty set). *Measure:* a test run with healthy Bismark reports
  yields ≥1 non-UNVERIFIED methylseq `QCResult`; a grossly-failed run yields FAIL.
- **G2 — no silent no-op ever again for methylseq.** A located-but-unparseable
  artifact yields an **explicit UNVERIFIED breadcrumb** `QCResult`, never silence.
  *Measure:* the located-but-empty test asserts exactly one
  `methylseq_qc:<sample>` UNVERIFIED result.
- **G3 — honest absence.** No artifact at all → silent skip (structural QC owns the
  missing-output case), exactly as scrnaseq does. *Measure:* no-file test asserts no
  methylseq metric results and no crash.
- **G4 — reusable seam.** The methylseq gate/parser shape is a clean template so
  ampliseq and mag are near-mechanical fast-follows (separate slices).

**Non-metric of success (explicit):** we are **not** claiming the bands are
biologically calibrated. Correctness of the *threshold values* is out of scope;
correctness of the *firing mechanism* is the whole point.

## User Personas & Scenarios

- **A, lone computational biologist** running nf-core/methylseq on their own data:
  today Contig's verdict says nothing about conversion/mapping/duplication sanity;
  after this, a grossly-failed methylation run is flagged instead of passing
  silently.
- **C, core facility** running methylseq at throughput: wants a verdict that
  actually inspects the assay, and an honest UNVERIFIED when it genuinely can't.

## Requirements

### Must-have (this slice — methylseq)

- **M1.** A new `verification/methylseq_metrics.py` with pure, stdlib-only parsers
  that read Bismark's own on-disk report artifacts for one sample into
  `{canonical_slug: float}`:
  - `percent_aligned` from the Bismark **alignment report** (`*_PE_report.txt` /
    `*_SE_report.txt`, "Mapping efficiency").
  - `percent_duplication` from the **deduplication report**
    (`deduplicate_bismark` output / `*.deduplication_report.txt`).
  - `percent_bs_conversion` **only** when a recognizable conversion/control line is
    present (splitting report / spike-in); otherwise omitted (→ UNVERIFIED, never
    guessed). Kept in the pack per the interview decision.
  - **Floor principle** (mirror scrnaseq): a non-numeric/absent value is omitted,
    never coerced to 0; an unrecognized artifact returns `{}`. No HTML scraping.
- **M2.** In `runner._discover_qc`, a dedicated `if assay == "methylseq":` gate
  (mirroring the scrnaseq gate `runner.py:231-246`) with `_locate_methylseq_qc` +
  a `_sample_from_*` helper (mirror `_locate_scrnaseq_qc` `runner.py:90-107`):
  - metrics parsed → `evaluate({sample: metrics}, METHYLSEQ_RULE_PACK)`;
  - artifact located but no usable metric → **explicit UNVERIFIED**
    `QCResult(check=f"methylseq_qc:{sample}", status="unverified", value=None,
    kind="metric")`;
  - no artifact at all → silent skip.
- **M3.** Deterministic per-sample id derivation; if two report kinds (alignment,
  dedup) map to the same sample, merge into **one metric dict per sample**, no
  double-count. **Partial reports are honest:** a sample with only the alignment
  report evaluates the checks it *can* (mapping efficiency) and simply emits no
  result for the metrics whose source artifact is absent — it does **not** become a
  whole-sample UNVERIFIED. The explicit-UNVERIFIED breadcrumb (G2) fires **only**
  when a located artifact yields **zero** usable metrics for that sample (mirrors
  scrnaseq's `if sample_metrics:` boundary, `runner.py:238`). A present-but-absent
  single metric (e.g. bisulfite conversion with no control line) yields no result
  for that one check — honest silence at the check level, not a false UNVERIFIED for
  the sample.
- **M6.** The new methylseq gate is the **single authoritative source** for
  methylseq biological metrics. Because the generic MultiQC pack path
  (`runner.py:121-124`) also selects `METHYLSEQ_RULE_PACK`, the plan must prevent
  double-emission: skip the generic pack evaluation for `assay == "methylseq"` (the
  gate owns it), so a check can never be emitted twice if a future MultiQC ever
  carried a matching slug.
- **M4.** Packs stay **WARN/FAIL-capped and UNVERIFIED-when-absent**; **no band
  re-calibration** in this slice. The `METHYLSEQ_RULE_PACK` slugs are unchanged if
  the parser emits those canonical names; the "slug unverified" comment is tightened
  to name the confirmed source artifact.
- **M5.** Strict TDD, stdlib-only, no new dependency, no raw-read egress, no real
  nf-core run in CI. Tests use realistic hand-authored Bismark report fixtures.

### Should-have

- **S1.** A realistic methylseq fixture (report text shaped like real Bismark
  output) committed under `tests/` so the slugs are pinned to a concrete artifact,
  not a guess.
- **S2.** The gate is written so ampliseq/mag drop in with only a new parser + gate
  branch (no rework of the shared shape).

### Nice-to-have (explicitly deferred to later slices)

- ampliseq firing (DADA2 read-retention / ASV count / read depth).
- mag firing (QUAST N50, CheckM completeness/contamination).
- Band calibration on real data / FAIL-severity tuning (separately deferred across
  all C1/C3 slices).
- Dashboard surfacing beyond what the existing QC panel already renders.

## Technical Considerations

- **Architecture (decided):** dedicated on-disk artifact parsers behind a per-assay
  gate — **not** MultiQC slug-aliasing. Rationale: the general-stats path is the
  exact fragile assumption that broke scrnaseq; `percent_bs_conversion` in
  particular is commonly absent from Bismark general-stats.
- **Where it sits:** verify stage only (`_discover_qc` in the run pipeline). No
  change to plan, launch, self-heal, or reproduce. No change to `models.py`,
  `overall_verdict`, `_RULE_PACKS`, or `rule_pack_for` — selection already works;
  only metric delivery is added.
- **Reproducibility/verification impact:** strictly additive to the verdict. A run
  that previously reduced to PASS/UNVERIFIED on structural checks alone can now
  additionally WARN/FAIL on biology, or emit an explicit UNVERIFIED breadcrumb.
  UNVERIFIED is never rendered as PASS (`overall_verdict`, `models.py:78-96`).
- **Eval data captured:** methylseq plausibility outcomes join the per-assay
  reference distributions (moat #2), same as the other C3 slices.

## Risks & Open Questions

- **R1 (primary) — wrong offline slug/artifact.** CI never runs nf-core/methylseq
  and no real methylseq artifact exists locally, so the exact Bismark report field
  names are pinned from a hand-authored fixture. *Mitigation:* the explicit
  UNVERIFIED breadcrumb makes a wrong field **fail loudly**, never silently — the
  failure mode we're eliminating cannot recur. Confirm field names against real
  Bismark report format during the parser build.
- **R2 — bisulfite conversion rarely present.** Accepted: it degrades to UNVERIFIED
  when no control line exists (interview decision), and fires for runs that carry a
  conversion control. Honest, not a blocker.
- **R3 — sample-id derivation across two report kinds.** Must merge alignment +
  dedup reports for the same sample without double-count. Covered by M3 + a test.
- **R4 — the common single-report case.** A real methylseq run may carry only the
  alignment report (no dedup, no conversion control). Decided (M3): that surfaces as
  an honest PASS/WARN on mapping efficiency, **not** a whole-sample UNVERIFIED. The
  plan must encode this boundary precisely — getting it wrong reintroduces either a
  silent gap or a cry-wolf UNVERIFIED.
- **Open:** exact filename globs for the Bismark reports (resolved in tech-plan
  against the real nf-core/methylseq output layout).

## Out of Scope

- ampliseq and mag firing (separate fast-follow slices on the same seam).
- Any band re-calibration or FAIL-severity tuning on real data.
- MultiQC slug-aliasing as the mechanism (rejected in favor of dedicated parsers).
- The deferred single-cell simpleaf/alevin-fry ingestion (different, genuinely
  blocked: no structured artifact at all).
- Any Layer-1 workflow authoring; any new assay; any self-heal change.

## Guardrail check (CLAUDE.md)

Pure Layer-2 verification hardening. No Layer-1. No raw-read egress (parsers read
small report text files on the user's compute). No correctness over-claiming
(UNVERIFIED never PASS; bands scoped per assay, uncalibrated defaults unchanged).
Test-first.

# PRD: RNA-seq biological-plausibility verification (C3 follow-on)

- **Slug:** `rnaseq-plausibility`
- **Type:** feat · **Owner:** aliz · **Branch:** `feat/rnaseq-plausibility/aliz`
- **Capability:** C3 (biological-plausibility verification), RNA-seq slice
- **Source:** inline brief from `contig-next` (`_card/issue.md`); dig note
  (`_card/understanding.md`)

## Problem Statement

Contig's RNA-seq verdict today rests on generic "did it run" QC — mapping rate,
assignment rate, pseudo-alignment rate (`RNASEQ_RULE_PACK`, `rule_pack.py:16-41`) —
plus structural/integrity checks. It carries **no biological-plausibility axis**:
a run can map and assign reads fine yet be biologically implausible (e.g. heavy
PCR/optical duplication, high rRNA contamination from poor depletion). The germline
assay already gained this axis in v0.3.0 (Ti/Tv, het/hom via `variant_metrics.py`),
but RNA-seq — the **lead, highest-TAM assay** (ROADMAP §"Pipeline choice") — did not.
`CAPABILITY_ROADMAP.md:144-153` explicitly lists rRNA (RNA-seq) as deferred to a
later C3 slice. This is that slice.

**Why it matters (moat #1).** Issuing a verdict that is *smarter about biology* is
the judgement incumbents leave to humans (FEATURES.md competitive scan). It also
compounds moat #2: plausibility outcomes per assay become reference distributions
and seed corpus cases.

## Goals & Success Metrics

1. A bulk-RNA-seq run gains at least two WARN-capped biological-plausibility checks
   (duplication, rRNA contamination) that participate in the verdict.
2. **Honesty guarantee preserved:** a plausibility metric absent from the run's
   ingested MultiQC yields `unverified` for that check — **never PASS, never FAIL**.
3. WARN-capped only: no plausibility check can FAIL a verdict in this slice (bands
   are illustrative engineering defaults, uncalibrated on real data).
4. Full test suite green; no regression to the existing RNA-seq mapping-rate QC or
   to the detector eval.

Measured by: new unit tests (in-band→PASS, out-of-band→WARN, absent→UNVERIFIED) and
the full `uv run pytest` suite passing.

## User Personas & Scenarios

- **A, lone computational biologist** runs nf-core/rnaseq; wants the verdict to flag
  a library-quality problem (high duplication / rRNA) without hand-reading MultiQC.
- **B, wet-lab scientist who can't code** needs a trustworthy answer; a WARN with a
  named biological reason ("rRNA contamination above expected band") is actionable
  where a raw MultiQC table is not.
- **D, biotech researcher** wants the plausibility signal captured in provenance for
  a defensible Methods record.

## Requirements

### Must-have

- **M1 — RNA-seq plausibility rule set.** A new WARN-only pack
  (`RNASEQ_PLAUSIBILITY_PACK`) separate from `RNASEQ_RULE_PACK`, with two checks:
  - `duplication_rate` over metric `percent_duplication` (Picard MarkDuplicates;
    0–100 scale, matching the existing methylseq usage at `rule_pack.py:148-154`),
    `warn_above` only (RNA-seq tolerates higher duplication than methyl-seq — band
    set leniently, e.g. ~80%), **no `fail_*`**.
  - `rrna_contamination` over metric `percent_rRNA` (best-effort MultiQC slug;
    one-sided `warn_above`, e.g. ~10%), **no `fail_*`**.
  - Both documented as illustrative, tunable defaults with the slug marked
    unverified, matching the existing-pack comment convention.
- **M2 — honest evaluator wrapper.** `evaluate_rnaseq_plausibility(metrics_by_sample)`
  mirroring `evaluate_variant_plausibility`: pass/warn for present metrics via the
  shared `evaluate()`, and an **explicit `unverified` `QCResult`** (`kind="metric"`,
  `value=None`) for every plausibility metric absent from a sample's dict. (The
  shared `evaluate()` silently skips absent metrics — `rule_pack.py:288` — so the
  honest-UNVERIFIED behavior must live in this wrapper, exactly as germline does.)
- **M3 — wiring.** Invoke the wrapper from `runner._discover_qc` under
  `assay == "rnaseq"`, reusing the MultiQC metrics already parsed for the assay rule
  pack (do not re-parse the report).
- **M4 — tests (test-first).** Mirror `tests/verification/test_variant_metrics.py`:
  in-band→PASS, out-of-band→WARN (assert never FAIL), metric absent→UNVERIFIED with
  `value=None`; and an integration assertion that the checks appear for an RNA-seq
  run with a MultiQC report carrying the metrics.

> **Corpus seeding removed.** The brief said "seed the eval corpus per the C3
> pattern," but `detector_corpus.jsonl` is a *failure-detection* corpus keyed by
> `FailureClass`; a plausibility WARN is not a failure class, and the germline C3
> slice seeded **zero** corpus cases. Seeding here would require a bogus
> `expected_class` and pollute the detector eval. **Decision (user): tests-only**,
> matching the real C3 precedent. The detector eval must stay green (we do not touch
> the corpus).

### Should-have

- A one-line `message` per check that names the biological reason in plain language
  (surfaced via the existing `kind="metric"` rendering).

### Nice-to-have / explicitly deferred

- Gene-body-coverage evenness, exonic-mapping-fraction-as-plausibility, library
  complexity — **deferred**: gene-body evenness needs a *new* RSeQC compute path
  (parse `geneBody_coverage` output), not just a rule (contig-next caveat).
- FAIL severity for any plausibility check — deferred until bands are calibrated on
  real data (same posture as the germline slice).
- single-cell (doublet, mito fraction) and sex-check — separate later C3 slices.

## Technical Considerations

- **Architecture fit.** Pure addition on the verify path; reuses the
  metric→rule→verdict plumbing and the germline wrapper pattern. No new QC kind
  (`kind="metric"` already renders in report/dashboard).
- **Metric availability is the known risk (see Risks).** Resolved by design: the
  UNVERIFIED-when-absent guarantee means a wrong/missing slug degrades honestly
  rather than producing a false signal.
- **Reproducibility/verification impact.** Strengthens the verdict; no change to the
  run record schema. Plausibility checks are deterministic functions of the ingested
  metrics. No raw-read egress (reads the run's own MultiQC on the user's compute).
- **No Layer-1 surface.** Verification only; consumes nf-core/rnaseq output.

## Risks & Open Questions

- **R1 (primary): metric slugs not confirmable from fixtures.** `percent_duplication`
  and `percent_rRNA` are not in any current test fixture; the exact nf-core/rnaseq
  MultiQC general-stats keys are unverified from the repo. **Decision (user):**
  proceed best-effort — pick the most-likely keys, band WARN-only, rely on
  UNVERIFIED-when-absent; a later real run calibrates keys/bands. Consequence to
  accept: on runs whose MultiQC lacks these keys, the checks read UNVERIFIED (honest,
  not a false pass) rather than firing.
- **R2: band values are illustrative.** Documented as tunable engineering defaults,
  not biological claims (matching every existing pack's comment). WARN-only contains
  the blast radius.
- **R3: duplication double-surface.** methylseq already keys `percent_duplication`;
  the RNA-seq check is in a *separate* pack via the plausibility wrapper, so there's
  no collision with the methylseq `duplication_rate` rule.
- **Open:** exact `warn_above` values for each band (set in the plan; illustrative).

## Out of Scope

- Gene-body-coverage evenness / any new metric-compute path (no `rnaseq_metrics.py`
  analogue to `variant_metrics.py` this slice — all metrics come from ingested
  MultiQC).
- **Detector-corpus seeding** (the checks are not a `FailureClass`; tests-only).
- FAIL severity; single-cell and germline-sex-check plausibility; dashboard/report
  rendering changes; recalibrating the existing `RNASEQ_RULE_PACK` mapping-rate rules.

## Artifact / Run Contracts

- New `QCResult`s with `check` formatted `"{check}:{sample}"`, `kind="metric"`,
  `status ∈ {pass, warn, unverified}`, `value` a float or `None`. No schema change.

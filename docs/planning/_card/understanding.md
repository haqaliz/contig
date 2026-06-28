# Understanding: rnaseq-plausibility

Phase-2 dig note (grounded in a code map of this worktree, agent reconnaissance).
File:line refs are to `src/contig/` unless noted. This slice **extends** the
just-shipped germline C3 biological-plausibility verdict to **bulk RNA-seq**.

## What the work is really asking

Make the RNA-seq verdict *smarter about biology*, the same way the germline slice
did: add WARN-capped plausibility checks that degrade to UNVERIFIED (never PASS)
when their input is absent, on a path that mirrors `evaluate_variant_plausibility`.

## The germline template to mirror (do NOT rebuild)

- `verification/variant_metrics.py:107-179`: `variant_metrics(vcf)` computes
  `ts_tv`/`het_hom` (each `None` when uncomputable); `evaluate_variant_plausibility`
  looks up the WARN-only rules, builds a `{sample: {metric: value}}` dict for
  computable metrics, calls the shared `evaluate()`, and **explicitly emits an
  `unverified` `QCResult` (kind="metric", value=None) for each uncomputable metric**.
- The shared evaluator `rule_pack.evaluate(metrics, rule_pack)` (`rule_pack.py:282`)
  **silently skips** a metric that isn't in the dict (`:288 continue`). So the
  "unverified when absent, never PASS" guarantee is the *caller's* job — exactly why
  germline has its own `evaluate_variant_plausibility` wrapper. RNA-seq needs the
  same wrapper; we cannot just drop plausibility rules into `RNASEQ_RULE_PACK`
  (they'd silently skip → no honest UNVERIFIED).
- WARN-only rules carry `warn_below`/`warn_above` and **no** `fail_*`
  (`rule_pack.py:54-67`). Worse-status-wins via `_status_for` (`:249-268`).

## The wiring hook point

`runner.py:_discover_qc` (`:36-67`). Today it runs the assay rule pack over MultiQC
(`:40-48`) and, **for `variant_calling` only**, runs VCF plausibility (`:62-66`). The
RNA-seq plausibility step hooks in as a parallel `if assay == "rnaseq":` branch that
emits the new checks. `assay` is already threaded through (`:36`, called `:286`).

## THE CENTRAL FINDING — metric availability (the real scope decision)

The agent traced exactly what RNA-seq metrics reach the verdict via
`qc_ingest.parse_multiqc_general_stats` (`qc_ingest.py:5-23`):

**Already ingested** (from `tests/test_qc_ingest.py:104-122` and `demo/`): Salmon
`percent_mapped`, STAR `uniquely_mapped_percent`, featureCounts `percent_assigned`,
samtools `reads_mapped_percent`, rseqc `unique_percent`, `total_reads`.

**NOT in any fixture**: rRNA-contamination fraction, `percent_duplication`,
gene-body-coverage evenness, doublet/sex-check.

The tension this creates (and the thing the interview must resolve):
- The metrics that would make RNA-seq plausibility **distinct** from the existing
  "did it map / did it assign" QC (rRNA, duplication, gene-body evenness) are **not
  confirmed present** in the ingested MultiQC.
- The metrics that **are** present (mapping %, assignment %) are already covered by
  the three existing `RNASEQ_RULE_PACK` rules (`rule_pack.py:16-41`) — they are
  lower-bound "did it run" checks, not two-sided biological-plausibility bands.

So a naive "add plausibility rules over ingested metrics" risks either (a)
duplicating existing checks, or (b) keying off metrics that aren't there.

## The honest, shippable slice

Mirror germline exactly, and let the UNVERIFIED-when-absent guarantee carry the
uncertainty about which metrics a given run's MultiQC actually contains:

1. A small `RNASEQ_PLAUSIBILITY_PACK` (separate from `RNASEQ_RULE_PACK`) of
   **WARN-only** two-sided plausibility rules over the most-likely-present
   plausibility metric(s) — lead candidate **`percent_duplication`** (Picard
   MarkDuplicates runs in nf-core/rnaseq), with rRNA as a second candidate if its
   key is confirmable.
2. A new `evaluate_rnaseq_plausibility(metrics_by_sample)` wrapper that emits
   pass/warn for present plausibility metrics and **explicit `unverified`** for any
   plausibility metric absent from a sample's ingested dict — the germline pattern.
3. Wire it into `_discover_qc` under `assay == "rnaseq"`, reusing the MultiQC
   metrics already parsed (don't re-parse).
4. Tests mirror `tests/verification/test_variant_metrics.py`: a synthetic metrics
   dict in-band → PASS, out-of-band → WARN (never FAIL), metric absent → UNVERIFIED.
5. Seed one golden corpus case per new check (`detector_corpus.jsonl`), per the
   brief, keeping the detector eval green.

This ships regardless of whether a specific nf-core/rnaseq run carries the metric:
present → it's checked; absent → honest UNVERIFIED. **Gene-body-coverage evenness is
deferred** (needs a new RSeQC compute path, not just a rule) per the contig-next
caveat.

## Open questions for the interview

- **Exact metric key(s)** nf-core/rnaseq's MultiQC general-stats emits for
  duplication / rRNA, and which `qc_ingest.py` surfaces. (Cannot verify from fixtures
  alone — pick the most-likely key, band it WARN-only, rely on UNVERIFIED-when-absent.)
- **Which checks ship this slice** (lead: duplication; rRNA if key confirmable) vs.
  defer (gene-body evenness → new compute path).
- **WARN bands** per metric (illustrative engineering defaults, like germline
  Ti/Tv / het/hom), with a one-line rationale each.
- **Separate pack vs. flag within `RNASEQ_RULE_PACK`** (lean: separate pack, because
  the shared evaluator silently skips absent metrics and we need honest UNVERIFIED).
- **Corpus**: one golden case per new check (brief leans yes) vs. tests-only.
- **Surface footprint**: QC-panel `kind="metric"` rendering only (germline parity)
  vs. also a verdict line (lean: parity, no new rendering).

## Guardrails check (CLAUDE.md)

Layer 2 (verify) only; no Layer-1 authoring. No raw-read egress (reads the run's own
MultiQC on the user's compute). WARN-capped (no FAIL until bands calibrated on real
data); UNVERIFIED never rendered as PASS; scoped honestly per assay. Test-first via
synthetic metric fixtures (no real nf-core run in CI). Gets better as base models
adjudicate borderline bands. No contradiction between brief and code; the one nuance
is metric availability (above), which the UNVERIFIED-when-absent design absorbs.

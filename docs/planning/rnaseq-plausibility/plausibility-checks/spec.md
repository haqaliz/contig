# Aspect spec: plausibility-checks (rnaseq-plausibility, slice 1)

Parent PRD: `../prd.md`. One buildable aspect: add WARN-capped RNA-seq
biological-plausibility checks (duplication, rRNA) over ingested MultiQC metrics,
on a path that mirrors `evaluate_variant_plausibility` so absent metrics yield
`unverified`, never PASS.

## Problem slice and outcome

A bulk-RNA-seq run's `percent_duplication` and `percent_rRNA` (when present in its
ingested MultiQC general-stats) become WARN-capped QC checks that participate in the
verdict; when a metric is absent, that check is `unverified`. No metric-compute path
is added — all values come from the already-parsed MultiQC.

## In scope

- `verification/rule_pack.py`: a new `RNASEQ_PLAUSIBILITY_PACK` (separate from
  `RNASEQ_RULE_PACK`) with two **WARN-only** rules (no `fail_*`):
  - `duplication_rate` → metric `percent_duplication`, `warn_above` (0–100 scale,
    matching methylseq `rule_pack.py:148-154`); lenient band (~80) for RNA-seq.
  - `rrna_contamination` → metric `percent_rRNA`, `warn_above` (~10); slug marked
    unverified in a comment, illustrative/tunable default.
- A `evaluate_rnaseq_plausibility(metrics_by_sample)` function (location: extend
  `verification/run_qc.py` or a small new module, plan decides) that:
  - runs the shared `evaluate()` over the present plausibility metrics, and
  - emits an explicit `QCResult(status="unverified", kind="metric", value=None,
    check="{check}:{sample}")` for every plausibility metric absent from a sample's
    dict — mirroring `variant_metrics.evaluate_variant_plausibility:168-178`.
- Wire it into `runner._discover_qc` (`runner.py:36-67`) under `assay == "rnaseq"`,
  gated to when a MultiQC report was found (the metric source).

## Out of scope

- **Detector-corpus seeding** — `detector_corpus.jsonl` is keyed by `FailureClass`;
  a plausibility WARN is not a failure class and the germline C3 slice seeded none.
  Tests-only this slice (do not touch the corpus; detector eval stays green).
- Any new metric-compute path / `rnaseq_metrics.py`; gene-body-coverage evenness;
  exonic-fraction-as-plausibility; FAIL severity; single-cell or sex-check checks;
  dashboard/report rendering changes; touching the existing mapping-rate
  `RNASEQ_RULE_PACK` rules.

## Acceptance criteria (testable)

- A metrics dict with `percent_duplication` in-band → PASS `duplication_rate:sample`;
  out-of-band (above `warn_above`) → WARN; **never FAIL** (assert no FAIL possible).
- Same three-way behavior for `percent_rRNA` / `rrna_contamination`.
- A metrics dict missing a plausibility metric → `unverified` for that check, with
  `kind="metric"` and `value=None`; no crash, no PASS.
- The plausibility checks are produced for an `assay == "rnaseq"` run whose MultiQC
  carries the metrics, and are NOT produced for non-rnaseq assays.
- Detector eval stays green (the corpus is untouched).
- Full suite green at branch point (record the count in the plan).

## Dependencies and sequencing

- Reuses `rule_pack.evaluate` and the germline wrapper pattern; no external deps.
- Sequence: (1) `RNASEQ_PLAUSIBILITY_PACK` WARN-only rules →
  (2) `evaluate_rnaseq_plausibility` wrapper with unverified-when-absent →
  (3) wire into `_discover_qc` under `rnaseq` → (4) seed corpus cases.

## Open questions / risks specific to this aspect

- Exact MultiQC slugs for duplication/rRNA are unverified (PRD R1) — proceed
  best-effort; the unverified-when-absent path absorbs a wrong/missing slug.
- Confirm `percent_duplication` scale (0–100) against how the methylseq pack and the
  ingest treat it, so the band is on the right scale.
- Where `evaluate_rnaseq_plausibility` lives (run_qc.py vs a new module) — plan call.

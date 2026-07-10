# Understanding — assay-qc-verdict-fires (Phase 2 dig)

## What the work really asks

Make the biological QC verdict for `methylseq`, `ampliseq`, and `mag` **actually
fire** on a real run instead of silently degrading to UNVERIFIED, and make any
"can't compute" outcome **explicit** (a breadcrumb) rather than an invisible no-op.
Lead depth-first with **methylseq**; ampliseq and mag are fast-follows on the same
seam.

This is the exact class of latent no-op that hollowed the single-cell verdict until
v0.21.0 fixed it — and that fix is the proven template to mirror.

## Root cause (confirmed in code)

- `METHYLSEQ_RULE_PACK` / `AMPLISEQ_RULE_PACK` / `MAG_RULE_PACK`
  (`rule_pack.py:131-226`) are selected fine via `rule_pack_for(assay)` and reach
  `evaluate()`, but their metrics arrive **only** through the generic MultiQC
  general-stats path (`runner.py:115-124` → `run_qc.py:21-39` →
  `qc_ingest.py:5-30`).
- `evaluate()` does `if check["metric"] not in sample_metrics: continue`
  (`rule_pack.py:368-369`) — an absent slug emits **nothing**. And
  `evaluate_run_qc` returns `[]` on empty metrics (`run_qc.py:34-35`). So a
  wrong/missing slug is **invisible**: no PASS, no FAIL, no UNVERIFIED.
- Every slug in the three packs is annotated **"slug unverified"** in the source.
- `qc_ingest.parse_multiqc_general_stats` takes sample ids and metric keys
  **verbatim** — there is no aliasing/normalization today.

## The proven precedent (scrnaseq, v0.21.0) — the template

`runner.py:231-246` is the shape to copy. scrnaseq did **not** try to fix MultiQC
slugs — it added **dedicated on-disk artifact parsers** (`scrnaseq_metrics.py`
reading STARsolo `Summary.csv` / Cell Ranger `metrics_summary.csv`) behind a
per-assay gate that:
- runs `evaluate({sample: metrics}, PACK)` when metrics parse, else
- emits an **explicit UNVERIFIED** `QCResult(check=f"...:{sample}",
  status="unverified", kind="metric")` when the artifact is located-but-unparseable,
- and **silently skips** only when no artifact exists at all (structural QC owns the
  missing-output case).
Cell-Ranger-over-STARsolo precedence, floor principle (non-numeric omitted, never
guessed to 0), no HTML scraping.

## Affected areas / seams

- `src/contig/runner.py` — `_discover_qc` (add a per-assay gate + `_locate_*` +
  `_sample_from_*` helpers, mirroring `:90-107` and `:231-246`).
- `src/contig/verification/` — likely NEW `methylseq_metrics.py` (then
  `ampliseq_metrics.py`, `mag_metrics.py`) mirroring `scrnaseq_metrics.py`; OR a
  slug-alias layer in `qc_ingest.py` (see the fork below).
- `src/contig/verification/rule_pack.py` — packs unchanged if new parsers emit the
  canonical slugs; tighten "slug unverified" comments once confirmed.
- `tests/verification/` — NEW `test_methylseq_metrics.py` + a methylseq gate block
  in `test_run_qc.py` (mirror `:531-649`); inline synthetic fixtures.
- Registry (`registry.py:67-87`) already wires the three assays (`methylseq`,
  `ampliseq`, `mag`); structural manifests (`structural.py:265-275`) already fire —
  only the **biological metric packs** are hollow. No `models.py` / `overall_verdict`
  / `_RULE_PACKS` change needed.

## The key architecture fork (for the PRD interview)

Where do the metrics come from?

- **Option A — slug aliasing in the MultiQC path.** If Bismark/DADA2/QUAST *do*
  route these metrics into MultiQC general-stats (just under different key names),
  add a tolerant per-metric alias set so the pack matches. Smaller change; still
  needs a per-assay gate to emit explicit UNVERIFIED when the keys are absent.
- **Option B — dedicated artifact parsers (the scrnaseq pattern).** Parse the
  tool's own on-disk report files (Bismark `*_PE_report.txt` /
  `deduplicate_bismark` report; DADA2 stats table; QUAST `report.tsv` + CheckM tsv)
  into canonical slugs behind a gate. Provably robust — does not depend on the base
  pipeline routing to general-stats (the exact assumption that broke scrnaseq).
  More per-assay work.

**Lean:** Option B for methylseq, because it is the proven-robust pattern and the
whole point is to stop depending on the fragile general-stats assumption.
`percent_bs_conversion` in particular is commonly **absent** from Bismark
general-stats, which is a concrete argument against Option A. But this is a real
decision the interview should confirm, ideally against a real report layout.

## Fixture caveat (dig-confirmed)

CI never runs nf-core/methylseq/ampliseq/mag, and **no real methylseq/ampliseq/mag
MultiQC or report artifact exists locally** — the only `multiqc_data.json` files on
disk are RNA-seq/variant runs (same `report_general_stats_data` schema:
`[ {sample: {metric_key: value}} ]`). So slugs/report layouts must be pinned from
**realistic hand-authored fixtures** shaped like real nf-core output (in-pattern:
commit `5cedaaa` did this for sarek annotation). The explicit-UNVERIFIED breadcrumb
is the safety net: even an unconfirmed slug fails **loudly**, never silently.

## Open questions for the interview

1. Option A (alias) vs Option B (dedicated parsers) — confirm B, or A where a metric
   is genuinely in general-stats?
2. Scope of the first shippable slice: **methylseq only** (recommended, depth-first)
   or all three at once?
3. Which Bismark artifact is authoritative for each metric (report file vs MultiQC),
   and can we confirm `percent_bs_conversion`'s real source at all offline?
4. Bands unchanged (WARN/FAIL-capped, uncalibrated) — confirm no recalibration in
   this slice (FAIL-severity calibration is separately deferred).

## Guardrail check

Pure Layer-2 verification hardening (C3). No Layer-1, no raw-read egress (parsers
read small summary/report files on the user's compute), no over-claiming
(UNVERIFIED never rendered as PASS). Clean.

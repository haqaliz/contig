# PRD: Single-cell RNA-seq metric ingestion — make the scrnaseq verdict fire

- **Slug:** `single-cell-plausibility`
- **Branch:** `feat/single-cell-plausibility/aliz`
- **Capability:** C3 (biological-plausibility verification), single-cell slice
- **Type:** feat · **Owner:** aliz · **Source:** inline brief via `contig-next` (2026-07-07)
- **Status:** PRD for review (Phase 4 gate pending)

---

## Problem Statement

Single-cell RNA-seq (`scrnaseq`) is a shipped Contig assay, and it **already has a
biological QC pack** — `SCRNASEQ_RULE_PACK` (`rule_pack.py:87–116`) scoring
`estimated_cells`, `median_genes_per_cell`, `fraction_reads_in_cells`, and
`pct_reads_mito`, registered in `_RULE_PACKS` and run via `rule_pack_for("scrnaseq")`.

**The pack silently never fires on a real run.** Its metrics are read only from
MultiQC `general_stats` (`parse_multiqc_general_stats_file`), but the cell-level
single-cell QC does not land there:

- The pinned `nf-core/scrnaseq@4.1.0` defaults to the **`simpleaf`/alevin-fry**
  aligner, whose cell QC is emitted as standalone **AlevinQC/QCatch** output, not
  MultiQC general-stats.
- MultiQC's stock **STAR module does not parse STARsolo `Summary.csv`**, so STARsolo
  cell metrics never reach general-stats either.
- Only the **Cell Ranger** MultiQC module surfaces these columns — and Cell Ranger is
  licensed, the least-used path for our ICP.

Because `evaluate()` (`rule_pack.py:332–351`) **silently skips any absent metric**, the
scrnaseq verdict degrades to UNVERIFIED on an out-of-the-box run. The checks read as
"wired" but produce no signal. Separately, `pct_reads_mito` requires downstream
**scanpy** (`pct_counts_mt`), which the base pipeline never runs — so that check is
dead on *every* aligner path.

**This is a verification hole, not a missing feature.** The moat is the verified
verdict; a verdict axis that silently no-ops is worse than none, because it looks
covered. Fixing it means **ingesting the cell-level QC the pipeline actually writes to
disk** so the existing checks evaluate on real data.

### Evidence it's real
- `runner.py:114–120` — scrnaseq has no metric source beyond MultiQC general-stats.
- Dig research: `nf-core/scrnaseq@4.1.0` default aligner is `simpleaf`; STARsolo
  `Summary.csv` and Cell Ranger `metrics_summary.csv` carry the cell metrics on disk but
  are not routed to MultiQC general-stats. (See `_card/understanding.md`.)
- `test_rule_pack.py:203–278` exercises the scrnaseq pack only with hand-authored metric
  dicts — there is no fixture proving the metrics are ever ingested from a real artifact.

---

## Goals & Success Metrics

**Goal:** a single-cell run's cell-level QC metrics reach the verdict, so
`SCRNASEQ_RULE_PACK` emits real PASS/WARN/FAIL/UNVERIFIED instead of silent skips —
across the STARsolo, Cell Ranger, and (best-effort) default simpleaf paths.

| # | Success criterion | Measured by |
|---|---|---|
| S1 | A synthetic STARsolo `Summary.csv` fixture yields the four metrics keyed by sample and drives the pack to the expected statuses | new parser + runner-gate tests |
| S2 | A synthetic Cell Ranger `metrics_summary.csv` (comma-thousands, `%` values) parses to the same slugs and drives the pack | parser tests |
| S3 | The default simpleaf/alevin-fry path yields metrics **when its artifact is recognized**, and **UNVERIFIED (never a false pass)** when it is not | parser + gate tests |
| S4 | A grossly-failed capture (near-empty cells) FAILs the verdict; a healthy one PASSes; a missing/absent metric is UNVERIFIED | runner-gate tests |
| S5 | No regression: the full suite stays green; other assays' `_discover_qc` behavior is unchanged | `uv run pytest` |
| S6 | Zero false passes and no raw-read egress: parsers read only small text/HTML QC files on the user's compute | design + tests |
| S7 | On a synthetic run dir per aligner, the gate emits ≥1 non-UNVERIFIED metric for **STARsolo** and **Cell Ranger**; **simpleaf may legitimately be all-UNVERIFIED** if no structured artifact is confirmed (R1) | runner-gate tests |

**Non-metric success:** the scrnaseq verdict stops being silently dormant — the
single most important qualitative outcome.

---

## User Personas & Scenarios

- **A — lone computational biologist** runs `nf-core/scrnaseq` through Contig on a 10x
  dataset. Today the verdict says nothing about cell recovery or ambient contamination;
  after this, a near-empty capture or a droplet-dominated run is caught and named.
- **C — core facility** runs many single-cell samples and needs a consistent, auditable
  per-sample verdict, not a silent UNVERIFIED that looks like coverage.
- **B — wet-lab scientist who can't code** gets a plain PASS/WARN/FAIL on "did enough
  cells come through," instead of a blank.

---

## Requirements

### Must-have (this slice)

- **M1 — STARsolo `Summary.csv` parser.** A new `verification/scrnaseq_metrics.py`
  parses STARsolo's per-sample `Summary.csv` (two-column, no header) into
  `{sample: {slug: float}}`, mapping the documented fields to the pack's slugs:
  `Estimated Number of Cells → estimated_cells`, `Median Gene per Cell →
  median_genes_per_cell`, `Fraction of Unique Reads in Cells → fraction_reads_in_cells`.
  Sample id derived from the enclosing STARsolo output directory. Unrecognized/malformed
  rows are skipped, never guessed.
- **M2 — Cell Ranger `metrics_summary.csv` parser.** Parse Cell Ranger's single-row CSV
  (header + values, **comma thousands separators and `%`-suffixed values**) to the same
  slugs (`Estimated Number of Cells`, `Median Genes per Cell`, `Fraction Reads in
  Cells`), coercing `"1,234"`→1234.0 and `"92.3%"`→0.923 (fraction) / 92.3 (percent) per
  the slug's expected unit. Unit handling must match the pack's band units exactly.
- **M3 — simpleaf/alevin-fry best-effort parser (floor = degrade).** The **guaranteed
  deliverable** is: recognize a structured QCatch/alevin-fry artifact **if one exists**
  and otherwise **emit nothing → UNVERIFIED, never a false pass.** How much more than the
  floor M3 delivers is gated by a **tech-plan spike** confirming what structured artifact
  `nf-core/scrnaseq@4.1.0` simpleaf actually writes (R1). M3 is NOT allowed to become an
  HTML-scraping effort that blocks the slice; if no structured source exists, the floor
  (UNVERIFIED) is the accepted outcome and STARsolo/Cell Ranger (M1/M2) carry the slice.
  The fragility of this path is isolated so it can never affect M1/M2.
- **M4 — Wire ingestion into `_discover_qc`.** A scrnaseq gate locates the cell-level QC
  files under the run dir (by aligner-specific filename/dir signature), parses them
  (M1–M3), and evaluates `SCRNASEQ_RULE_PACK` over the merged metrics — mirroring the
  dedicated germline VCF gate rather than the MultiQC path. Gated strictly to
  `assay == "scrnaseq"`; other assays untouched.
- **M5 — Remove the dead `pct_reads_mito` check** from `SCRNASEQ_RULE_PACK` (base
  pipeline never produces it; keeping it is a silent-dead check that misleads). Record
  it as deferred (needs downstream scanpy).
- **M6 — Keep FAIL severity** on the grossly-failed-capture bands (`estimated_cells`
  fail_below, `fraction_reads_in_cells` fail_below, `median_genes_per_cell` fail_below),
  consistent with sibling did-it-run packs (methylseq/ampliseq/mag). No re-posture to
  WARN. The bug was ingestion, not severity.
- **M7 — Test-first, synthetic fixtures only.** Every parser and the gate is covered by
  synthetic `Summary.csv` / `metrics_summary.csv` / alevin-fry fixtures. **No real
  nf-core/scrnaseq run in CI.** Zero-false-pass and UNVERIFIED-when-absent are explicit
  test cases.

### Should-have (adjacent, not blocking)

- Multi-sample handling: several per-sample QC files under one run → one metrics entry
  per sample, so check naming (`check:sample`) and any cross-sample view line up with
  how MultiQC keys samples.
- **Multi-output disambiguation:** a run dir may contain more than one aligner's outputs.
  State and test the selection rule — the gate reads the artifact matching the run's
  configured aligner (by filename/dir signature), and if multiple candidates for the same
  sample exist, it prefers the aligner-native artifact deterministically rather than
  merging them. Covered by a fixture with two aligner outputs present.
- A short methods/report note that scrnaseq QC is sourced from the aligner's cell-QC
  artifact (provenance honesty about where the numbers came from).

### Nice-to-have (explicitly deferred)

- A separate WARN-capped `SCRNASEQ_PLAUSIBILITY_PACK` for softer biological bands beyond
  the did-it-run pack. Not needed once ingestion works; would add a redundant path now.
- `pct_reads_mito` / doublet-rate once a downstream scanpy/scDblFinder step exists.
- Sequencing-saturation and mean-reads-per-cell checks.
- Calibrating the bands on real data (they stay illustrative engineering defaults).

---

## Technical Considerations

- **Where it sits:** verify layer only (Layer 2). No planner/run changes; additive to
  `_discover_qc`. No new `FailureClass`, detector-corpus, or persisted-record change —
  matching how the RNA-seq plausibility slice shipped (v0.6.0).
- **Data contract:** parsers return `{sample: {slug: float}}`, the exact shape
  `evaluate()` consumes. Slug set for this slice: `estimated_cells`,
  `median_genes_per_cell`, `fraction_reads_in_cells`.
- **Wiring choice:** evaluate the pack over parsed cell-QC in a dedicated scrnaseq gate
  (like the germline VCF gate), and **drop `scrnaseq` from the MultiQC-driven
  `_RULE_PACKS` path** (it never carried usable data there) to avoid a dead double-path.
  Confirm in tech-plan that this removal doesn't affect other call sites of
  `rule_pack_for`.
- **Unit correctness:** Cell Ranger reports `Fraction Reads in Cells` as a `%` string;
  STARsolo reports it as a 0–1 fraction. The parsers must normalize to the unit the pack
  band expects (`fraction_reads_in_cells` warn_below 0.7 → a 0–1 fraction). A unit
  mismatch would silently mis-verdict — cover with an explicit test per path.
- **Sample identity:** derive a stable sample id from the aligner output dir so results
  key consistently; document the derivation.
- **Reproducibility/verification impact:** turns a dormant verdict live; strengthens the
  verified-verdict moat and captures per-assay metric distributions (eval corpus). No
  raw-read egress — QC artifacts are small summary files on the user's compute.

---

## Risks & Open Questions

- **R1 (accepted) — simpleaf/alevin-fry source is fragile.** The default path emits HTML
  (AlevinQC) or evolving QCatch output; there may be no stable structured field for every
  metric. **Mitigation:** parse the most structured artifact available, degrade to
  UNVERIFIED on anything unrecognized (never a false pass), and isolate this path so its
  fragility can't affect the STARsolo/CellRanger paths. **Open:** confirm during
  tech-plan exactly which structured artifact `nf-core/scrnaseq@4.1.0` simpleaf writes
  (QCatch JSON? permit-list JSON? h5ad-derived?) — this determines how much M3 can
  actually deliver vs. degrade.
- **R2 — exact slug/field spellings unverified.** STARsolo/Cell Ranger field labels vary
  by version. **Mitigation:** map on documented field names, tolerate absence, and lean
  on UNVERIFIED-when-absent. Fixtures pin the mapping we build against.
- **R3 — the metrics still may not fire on many real runs** if users stay on the default
  aligner and R1 degrades. Honest framing: the verdict is then UNVERIFIED (correct), not
  a false pass. If field telemetry later shows most runs are simpleaf and degrade, that's
  the signal to invest further in the simpleaf source (a follow-on).
- **R4 — `_RULE_PACKS` removal blast radius.** Dropping scrnaseq from the MultiQC-driven
  registry must not break `rule_pack_for` callers or other assays. Covered by S5 + a
  targeted test.

---

## Out of Scope

- Any Layer-1 workflow authoring.
- Doublet-rate and mitochondrial-fraction checks (need a downstream compute path the base
  pipeline doesn't run).
- Calibrating bands on real data; changing FAIL/WARN thresholds beyond removing the dead
  mito check.
- A real nf-core/scrnaseq execution in CI.
- Single-cell cross-tool concordance (C1) — separate capability.

---

## Artifact / Run Contracts

- **New module:** `src/contig/verification/scrnaseq_metrics.py` — pure parsers, no I/O
  beyond reading the passed QC file(s), no network, deterministic.
- **Changed:** `src/contig/verification/rule_pack.py` (remove `pct_reads_mito`; drop
  scrnaseq from `_RULE_PACKS` if adopting the dedicated-gate wiring),
  `src/contig/runner.py` (`_discover_qc` scrnaseq gate + import).
- **Tests:** `tests/verification/test_scrnaseq_metrics.py` (new, per parser),
  updates to `tests/verification/test_rule_pack.py` (mito removal) and
  `tests/verification/test_run_qc.py` (scrnaseq gate: fires / degrades / other-assay
  untouched).
- **No change:** persisted `RunRecord` schema, detector corpus, CLI surface.

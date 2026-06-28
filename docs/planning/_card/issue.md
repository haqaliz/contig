# rnaseq-plausibility (extend biological-plausibility verification from germline to bulk RNA-seq)

- **Type:** feat
- **Id/slug:** rnaseq-plausibility
- **Owner:** aliz
- **Branch:** feat/rnaseq-plausibility/aliz
- **Source:** inline brief (no GitHub issue; handed off from `contig-next`)

## Brief

Extend biological-plausibility verification (capability **C3**) from germline to
**bulk RNA-seq**, the lead/highest-TAM assay.

- Add RNA-seq plausibility rules to `RNASEQ_RULE_PACK`
  (`src/contig/verification/rule_pack.py`) — start with rRNA-contamination
  fraction and duplication/exonic sanity — and make sure their metrics actually
  reach the verdict, mirroring the germline `variant_metrics.py` pattern.
- **Caveat to resolve first in the dig:** check which of these metrics
  nf-core/rnaseq's MultiQC general-stats already carries (ingested via
  `qc_ingest.py`) versus which need a new compute path; ship the MultiQC-carried
  ones this slice and defer gene-body-coverage evenness if it needs a new
  computation.
- Keep rules **WARN-capped** (no FAIL until calibrated on real data), degrade to
  **UNVERIFIED (never PASS)** when a metric is absent, build **test-first** with
  fixtures inside/outside each band, and seed the eval corpus per the C3 pattern.

## Provenance / why this is next (from contig-next ranking)

- Cleanest, lowest-risk follow-on of the just-shipped C3 germline slice
  (CHANGELOG §0.3.0; `docs/technical/CAPABILITY_ROADMAP.md:144-153` lists rRNA
  RNA-seq as deferred to a later slice).
- The machine already exists: `verification/variant_metrics.py` proved the
  metric→rule→verdict path; `RNASEQ_RULE_PACK` is the slot to fill — today it
  holds only generic mapping-rate checks, no biological-plausibility rules.
- Deepens moat #1 (verdict gets smarter about biology) on the highest-TAM assay
  (RNA-seq DE, `docs/ROADMAP.md:44-49`). Captures eval data; gets better as base
  models adjudicate borderline bands.

## Known caveat to settle in the dig

The germline slice needed a **new compute path** (`variant_metrics.py` from the
VCF) because MultiQC didn't carry Ti/Tv reliably. For RNA-seq, confirm which
plausibility metrics nf-core/rnaseq's MultiQC general-stats already carries
(ingested via `qc_ingest.py`) vs. which need a new BAM/RSeQC-derived computation.
Start with MultiQC-carried metrics (rRNA-contamination fraction, duplication,
exonic/assignment sanity); **defer gene-body-coverage evenness** if it requires a
new compute path.

## Open questions for the interview

- Exact metric keys nf-core/rnaseq's MultiQC emits and which `qc_ingest.py`
  already surfaces (e.g. `percent_rRNA`, `percent_duplication`, exonic fraction).
- Which plausibility checks ship this slice vs. defer (gene-body-coverage evenness
  pending feasibility).
- WARN bands for each metric (illustrative engineering defaults, like the germline
  Ti/Tv / het/hom bands) — values + sources.
- Corpus: one golden RNA-seq plausibility case per new check, or a representative
  set? (Brief leans: seed per the C3 pattern.)
- Surface footprint: QC panel grouping only (like germline), or also a verdict
  line? (Lean: match the germline slice.)

## Guardrails (CLAUDE.md)

- Layer 2 only (verify); no Layer-1 workflow authoring.
- No raw-read egress; runs on the user's compute.
- No correctness over-claiming: WARN-capped, UNVERIFIED never rendered as PASS,
  scoped honestly per assay.
- Test-first.

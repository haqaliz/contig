# C3, Biological-plausibility verification

Source: no GitHub issue. Inline brief, owner `aliz`, branch `feat/bio-plausibility/aliz`.
Origin: `docs/technical/CAPABILITY_ROADMAP.md` capability C3, plus the engine
investigation captured earlier this session.

## Brief

Deepen the verified verdict with **assay-aware biological sanity checks**: encode
what a biologically reasonable result looks like for each assay, beyond the generic
metric thresholds already in the rule packs. This is the verification layer getting
smarter about biology, the judgement incumbents leave to the human.

Candidate checks per assay (illustrative, tunable engineering defaults, NOT clinical
claims):
- RNA-seq: rRNA-contamination fraction within expected bounds, exonic/gene-body
  coverage sanity, duplication/library-complexity sanity.
- Germline variants: Ti/Tv ratio in the expected range for the capture, het/hom
  ratio sanity, expected variant-count band, optional sex-check concordance.
- Single-cell RNA-seq: doublet-rate band, mitochondrial-fraction distribution,
  knee-point sanity on the barcode-rank curve, recovered-cell band.

Each check is conservative, names its evidence, and degrades to UNVERIFIED (never
PASS) when the inputs the check needs are absent. Honesty scoped per assay.

## Why it is the moat

This is verification getting smarter about biology, exactly the judgement
incumbents punt to the human. It composes with the QC rule packs and the new C1
concordance axis: more ways the verdict is hard to fool, all feeding the
evaluation corpus.

## Investigation findings (from the session, to confirm in Phase 2)

- `src/contig/verification/rule_pack.py` is **data, not code**: per-assay rule
  packs (`rule_pack_for(assay)`), evaluated by `evaluate(metrics, pack)`. Existing
  thresholds are explicitly "illustrative, tunable, not clinical".
- So most plausibility checks are likely **new declarative rule entries** in the
  existing pack structure, plus a few new metric extractors where the needed metric
  is not already parsed from MultiQC.
- Metrics come from MultiQC via `verification/qc_ingest.py`
  (`parse_multiqc_general_stats_file`); `run_qc.py` ties ingestion to the pack.
- A plausibility result is just a `QCResult` (kind defaults to "metric"); it flows
  through `overall_verdict` like any other check. Note: `QCStatus` now includes
  "unverified" (added by C1), which is exactly what an absent-metric check needs.

## Scope guardrails (CLAUDE.md / FEATURES.md / USE_CASE_UNIVERSE.md)

- No clinical claims. A check means "biologically plausible for this assay", scoped
  honestly; UNVERIFIED when the metric is missing, never a false PASS.
- No Layer-1 authoring. No raw-read egress. Engineering-defensible defaults only.
- Test-first: every check lands with its failing test first.

## Open questions for the interview

- Which assay to lead with for slice 1 (germline Ti/Tv is a clean, well-known
  check; RNA-seq rRNA is also clean). Depth-first on one, then extend.
- Are the needed metrics already in the MultiQC general-stats parse, or do some
  need a new extractor?
- A new QC `kind` for plausibility (like concordance got), or do these stay
  kind="metric" but live in a separate, clearly-labelled pack?
- Exact conservative default bands per check, and the WARN vs UNVERIFIED vs FAIL
  policy (slice 1 likely WARN-or-unverified only, mirroring how concordance stayed
  conservative).

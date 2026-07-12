# Card: feat / scrnaseq-concordance

- **Type:** feat
- **Id/slug:** scrnaseq-concordance
- **Owner:** aliz

No GitHub issue — this unit of work came from a `/contig-next` recommendation.
Source of truth for the pipeline is the inline brief below.

## Brief

Add the single-cell RNA-seq cross-tool concordance axis (capability C1) to the
verdict, filling the last unimplemented concordance slot. Concordance already ships
for germline (`concordance.py`, `--concordance-vcf`/`--concordance-auto`), RNA-seq
(`count_concordance.py`, `--concordance-counts` + kallisto autorun
`--concordance-counts-auto`), somatic (`somatic_concordance.py`, auto in the verdict),
and annotation (`annotation_concordance.py`, VEP-vs-SnpEff). Single-cell is named as
deferred in every C1 list (`CAPABILITY_ROADMAP.md:58,73,117`).

**First slice only:** a `contig verify --concordance-counts-sc <matrix>` flag that
corroborates the run's own `scrnaseq` cell×gene matrix against a user-supplied second
matrix via a **pseudobulk gene-level Spearman + fraction-agreeing** check, reusing
`verification/count_concordance.py` and the `scrnaseq` discovery gate from
`verification/scrnaseq_metrics.py`. Keep it mutually exclusive with the other four
concordance flags.

**Honest contract (standing concordance contract, non-negotiable):** at most WARN,
never changes the `verify` exit code, `unverified` (never a false pass) below the
shared-gene floor.

## Scope caveat to respect (from the contig-next handoff)

The roadmap's *full* vision for single-cell concordance is "cell-count and
cluster-stability agreement across two quantifiers" (`CAPABILITY_ROADMAP.md:117`).

- **Defer cluster-stability agreement** — it needs a downstream clustering step Contig
  doesn't run (same blocker as single-cell doublet/mito plausibility).
- **Defer the second-quantifier autorun** (a `--concordance-counts-sc-auto` mirroring
  kallisto v0.24.0) — a second single-cell quantifier's barcode/cell-calling has no
  clean CI story.

Ship the **user-supplied matrix-correlation** slice test-first with synthetic matrices
and **no real tool in CI**. One consequence to acknowledge in the PRD: single-cell users
may not have a second matrix on hand, so immediate turnkey value waits for the autorun
follow-on — this first slice establishes the axis and the contract.

## Guardrails (CLAUDE.md)

- Layer-2 only (run/self-heal/verify/reproduce). This is verification depth — on-thesis.
- No raw-read egress: the concordance compares gene-count metrics on the user's compute.
- No correctness over-claiming: concordance is corroboration, at most WARN; UNVERIFIED is
  never rendered as PASS.
- Test-first: every capability lands with its failing test written first.

## Reusable machinery confirmed to exist (Phase 0 recon)

- `src/contig/verification/count_concordance.py` — RNA-seq gene-matrix Spearman /
  fraction-agreeing / shared-gene floor. Direct reuse target.
- `src/contig/verification/count_quantifier.py` — kallisto autorun seam (autorun pattern
  reference, deferred here).
- `src/contig/verification/scrnaseq_metrics.py` — v0.21.0 cell-QC ingestion; the
  `scrnaseq` `_discover_qc` gate + artifact-location pattern to mirror.
- No existing `docs/planning/scrnaseq-concordance/` dir — genuinely pending, not shipped.

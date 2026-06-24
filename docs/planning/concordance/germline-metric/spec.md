# Aspect spec: germline-metric (concordance slice 1)

Parent PRD: `../prd.md`. One buildable aspect: the deterministic germline
genotype-concordance metric, its verdict integration, a thin CLI surface, and the
report grouping.

## Problem slice and outcome

Given a germline run's primary VCF and a second call set supplied by the user,
emit two `kind="concordance"` QC checks (genotype concordance over shared sites,
and site overlap) that participate in the verdict at most as WARN, and surface
them in `contig verify`/`show` and the HTML report.

## In scope
- `concordance` added to `QCKind`.
- `verification/concordance.py`: a minimal deterministic VCF parser, the metric,
  and a `_concordance()` tagging helper.
- Assay-gated evaluation entry point (germline `variant_calling` only).
- `contig verify --concordance-vcf <path>` entry point.
- Report surfacing (text + HTML grouping).
- Dashboard `QCKind` type + QC panel grouping (should-have).

## Out of scope
- Auto-running a second caller; RNA-seq/single-cell concordance; FAIL severity;
  VCF normalization beyond the literal site key; clinical interpretation.

## Acceptance criteria (testable)
- A concordant VCF pair yields a PASS `genotype_concordance` check; a divergent
  pair yields WARN; both compared call sets are identified in the output.
- Two call sets with no shared sites yield an `unverified` `genotype_concordance`
  check (never PASS, no 0/0 crash) and a WARN `site_overlap` of 0.0.
- A WARN concordance result drops `RunRecord.verdict` to at most WARN, never FAIL.
- `contig verify --concordance-vcf` emits the checks against the run's primary VCF.
- HTML report groups concordance under its own heading, apart from metric and
  structural.
- Full suite stays green (726 passing at branch point).

## Dependencies and sequencing
- No external deps. Pure-Python parsing of small VCFs (plain and gzip).
- Sequence: metric (foundation) -> gating/wiring -> CLI -> report -> dashboard.

## Open questions / risks
- Conservative WARN thresholds (default 0.90 for both, tunable, documented).
- VCF representation differences (normalization) deferred; literal site key only.

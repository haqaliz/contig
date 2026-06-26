# concordance-autorun (turnkey cross-tool concordance)

Source: no GitHub issue. Inline brief, owner `aliz`, branch `feat/concordance-autorun/aliz`.
Origin: follow-on slice to C1 (CAPABILITY_ROADMAP.md), which shipped in v0.2.0.

## Brief

C1 cross-tool concordance shipped a deterministic metric, but the user must
**supply** the second call set themselves (`contig verify --concordance-vcf
<vcf>`). This slice makes concordance **turnkey**: Contig runs a second,
independent variant caller (for example `bcftools call`) on the same input as the
primary germline run, then compares the two call sets with the existing
concordance machinery, with no user-supplied VCF.

Reuses what C1 shipped: `verification/concordance.py` (`parse_vcf`,
`genotype_concordance`, `concordance_results`, `evaluate_concordance`). The new
work is producing the second VCF by executing a tool, and wiring that into the
verify/run path.

## Why it is the moat

Completes the concordance story into something usable without manual prep, and
keeps capturing cross-tool agreement data. Still Layer 2 (run and verify), not
Layer 1.

## The wrinkle (key design tension)

Executing a real second caller (bcftools) introduces a **tool/runtime dependency
and nondeterminism** into a path that has been deterministic and test-only so far.
The whole engine's test suite runs with no tool execution and no network. So slice
1 must make the second-caller execution **pluggable / injectable**, so tests use a
fake caller (or a recorded VCF) and never actually shell out, while real runs use
bcftools. Mirrors how the executor is injected in `runner.py`.

## Scope guardrails (CLAUDE.md / FEATURES.md)

- No raw-read egress; the second caller runs on the user's compute.
- Concordance stays at most WARN, corroboration not ground truth, unverified on no
  shared sites. No clinical claim.
- Test-first; no real tool execution in tests.

## Open questions for the interview

- Which second caller to standardize on (bcftools call is light and ubiquitous;
  DeepVariant is heavier). Likely bcftools for slice 1.
- Where it runs: a new `contig verify --concordance` (auto) flag, or inside the
  run pipeline after a germline run finishes. Probably a CLI flag first.
- The injection seam for the second caller so tests never execute it.
- What inputs the second caller needs (the aligned BAM + reference) and whether a
  finished germline run bundle carries them.

# Card — feat/rnaseq-concordance

**Type:** feat · **Owner:** aliz · **Branch:** `feat/rnaseq-concordance/aliz`

No GitHub issue — source is the inline brief carried from `contig-next` (2026-07-02).

## Brief

Add one independent axis to the RNA-seq verdict: **cross-tool quantification
concordance**, the RNA-seq slice of capability **C1** (germline shipped in v0.2.0;
see `docs/technical/CAPABILITY_ROADMAP.md:70-71`).

Compute **per-gene Spearman rank correlation** and the **fraction of genes agreeing
within a tolerance** between the run's primary count matrix and a second count
matrix supplied via a new `contig verify --concordance-counts <matrix>` flag,
emitting `kind="concordance"` QCResults that are **WARN-capped** (corroboration,
not ground truth) and report **`unverified`** (never a false pass) when the two
matrices share no comparable genes — mirroring the shipped germline
`--concordance-vcf` path.

Build **test-first** with synthetic count-matrix fixtures:
- concordant pair → PASS with the metric reported,
- divergent pair → WARN naming the metric and both quantifiers,
- no shared genes → UNVERIFIED.

No network, no raw-read egress.

## Caveat to dig on first

`src/contig/verification/concordance.py` is genotype/VCF-specific today — its own
comment (`concordance.py:35-36`) even says "an RNA-seq quantification has no
genotypes to agree on." So this is a **genuinely new count-concordance code path**
(Spearman + fraction-within-tolerance over two count matrices), **not** a one-line
`_CONCORDANCE_ASSAYS` addition, and that comment must be updated.

Honest scope for **slice 1**: the deterministic computation plus a user-supplied
`--concordance-counts <matrix>` flag over the run's primary count matrix.
**Auto-running a second quantifier** (e.g. Salmon vs STAR+featureCounts) is the
**deferred follow-on**, exactly as the germline autorun followed one release later
(v0.4.0).

## Guardrails (CLAUDE.md)

- Layer-2 only (verify/corroborate), never Layer-1 workflow authoring.
- No raw-read egress; deterministic; synthetic fixtures (no real nf-core run in CI).
- No over-claiming: WARN-cap, UNVERIFIED-never-PASS.

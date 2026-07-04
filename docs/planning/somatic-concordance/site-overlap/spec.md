# Aspect spec: site-overlap (somatic Strelka2-vs-Mutect2 PASS-site concordance)

Parent PRD: `docs/planning/somatic-concordance/prd.md`. This is the sole aspect of the
feature — the one honest metric slice-1 emits.

## Problem slice & user outcome

A somatic run's verdict gains an automatic cross-tool concordance line: the fraction of
confident (PASS) calls the run's Mutect2 and Strelka2 callers agree on, keyed on the
literal variant site. The user sees "corroborated by a second caller" without running or
supplying anything.

## In scope

- A new `verification/somatic_concordance.py` computing **PASS-site overlap** (Jaccard over
  `(CHROM,POS,REF,ALT)` of FILTER-PASS records) between the Mutect2 and Strelka2 call sets.
- FILTER-aware parsing (`FILTER ∈ {"PASS", "."}`); union of Strelka's split SNV+indel files.
- One `kind="concordance"` check, WARN-capped, UNVERIFIED below a min-total-PASS-sites floor.
- Auto-wiring into `runner.py:_discover_qc` somatic branch, alongside the existing VAF
  plausibility block, reusing the already-globbed VCF list.
- Deterministic caller/pair selection; **UNVERIFIED (not an arbitrary pick)** when more than
  one tumor–normal pair directory is present.

## Out of scope

- Tumor-VAF agreement, genotype concordance, variant normalization/left-alignment.
- FAIL severity; an explicit `contig verify` flag/echo; model changes; corpus/FailureClass.

## Acceptance criteria (testable)

1. Concordant pair (identical PASS sites) → `somatic_site_overlap` **pass**, value ≈ 1.0.
2. Divergent pair (little overlap) → **warn**, value below the threshold; exit code unchanged.
3. Union PASS sites below the floor → **unverified** (no severity), never pass.
4. A non-PASS record is excluded from both sets (FILTER filtering proven).
5. Strelka split files (`*.somatic_snvs.vcf.gz` + `*.somatic_indels.vcf.gz`) are unioned.
6. Gzipped inputs parse identically to plaintext.
7. mutect2-only / strelka-only / non-somatic run → no concordance result (clean skip); the
   somatic VAF-plausibility path is unaffected.
8. Two distinct `<tumor>_vs_<normal>` pair dirs → a single UNVERIFIED, no arbitrary compare.
9. The result appears in the somatic verdict's QC results and never changes the exit code.
10. Full suite green; no network, no tool execution.

## Dependencies & sequencing

Module (Phase 1) before wiring (Phase 2). No new packages. Mirrors `concordance.py` /
`count_concordance.py` (shape) and `somatic_plausibility.py` (VCF location / gzip idiom).

## Open questions / risks (aspect-specific)

- Concrete threshold + floor values — set in the plan with a one-line rationale (WARN-capped,
  absorbed by the UNVERIFIED-below-floor guarantee).
- Representation differences between callers lower literal-site overlap — disclosed, honest
  (reads as lower overlap → WARN, never a false pass); normalization deferred.

# PRD: Cross-tool concordance verification (C1)

Status: draft for review. Owner: aliz. Branch: `feat/concordance/aliz`.
Sources: `docs/planning/_card/issue.md`, `docs/planning/_card/understanding.md`,
`docs/technical/CAPABILITY_ROADMAP.md` (C1).

## Problem Statement

Today Contig's verified verdict rests on three signals: per-sample metric checks (a
rule pack over MultiQC), structural and integrity checks on the output files, and,
when a designated reference run exists, the `benchmark` comparison. None of these
catches **tool-specific error**: a caller that systematically mis-genotypes a class
of sites can still pass every threshold and produce structurally valid output, and
without a pre-existing reference run there is nothing to compare against.

Concordance closes that gap. Running a second independent tool on the same input
and measuring agreement is a standard way working bioinformaticians sanity-check a
call set, and no incumbent platform (Galaxy, Terra, DNAnexus, Seqera, Latch,
Basepair) issues a cross-tool correctness signal. It is a defensible, novel axis of
the verified verdict and a source of compounding evaluation data (agreement
distributions per assay).

This PRD scopes the **first slice**: a deterministic concordance metric over two
provided call sets for the germline variant assay, wired into the verdict. It does
**not** auto-run a second caller (a later slice).

## Goals & Success Metrics

- A new `concordance` QC kind exists and participates in `RunRecord.verdict`
  through the existing kind-agnostic reduction, with zero regression to the 726
  passing tests.
- For germline variants, `genotype_concordance(vcf_a, vcf_b)` returns a
  deterministic concordance rate over shared sites, plus a site-overlap figure,
  on synthetic fixtures with no tool execution and no network.
- A concordant pair yields a PASS concordance result; a divergent pair yields a
  WARN result that names both the metric and the two call sets, and drops
  `RunRecord.verdict` to at most WARN (never FAIL in this slice).
- The result is visible: `contig show` renders a "Concordance (cross-tool
  corroboration)" line, and the HTML report groups it apart from metric and
  structural checks.
- Honesty preserved: concordance never promotes an UNVERIFIED run to PASS, and the
  copy never claims "concordant means correct".

## User Personas & Scenarios

- **A, lone computational biologist**: has a germline VCF from Contig and a second
  call set (from another caller or a prior run) and wants a quick, recorded answer
  to "do these two agree, and where do they differ?" without writing a comparison
  script.
- **C, core facility**: wants the verdict to carry a corroboration signal a
  non-expert PI can read, so a passing run is visibly backed by more than one tool.
- **D, biotech researcher**: wants the concordance figure and the two compared
  call sets captured in provenance for the Methods record.

## Requirements

### Must-have (this slice)
- `concordance` added to `QCKind`; `QCResult.kind` continues to default to
  `metric` so existing records deserialize unchanged.
- `verification/concordance.py`: a `_concordance()` tagging helper and a pure,
  deterministic `genotype_concordance(vcf_a, vcf_b)` returning the concordance rate
  over shared sites and the site-overlap fraction.
- Two emitted checks per comparison: `genotype_concordance` (rate over shared
  sites) and `site_overlap` (fraction of sites shared), both `kind="concordance"`.
- **Empty-intersection behavior**: if the two call sets share no sites, the
  `genotype_concordance` check is `unverified` for that check (nothing was
  corroborated), never PASS and never a 0/0 crash. `site_overlap` still reports
  0.0 as a WARN (the two callers found disjoint sites, which is itself a signal).
- Verdict severity: low concordance and low overlap map to WARN at most; never
  FAIL in this slice. Thresholds are explicit, documented engineering defaults
  (not clinical claims), tunable like the rule packs.
- **User entry point (committed)**: `contig verify --concordance-vcf <path>` on the
  existing germline run supplies the second call set and emits the concordance
  checks against the run's primary VCF. This is the thin, standalone surface that
  makes the slice usable without re-architecting the run pipeline.
- Assay gating: concordance evaluation only engages for `variant_calling`; other
  assays are untouched.
- Surfacing: `contig show` (text) and `render_run_report_html` group concordance
  results under their own heading.
- The two compared call sets (their paths and hashes) are recorded so the result
  is reproducible and auditable.

### Should-have
- Dashboard `QCKind` type and QC panel updated to render the concordance group.

### Nice-to-have (explicitly later slices, not now)
- Auto-running a second caller (e.g. bcftools) to produce the second call set.
- RNA-seq quantification concordance (per-gene rank correlation) and single-cell.
- Promoting concordance to FAIL once thresholds are calibrated on real data.

## Technical Considerations

- **Verdict integration is free**: `overall_verdict` (`models.py:73`) reduces on
  `status` only, so a concordance result flows through unchanged. The work is the
  metric, the emission, the gating, and the surfacing.
- **Pattern**: mirror `verification/structural.py` (helper plus per-assay entry
  point) and wire through `verification/run_qc.py`, gated on assay exactly as
  `cross_sample` is today. Assay is already threaded via
  `runner.py:_discover_qc(run_dir, assay)`.
- **VCF parsing**: parse minimally and deterministically (CHROM, POS, REF, ALT,
  and the genotype) from small plain or gzipped VCF fixtures; no external bequest
  on a VCF library unless one is already a dependency. Treat a site key as
  (CHROM, POS, REF, ALT); genotype concordance compares the GT call at shared site
  keys.
- **Determinism and no network**: the slice runs entirely on provided files;
  fixtures are tiny inline VCFs, matching the `test_structural.py` and
  `test_run_qc.py` conventions (real `tmp_path` files, no mocks).
- **Reproducibility impact**: the compared call sets and the resulting figures
  belong in the bundle so a re-run reproduces the same concordance verdict.
- **Verification impact**: this strengthens the verified verdict; it must stay
  conservative (corroboration, at most WARN) to protect the near-zero false-pass
  rate.

## Data Model / Artifact Contracts

- `QCKind = Literal["metric", "structural", "concordance"]`.
- Concordance `QCResult`s use `check` names `genotype_concordance` and
  `site_overlap`, carry the numeric `value` (the rate or fraction) and an
  `expected_range`, and set `kind="concordance"`.
- The two compared call sets are identified (path plus checksum) in the run record
  or the concordance result message so the comparison is auditable.

## Risks & Open Questions

- **Over-claiming** (fatal to trust): mitigated by at-most-WARN and explicit "not
  ground truth" copy.
- **VCF representation differences** (normalization, multiallelic splitting, indel
  left-alignment) can make two callers look discordant when they agree
  biologically. Slice 1 compares on the literal site key; the PRD notes
  normalization as a known limitation to address before promoting to FAIL.
- **Threshold calibration**: defaults are illustrative until real-data
  distributions exist (this is exactly the eval data the feature captures).
- Open: exact default thresholds for `genotype_concordance` and `site_overlap`
  WARN bands (to set in the tech plan; deliberately conservative).
- Noted: slice 1 has the user supply the second VCF, so its standalone value
  depends on the user already having one. It is deliberately the deterministic
  foundation; the "auto-run a second caller" slice that follows is what makes
  concordance turnkey, and should be sequenced immediately after.

## Out of Scope

- Auto-running a second variant caller or any new pipeline execution.
- RNA-seq / single-cell concordance.
- FAIL-severity concordance.
- VCF normalization/harmonization beyond the literal site key.
- Any clinical interpretation of concordance.

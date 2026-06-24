# C1 concordance — Phase 2 understanding

Grounded by a graphify-first code-mapping pass. File:line anchors are against the
worktree (identical to master at branch point).

## What the work really asks

Add a third verification axis, **concordance**, alongside the existing metric and
structural checks: corroborate the primary result with a second independent tool
and let agreement or disagreement move the verdict honestly.

## Affected areas (confirmed)

- `src/contig/models.py:59` — `QCKind = Literal["metric", "structural"]`. Add
  `"concordance"`. `QCResult.kind` defaults to `"metric"` (line 70), so old records
  deserialize unchanged.
- `src/contig/models.py:73` `overall_verdict` — reduction is **kind-agnostic**
  (looks only at `status`). A concordance result with `warn`/`fail` flows through
  unchanged and contributes to `RunRecord.verdict`. No reduction rewrite needed.
- `src/contig/verification/concordance.py` — NEW module, mirroring
  `structural.py`: a `_concordance()` tagging helper (sets `kind="concordance"`),
  a deterministic metric function, and an `evaluate_*` entry point.
- `src/contig/verification/run_qc.py` — the wiring seam. Concordance is added like
  `cross_sample` is gated today (`evaluate_run_qc` / `run_qc`).
- `src/contig/runner.py:35` `_discover_qc(run_dir, assay)` and `run_pipeline(...,
  assay=...)` — assay is already threaded here; concordance gates off the same
  `assay` string. Assay ids in use: `rnaseq`, `variant_calling`, `scrnaseq`,
  `methylseq`, `ampliseq`, `mag`.
- `src/contig/report.py:258-265` — groups QC into metric vs structural; add a
  concordance group ("Concordance (cross-tool corroboration)").
- `dashboard/lib/types.ts:12` — mirror `"concordance"` into the TS `QCKind`; check
  the QC panel groups it.
- Tests to mirror: `tests/verification/test_structural.py`,
  `tests/verification/test_run_qc.py`, `tests/verification/test_cross_sample.py`
  (real files via `tmp_path`, no mocks, `test_<fn>_<scenario>` naming).

## The crux (contradiction to resolve in the interview)

`variant_calling` runs **nf-core/sarek with GATK only** (registry.py); its
structural manifest expects `*.vcf.gz` (structural.py:250-253). **There is no
second call set produced today.** So "two call sets in the same run" does not yet
exist. The first slice must decide where the second call set comes from:

- **A. Pure metric over two given call sets (recommended first slice).** Implement
  and test a deterministic `genotype_concordance(vcf_a, vcf_b)` and its QCResult
  emission, with the second call set supplied as an input path. Fully deterministic,
  no tool execution, no network, matches the repo's fixture style. Executing a
  second caller is a separate, later slice.
- **B. Execute a second caller (e.g. bcftools) as a post-run step.** Heavier,
  introduces tool/runtime dependency and nondeterminism into the test path.
- **C. Compare against a user-provided reference VCF.** Close to A mechanically,
  but overlaps conceptually with the shipped `benchmark` (reference run); keep
  concordance about *tools*, not reference runs.

Recommendation: **A** for slice 1. It delivers the novel verdict axis test-first
with zero new runtime dependencies; B (auto-running the second caller) follows.

## Open product questions (for Phase 3)

1. Confirm slice 1 = the pure metric over two call sets (option A), deferring
   second-caller execution.
2. Genotype-concordance metric definition: concordance rate over shared sites,
   and how to treat sites present in only one call set (the denominator choice).
3. WARN vs FAIL thresholds, and whether slice 1 is ever FAIL or at most WARN.
4. Which second germline caller we standardize on for the later auto-run slice
   (e.g. bcftools call vs DeepVariant).

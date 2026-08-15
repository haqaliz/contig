# Spec — annotation-cache-wiring / launch-wiring

## Problem slice and user outcome

The launch side of C7 enablement: a `contig run` (or rerun/resume) on either sarek
variant assay (`variant_calling`, `somatic_variant_calling`) assembles
annotation-cache params (`download_cache`, `outdir_cache`) into the run's params so
sarek 3.5.1 downloads its VEP/SnpEff cache and produces an annotated VCF — instead
of hard-failing at cache initialisation (`ANNOTATION_CACHE_INITIALISATION` calls
`error()` on a missing cache). Outcome: variant runs stop crashing at the
annotation step, and the shipped C7 verification axes fire on real data.

## In-scope requirements

- Per-dispatch enablement inside `_dispatch_run` (cli.py), gated to
  `engine == "nextflow"` and `resolved_assay in VARIANT_ASSAYS`:
  - `params.setdefault("download_cache", "true")` — string `"true"` (Groovy/nf-core
    boolean coercion; `str(True)` → `"True"` risks schema rejection).
  - `params.setdefault("outdir_cache", str(cache_dir.resolve()))` where
    `cache_dir = Path(runs_dir) / "caches" / "annotation" / f"{pipeline}@{revision}"`
    — shared, deterministic, outside the run dir (without it sarek publishes the
    cache into `${outdir}/cache/` inside the run bundle).
  - `cache_dir.mkdir(parents=True, exist_ok=True)` before launch; on `OSError`
    refuse up front (message + `typer.Exit(code=1)`), nothing launched.
- Setdefault semantics: a user-supplied value in the incoming params wins (future
  CLI flag contract).
- Rerun/resume re-injection is automatic (both re-enter `_dispatch_run`; params
  are not persisted in `LaunchManifest`).
- Tests mirroring `tests/test_run_default_params.py` patterns (scripted
  `self_heal_run` spy, CliRunner).

## Out-of-scope boundaries

- No CLI flag, no `LaunchManifest` field, no `models.py` change, no verifier
  change, no `--step annotate`, no user-supplied `--vep_cache`/`--snpeff_cache`,
  no PON/germline-resource wiring, no repair for a failed download.
- Not validating that VEP/SnpEff run correctly (nf-core's guarantee); the
  existing C7 fixture suite covers the verifier side unchanged.

## Acceptance criteria (testable)

1. A germline and a somatic sarek run (test-profile mode, spy executor) assemble
   `download_cache == "true"` and an absolute `outdir_cache` under
   `<runs_dir>/caches/annotation/nf-core/sarek@3.5.1/`; the dir exists on disk.
2. An rnaseq run assembles neither key and creates no `caches/` tree.
3. A rerun of the same id assembles the same params (deterministic path).
4. Pre-set user `download_cache`/`outdir_cache` values survive the merge.
5. An uncreatable cache dir exits 1 before `self_heal_run` is called, naming the
   path.
6. `build_nextflow_command` over the merged params yields argv tokens
   `--download_cache true` and `--outdir_cache <dir>`.
7. Full suite green; `tests/test_run_default_params.py` and
   `tests/test_somatic_end_to_end.py` unchanged-and-green (registry dicts
   untouched — no exact-dict pins trip).

## Dependencies and sequencing

- Single aspect, single implementer task (TDD RED→GREEN→REFACTOR), then a docs
  sync commit (CAPABILITY_ROADMAP.md C7 caveat correction + CHANGELOG Unreleased).
- No dependency on other slices; base is `origin/master` (60fbd39).

## Open questions / risks

- R1: field failure shape unobserved (no real sarek in CI) — manual post-merge
  smoke gate stands.
- R5: the download is keyed to sarek's default `GATK.GRCh38` genome attrs; a
  custom-reference run would fetch the GRCh38 cache (wrong build). Accepted, noted
  in docs.

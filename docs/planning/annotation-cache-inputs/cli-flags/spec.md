# Spec — annotation-cache-inputs / cli-flags

## Problem slice and user outcome

The launch side of the C7 cache-input follow-on: a `contig run` on either sarek
variant assay can take typed, user-supplied annotation-cache paths
(`--vep-cache`/`--snpeff-cache`) that override the auto-download wiring and
survive `rerun`/`resume`; and an explicit-reference (`--fasta/--gtf`) variant run
with neither user cache is refused at pre-flight instead of silently downloading
a GRCh38 cache against a non-GRCh38 reference. Outcome: custom-reference variant
runs can never mis-annotate against the wrong build, and labs with pre-built
caches get a discoverable, replayable flag.

## In-scope requirements (PRD M1, M2, M3, M4, S1)

- **M1 — typed flags.** `--vep-cache` / `--snpeff-cache` (typer Option, plain
  `str`, no existence validation — sarek accepts paths and `s3://` URLs) on
  `contig run`, threaded through the four touch points: `run` declaration →
  `run`→`_dispatch_run` kwargs → `_dispatch_run` signature → `LaunchManifest`
  fields for `rerun`/`resume` replay (the `genome/fasta/gtf` pattern,
  `cli.py:406-408`, `:445-447`, `:530-532`, `:778-780`, `:892-894`, `:2561-2563`).
- **M2 — injection with correct precedence.** Inside the cache-wiring seam
  (`cli.py:486-513`): user caches (flag value, or `--opt` value already in
  `params`) win over auto-download; when both user caches are present the
  `download_cache`/`outdir_cache` auto-download params are NOT injected (a
  user-supplied `download_cache`/`outdir_cache` via `--opt` still wins if
  present — setdefault contract unchanged).
- **M3 — explicit-reference guard.** `engine == "nextflow"` and
  `assay in VARIANT_ASSAYS` and explicit mode (params carry `fasta`/`gtf`, no
  `genome` key) and **neither** user cache present → `typer.Exit(1)` refusal
  naming `--vep-cache`/`--snpeff-cache`, before any cache dir creation, nothing
  launched. All-or-nothing in explicit mode: exactly one user cache is also a
  refusal. iGenomes mode (params carry `genome`) and test-profile runs (neither
  key) keep today's auto-download.
- **M4 — manifest replay.** Additive `LaunchManifest.vep_cache: str | None = None`
  and `snpeff_cache: str | None = None` (unsigned; signing covers `RunRecord`
  only); written at manifest creation with the raw CLI args; `rerun`/`resume`
  replay them into `_dispatch_run` like `fasta/gtf`. Params are never persisted
  in the bundle (parent contract: re-derived per dispatch).
- **S1 — test-profile runs unchanged.** No resolved reference → auto-download as
  today; all 8 parent tests in `tests/test_annotation_cache_wiring.py` pass
  unmodified.

## Out-of-scope boundaries

- No `AnnotationProvenance`/`RunRecord` model change, no signature break.
- No sequence-inferred build detection, no `click.Path` existence checks, no
  `s3://` pre-flight validation (sarek owns resolution; a bad path fails mid-run
  honestly via existing self-heal).
- No change to `--opt` semantics; no new flag on `resume`/`rerun` (they replay
  the manifest).

## Acceptance criteria (testable)

1. `contig run --assay variant_calling --vep-cache /v --snpeff-cache /s` (test
   profile, spy executor): `params` carry `vep_cache == "/v"`,
   `snpeff_cache == "/s"`, and NO `download_cache`/`outdir_cache` keys; no
   `caches/` dir created.
2. `--opt vep_cache=/optv --vep-cache /flagv`: `params["vep_cache"] == "/optv"`
   (opt wins; setdefault).
3. Explicit mode (`--fasta`/`--gtf`) + neither cache → exit 1 before
   `self_heal_run`, message names `--vep-cache` and `--snpeff-cache`.
4. Explicit mode + exactly one cache → exit 1, message names both flags.
5. iGenomes mode (`--genome GRCh38`) + no caches → auto-download params injected
   (status quo).
6. iGenomes mode + both caches → user caches win, no download params.
7. Explicit mode + both caches → user caches win, no download params, launch
   proceeds (spy called).
8. `rerun`/`resume` of a run launched with the flags replays them into
   `_dispatch_run` (manifest round-trip).
9. `build_nextflow_command` over merged params yields `--vep_cache /v
   --snpeff_cache /s` tokens.
10. All 8 parent tests in `tests/test_annotation_cache_wiring.py` green
    unmodified; full suite green.

## Dependencies and sequencing

- Single aspect, single plan, 3-4 TDD tasks (seam logic first, then flags +
  manifest, then refusal paths, then replay pins). Base is this worktree (master
  + parent cache-wiring merged).

## Open questions / risks

- R5 (PRD): iGenomes-mode safety is assumed, not verified — smoke-gate item.
- `--genome GRCh38 --vep-cache /x` (single cache, iGenomes): allowed — the
  SnpEff half auto-downloads the correct build (PRD R3).
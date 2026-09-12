# Understanding — annotation-cache-inputs

Phase 2 dig note. Grounded in the inline brief (`docs/planning/_card/issue.md`), a
targeted code map (verified file:line citations below), and the parent slice's own
record (`docs/technical/CAPABILITY_ROADMAP.md:1585-1604`).

## What the work is really asking

The parent `annotation-cache-wiring` slice made variant-assay runs *annotate at all*
by injecting `download_cache=true` + `outdir_cache=<runs>/caches/annotation/…`
(`src/contig/cli.py:486-513`, called from `_dispatch_run` at `cli.py:760-763`). It
recorded two accepted gaps, and this slice closes the first:

1. **User-supplied cache paths don't exist.** `--vep_cache`/`--snpeff_cache` are
   nowhere in the CLI (grep: zero hits beyond the parent's docstring). The only
   escape hatch is the generic `--opt key=value` list, and since the parent injects
   via `setdefault` (`cli.py:512-513`), an `--opt vep_cache=…` value *would* win —
   untyped, undiscoverable, and unreplayed by `rerun`/`resume` (manifest persists
   only raw `genome/fasta/gtf`, `cli.py:778-780`).
2. **Wrong-build cache in explicit-reference mode.** The download is keyed to
   sarek's default `GATK.GRCh38` genome attrs (`conf/igenomes.config`), so a custom
   `--fasta/--gtf` run (mode `explicit`) would fetch the GRCh38 cache against a
   non-GRCh38 reference — silently mis-annotated calls, the exact "plausible-but-
   wrong" class the C7 concordance axis exists to catch. iGenomes mode is safe:
   sarek keys the download per-genome-key. The *sample-side* assembly-signature
   detector is a declared blocker (CAPABILITY_ROADMAP.md:512-516) — the reference
   side is fully knowable from params, no inference needed.

## Affected areas (verified)

- `src/contig/cli.py:406-408` — `--genome/--fasta/--gtf` flag declarations; the
  four-touch-point precedent for a new flag: `run` declaration → `run`→`_dispatch_run`
  kwargs (`cli.py:445-447`) → `_dispatch_run` signature (`cli.py:530-532`) →
  `LaunchManifest` field for rerun/resume replay (`cli.py:892-894`, `2561-2563`).
- `src/contig/cli.py:486-513` — `_enable_annotation_cache`; the natural seam for
  both the user-cache injection and the pre-flight guard. Called at `cli.py:760`
  **before** `_inject_default_params` (`cli.py:764`); `params` at that point already
  carries the resolved reference (`resolve_reference` at `cli.py:657` returns
  `{"genome": key}` or `{"fasta":…, "gtf":…}`, `reference.py:21-41`), so explicit-vs-
  iGenomes is knowable there via `params.get("genome")`. Note: test-profile runs
  (`if input:` guard, `cli.py:643`) never resolve a reference — neither key present.
- `src/contig/models.py:411-455` — `LaunchManifest`: additive, unsigned (signing
  covers `RunRecord` only, `signing.py:55-64`); `auto_approve` (`models.py:444`) is
  the additive-field idiom, but is *write-only* (re-decided per invocation) while
  `fasta/gtf` (`models.py:426-428`) are *replayed* — cache paths are input config,
  so the replayed pattern applies.
- `src/contig/models.py:221-237` — `AnnotationProvenance`: `tool/version/db_version`
  parsed from VCF headers (`bundle.py:183-252`), never from params. `RunRecord.
  parameters` (`models.py:337`) already persists whatever lands in `params`, so
  user cache paths are provenance for free — no model change needed for the input
  side; `db_version` is the observed output side. The chain
  params → VCF-header `cache="…"` token is complete without a new field.
- `src/contig/runner.py:1296-1328` — `build_nextflow_command`: every params key
  becomes `--key value` mechanically, no allow/deny list; `vep_cache`/`snpeff_cache`
  flow through with zero runner changes.
- `src/contig/registry.py:97` — `VARIANT_ASSAYS` gate; both variant entries carry
  `…,vep,snpeff` in `default_params` (`registry.py:42,58`).
- `tests/test_annotation_cache_wiring.py` — the parent's test style: real Typer
  app via `CliRunner`, a `self_heal_run` spy capturing `params`, argv/param
  assertions, `setdefault`-wins pin (`test_user_supplied_cache_params_win`, line 146).

## Open questions for the requirements interview

1. **Refusal posture.** Explicit-reference + no user caches: refuse the launch at
   pre-flight (parent's uncreatable-dir posture, `cli.py:505-511`) — or WARN and
   let sarek hard-fail at cache initialisation? The brief says "an honest refusal";
   refusing earlier is better UX and the sarek failure is guaranteed anyway.
2. **All-or-nothing vs per-tool.** Explicit mode with only `--vep-cache` given: the
   SnpEff download would still be wrong-build. Refuse unless BOTH are supplied, or
   accept mixed (user VEP + downloaded SnpEff) when the reference actually is
   GRCh38? Simplest honest rule: explicit mode requires both or neither.
3. **Test-profile runs.** No reference mode recorded (no genome, no fasta). Keep
   today's auto-download (status quo, they're dev smoke runs), or skip the guard
   for them? Recommend: keep auto-download — the guard addresses explicit mode only.
4. **Provenance depth.** Brief says "record which cache/build actually ran in
   `AnnotationProvenance`" — but `RunRecord.parameters` already records the inputs
   and `db_version` the observed build; a new `AnnotationProvenance` field would be
   a disclosed signature break (RunRecord is the signed payload) for zero new
   information. Options: (a) parameters-only (recommended), (b) additive
   `cache_source: Literal["auto_download","user_supplied"]|None` on
   `AnnotationProvenance` for surface visibility (+signature break), (c) render
   cache inputs in `contig methods`/HTML without a model change.
5. **Flag naming/precedence.** `--vep-cache`/`--snpeff-cache`; precedence vs `--opt
   vep_cache=…` — recommend flags pre-inject BEFORE `_enable_annotation_cache` and
   let `--opt` (already in params) win, preserving "user values win" (setdefault).
6. **rerun/resume.** Persist the two flags on `LaunchManifest` (replayed, like
   fasta/gtf) — additive, unsigned.

## Guardrails check

Layer 2 (run/verify enablement for the shipped C7 annotation assay). No Layer 1,
no wet-lab/clinical dependency, no raw-read egress, no correctness over-claim
(the refusal is a pre-flight guard, and annotation absence still degrades honestly
to UNVERIFIED). Test-first, argv/param pins, no real nf-core/VEP/sarek in CI —
the parent slice's precedent, unchanged.
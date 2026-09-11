# PRD — User-supplied annotation cache inputs + non-GRCh38 guard (C7 follow-on)

**Feature slug:** `annotation-cache-inputs` · **Type:** feat · **Owner:** aliz
**Branch:** `feat/annotation-cache-inputs/aliz` · **Capability:** C7 (research-use
variant annotation & prioritization) — the follow-on slice the
`annotation-cache-wiring` slice named for itself.
**Status:** drafted 2026-09-12 (brief → dig → interview → PRD).

## Problem Statement

`annotation-cache-wiring` made variant-assay runs annotate at all: `_dispatch_run`
injects `download_cache=true` + `outdir_cache=<runs>/caches/annotation/…` for both
variant assays, with `setdefault` so user-supplied values win
(`src/contig/cli.py:486-513`, `:760-763`). It shipped with two accepted gaps, and
this slice closes the first, which is a **silent-correctness hole**:

1. **No typed user-supplied cache path exists.** `--vep_cache`/`--snpeff_cache`
   appear nowhere in the CLI. A user with a pre-built VEP/SnpEff cache (a lab
   standard — caches are gigabytes and slow to download) can only pass it through
   the undocumented `--opt key=value` escape hatch, which is untyped,
   undiscoverable, and **not replayed** by `rerun`/`resume` (the launch manifest
   persists only raw `genome/fasta/gtf`, `cli.py:778-780`).
2. **Explicit-reference runs download a wrong-build cache.** The download is keyed
   to sarek's default `GATK.GRCh38` genome attrs (`conf/igenomes.config`), so a
   custom `--fasta/--gtf` run against a non-GRCh38 reference silently fetches the
   GRCh38 cache — VEP/SnpEff then annotate against the wrong build, and the C7
   concordance axis (`consequence_concordance`) corroborates two tools *both
   wrong in the same way*, defeating the verification the annotation assay exists
   for. iGenomes mode is safe (sarek keys the download per-genome-key); the
   *sample-side* assembly-signature detector is a declared blocker
   (CAPABILITY_ROADMAP.md:512-516), but the reference side is fully knowable from
   params at dispatch time — no inference needed.

The parent's own record names this slice: *"an explicit `--fasta/--gtf` run with a
non-GRCh38 reference would download the GRCh38 cache (wrong build) — accepted,
with user-supplied `--vep_cache`/`--snpeff_cache` paths still a future slice"*
(CAPABILITY_ROADMAP.md:1602-1603).

**What happens if we don't build this:** every custom-reference variant run either
mis-annotates silently (wrong build) or must be steered through an undocumented
`--opt` key with no rerun/resume replay — the exact "plausible-but-wrong" failure
R4 (false confidence) warns about.

## Goals & Success Metrics

- **G1 — typed cache inputs.** `contig run --vep-cache <path> --snpeff-cache <path>`
  passes both through to the sarek argv as `--vep_cache`/`--snpeff_cache`, survives
  `rerun`/`resume`, and user values always win over the auto-download wiring.
- **G2 — no wrong-build cache, ever.** An explicit-reference (`--fasta/--gtf`)
  variant run without both user caches is refused at pre-flight with a message
  naming the two flags, before anything launches. iGenomes runs and test-profile
  runs keep today's auto-download.
- **G3 — provenance chain.** The run record shows both sides: the cache inputs in
  `RunRecord.parameters` (free, automatic) and the observed build in
  `AnnotationProvenance.db_version` from the VCF header (shipped); the inputs are
  surfaced in `contig methods`/HTML renderers so the chain is readable.

**Measured how:** test-first — argv/param pins (parent's `test_annotation_cache_wiring.py`
style), refusal-path exit-code/name tests, rerun/resume replay pins, and a
renderer test. No real nf-core/sarek/VEP run in CI (standing posture); a real-run
smoke stays a manual post-merge gate.

## User Personas & Scenarios

- **A, lone computational biologist** (primary): has a lab-standard VEP/SnpEff
  cache on disk; wants a typed flag, not `--opt`, and the guarantee that a custom
  GRCh37 reference never gets annotated against GRCh38. Scenario: `contig run
  --assay variant_calling --fasta hg19.fa --gtf hg19.gtf --vep-cache
  /refs/vep/110_GRCh37 --snpeff-cache /refs/snpeff/GRCh37.105` → runs, annotates
  against the supplied caches, methods line names them.
- **B, wet-lab scientist who can't code**: not the buyer of this slice; the
  refusal message is their safety net when a wizard-driven custom-reference run
  has no cache — the launch form must not produce a silently wrong annotation.

## Requirements

### Must-have

- **M1 — typed flags.** `--vep-cache` / `--snpeff-cache` (typer Option, path or
  `s3://` string — sarek accepts both, so no path-existence validation at the
  CLI; the pipeline owns resolution) on `contig run`, threaded through
  `_dispatch_run` (four-touch-point precedent: declaration → `run` kwargs →
  `_dispatch_run` signature → `LaunchManifest`).
- **M2 — injection with correct precedence.** User cache values land in `params`
  *before* `_enable_annotation_cache` runs, so the parent's `setdefault` contract
  holds (`--opt` values, already in `params`, still win over the new flags);
  when either user cache is present, `download_cache`/`outdir_cache` auto-download
  wiring is **not** injected.
- **M3 — explicit-reference guard.** In `_enable_annotation_cache` (or its
  replacement): explicit-reference mode (params carry `fasta`/`gtf`, no `genome`)
  + missing either user cache → `typer.Exit(1)` refusal naming
  `--vep-cache`/`--snpeff-cache`, before the cache dir is even created
  (parent's uncreatable-dir posture, `cli.py:505-511`). All-or-nothing: both or
  neither (user decision, 2026-09-12).
- **M4 — manifest replay.** Both flags persisted on `LaunchManifest` (additive,
  unsigned — signing covers `RunRecord` only, `signing.py:55-64`) and replayed by
  `rerun`/`resume` (the `fasta/gtf` pattern, `cli.py:892-894`, `:2561-2563`),
  re-derived into params on each dispatch — never persisted in `params`/bundle.
- **M5 — provenance render.** `contig methods` and the HTML provenance panel show
  the annotation-cache inputs (user-supplied path or `download_cache=true`
  auto-download into `outdir_cache`) alongside the shipped `db_version` line,
  read from `RunRecord.parameters` — no new model field, no signature break
  (user decision, 2026-09-12).

### Should-have

- **S1 — test-profile runs stay working.** Test-profile variant runs (no resolved
  reference: neither `genome` nor `fasta`/`gtf` in params) keep today's
  auto-download — the guard addresses explicit mode only, and the existing parent
  tests must pass unmodified.

### Nice-to-have

- **N1 — `contig show` mention.** A one-line cache-input echo on `contig show`
  beyond methods/HTML (skip if the renderer seam makes it awkward).

## Technical Considerations

- **Seam:** `_enable_annotation_cache` (`cli.py:486-513`) is the single point —
  it already sees `params` post-`resolve_reference` (`cli.py:657`), so
  explicit-vs-iGenomes is knowable there via `params.get("genome")`; called
  before `_inject_default_params` (`cli.py:764`).
- **argv flow:** `build_nextflow_command` maps every params key to `--key value`
  with no allow/deny list (`runner.py:1326-1327`) — `vep_cache`/`snpeff_cache`
  flow through mechanically, zero runner changes.
- **Rerun/resume re-inject automatically** (both re-enter `_dispatch_run`;
  params are not persisted by design, parent slice's own contract).
- **Reproducibility:** the flags join the manifest like `fasta/gtf` (replayed,
  not re-decided) — cache inputs are analysis input config, unlike the
  write-only `auto_approve` idiom (`models.py:444`).
- **Signature:** no `RunRecord` field change → no disclosed signature break.
- **Dependencies:** none new (stdlib only; parent slice's posture unchanged).

## Risks & Open Questions

- **R1 — reasoned, not observed.** No real nf-core/sarek/VEP run in CI; the
  wrong-build claim is read from sarek 3.5.1 source and the parent's verified
  finding, not from an observed failure. Accepted (parent's posture); the manual
  smoke gate carries this slice's checklist too.
- **R2 — `s3://` cache paths.** A user-supplied `s3://` path needs network +
  credentials at run time; no pre-flight validation is attempted (sarek owns
  resolution), so a bad path fails mid-run honestly (existing self-heal).
- **R3 — mixed iGenomes/flag input.** `--genome GRCh38 --vep-cache /x` (no
  `--snpeff-cache`): iGenomes mode is safe, so the guard does not fire — the
  SnpEff half auto-downloads the correct-build cache. Confirmed consistent with
  M3's all-or-nothing rule, which scopes to explicit mode only.
- **R5 — iGenomes mode is assumed safe, not verified.** The guard's explicit-mode
  scope rests on the nf-core iGenomes mechanism (per-genome attrs supply per-genome
  cache URLs; only custom references fall back to sarek's hardcoded GRCh38
  default). Assumption recorded at the review gate (2026-09-12, option (a):
  accept-and-note). The manual post-merge smoke checklist must include one
  `--genome GRCh37` iGenomes run to confirm the downloaded cache is the GRCh37
  build; if it is not, widen the guard to non-GRCh38 iGenomes keys (revisit
  trigger: first real report, or the smoke gate itself).
- **OQ1 — flag value type.** Path `str` (no `click.Path` existence check) —
  resolved in M1; revisit if a real user reports a silent typo.

## Out of Scope

- **Sequence-inferred build detection** (assembly-signature from sample data) —
  declared blocker, CAPABILITY_ROADMAP.md:512-516.
- **GTF/known-sites version resolution** (C5 deferrals, no reliable source).
- **Cache download/resume machinery itself** — sarek owns it; Contig only
  supplies params and refuses the wrong-build combination.
- **Annotation prioritization** (C7's deferred follow-on).
- **Reconciling the parent's CHANGELOG entry** (it sits under [0.54.0] on master,
  docs-ahead-of-code) — the parent PR's business, not this slice's.

## Non-Functional Requirements

- Test-first; deterministic; no network; no real nf-core/VEP/sarek in CI.
- Stdlib only; no new dependency (`uv.lock` unchanged).
- No signature break; no `FailureClass`/corpus/guard-baseline change
  (`eval-guard`, `heal-guard`, `verify-guard`, `reproduce-guard` unmoved).
- Existing `tests/test_annotation_cache_wiring.py` passes unmodified.
# PRD — annotation-cache-wiring

**Feature slug:** `annotation-cache-wiring`
**Branch:** `feat/annotation-cache-wiring/aliz`
**Capability:** C7 (research-use variant annotation & prioritization) — the "live-cache
caveat" follow-on, the deepest shipped-but-not-turnkey gap in the roadmap.
**Status:** PRD (post-interview). Research-use verification only.

---

## Problem Statement

C7's verification axes — annotation structural verify, annotation plausibility,
VEP-vs-SnpEff concordance, and `AnnotationProvenance` capture — are all shipped and
marked SHIPPED (CAPABILITY_ROADMAP.md C7 M1–M5), but they depend on an **annotated
VCF existing in the run dir**. On a real nf-core/sarek 3.5.1 run, the annotation
step needs a VEP/SnpEff cache to run, and **Contig wires no cache**: `--vep_cache`
and `--snpeff_cache` default to `s3://annotation-cache/…` in sarek 3.5.1
(`nextflow_schema.json`, verified), so on a user's local machine without AWS
credentials the VEP/SnpEff step cannot resolve its cache. The roadmap states the
caveat verbatim: *"a real run's annotation step may still require a VEP/SnpEff
cache (`--vep_cache`/`--download_cache`) or a `--step annotate` entry point that
Contig does not yet wire — when that annotation output is absent the verifier
reports UNVERIFIED"* (CAPABILITY_ROADMAP.md:1494-1498). The same caveat is carried
by M3 (plausibility, :1530-1531) and M4 (concordance), and deferred in three
planning PRDs (annotation-plausibility, annotation-concordance, annotation-m5-surface).

**Consequence (verified against sarek 3.5.1 source, not assumed):** the whole C7
value is hollow on real data — and worse, the default variant run **hard-crashes**.
`subworkflows/local/annotation_cache_initialisation/main.nf` calls `error(...)`
("This path is not available within annotation-cache.") when the VEP/SnpEff cache
dir does not exist, and with the default `s3://annotation-cache/…` on local compute
without AWS access the run **FAILs at cache initialisation** — before any
verification can fire, and before any evaluation data reaches the C6 corpus
channels. The roadmap's M1 text ("when that annotation output is absent the
verifier reports UNVERIFIED") is therefore optimistic: the *observed-in-source*
shape is a hard run FAIL, not a tolerated absence. The fix is the same for both
shapes; this slice is a **variant-run reliability fix**, not C7 polish.

**Evidence it's real:** the caveat is recorded in the roadmap and in three planning
PRDs (`docs/planning/annotation-plausibility/prd.md:148-149,187`,
`docs/planning/annotation-concordance/prd.md:218-219,232`,
`docs/planning/annotation-m5-surface/prd.md:249`); the registry comments ship
annotation tools (`registry.py:29-41,49-57`) while nothing wires a cache; sarek
3.5.1's own schema pins the S3 cache defaults. No real sarek run exists in CI
(standing disclosure).

## Goals & Success Metrics

- **G1 — a real variant run produces an annotated VCF.** With the wiring in place,
  a sarek variant_calling / somatic run launches with annotation-cache params that
  let the shipped VEP/SnpEff steps resolve a cache on the user's compute (default:
  download at run time into a shared cache dir).
- **G2 — the annotation verifiers fire instead of degrading.** `_discover_qc`'s
  CSQ/ANN discovery (`runner.py:368-378`) and `_finalize`'s provenance capture
  (`self_heal.py:1722-1724`) find an annotated VCF on a real run. *Measure (this
  slice's own tests — the C7 verifier suite already passes and is not evidence for
  a launch-side change):* the new launch-side tests pin that a dispatched variant
  run assembles the annotation-cache params into the real argv (M1) and that the
  pre-flight refuses a bad cache dir (M2); the existing C7 fixture suite then
  covers the verifier side unchanged. The *real-run* measure (an actual sarek run
  produces an annotated VCF) is deferred to the manual post-merge smoke gate.
- **G3 — every failure path stays honest.** No cache-download reachable (no
  network), download fails, cache dir unwritable → the run fails or the verifiers
  report UNVERIFIED, never a false PASS; the bundle/reproduce contract is
  unchanged (cache dir is not inside the run dir; the annotated VCF self-describes
  db versions in its header).
- **G4 — rerun/resume and reproduce keep the params.** Re-injection via the
  persisted assay (`cli.py:716` on every `_dispatch_run` entry) means a rerun or
  resume re-wires the same annotation-cache params.

**Non-metric of success (explicit):** we are **not** validating that VEP/SnpEff
themselves run correctly — that is nf-core's guarantee and the shipped verifiers'
job. We are not wiring PON/germline-resource (separately deferred). No real
nf-core/sarek run in CI (the wiring is pinned by argv/param tests; a real-run smoke
test stays a manual post-merge gate).

## User Personas & Scenarios

- **A, lone computational biologist** running nf-core/sarek germline on their own
  machine: today the annotation axis of the verdict can't fire (or the run fails at
  the VEP step); after this, one run downloads the cache (first-run cost, then
  cached) and the annotated-VCF verification axes all produce results.
- **C, core facility** running variant calling at throughput: the annotation
  verification and the `verify-case-promote` corpus channel finally receive real
  annotation data instead of UNVERIFIED/absent.

## Requirements

### Must-have (this slice)

- **M1.** Both sarek variant entries (`variant_calling`, `somatic_variant_calling`)
  launch with annotation-cache params, injected non-destructively (user values win)
  through the existing per-dispatch param assembly in `_dispatch_run`:
  - `download_cache: true` — **verified**: with this set, sarek's main.nf takes the
    `DOWNLOAD_CACHE_SNPEFF_VEP` branch and **skips the cache-validation branch
    that hard-`error()`s on a missing cache** (sarek 3.5.1 main.nf:234-260);
  - `outdir_cache: <shared-cache-dir>` — **required, not optional**: without it
    the download publishes into `${outdir}/cache/` **inside the run dir**
    (conf/modules/download_cache.config publishDir fallback), polluting the run
    bundle. A deterministic path **outside the run dir** (e.g.
    `<runs-dir>/caches/annotation/<pipeline>@<revision>/`) makes the first run
    download once and rerun/resume and sibling runs reuse it.
  - No new CLI flag; no `LaunchManifest` change (params ride the existing
    `params` dict that is already recorded/replayed).
- **M2.** The cache dir is created (`mkdir -p`) at dispatch before launch; an
  unwritable/uncreatable path is an up-front refusal (the `ReferenceError` /
  `ConfigGenerationError` pattern: name the problem, exit 1, nothing launched).
- **M3.** Wiring is scoped to `VARIANT_ASSAYS` (both sarek entries); all other
  assays untouched (their runs carry no annotation tools, so the params would be
  dead weight).
- **M4.** `--step annotate` is **not** used: sarek's `step` enum is a *restart*
  mode (mapping/markduplicates/recalibrate/variant_calling/annotate) that needs a
  VCF-dir `--input` for a second run; annotation runs automatically after variant
  calling when `vep`/`snpeff` are in `--tools`, so the cache is the only missing
  enabler (verified: main.nf gates cache initialisation on `params.tools`
  containing `vep`/`snpeff`, not on `--step`). Rationale recorded in the
  roadmap/CHANGELOG.
- **M5.** Strict TDD, stdlib-only, no new dependency, no real nf-core run in CI.
  Tests pin: the merged params (setdefault semantics, user wins), the exact argv
  tokens (`--download_cache true` / `--outdir_cache <dir>` via
  `runner.py:1246-1247`), rerun/resume re-injection, the pre-flight refusal, and
  non-variant assays stay untouched.

### Should-have

- **S1.** The shared cache dir name is stable across runs and versions
  (`<pipeline>@<revision>`), and the same dir is reused on rerun/resume without
  re-download (sarek's download process is idempotent on an existing cache).
- **S2.** The honest scope note (push, not demand-pull; no real sarek in CI;
  unmeasured organic frequency) recorded in `docs/technical/CAPABILITY_ROADMAP.md`
  C7 (closing the M1/M3/M4 caveat — and correcting its "verifier reports
  UNVERIFIED" wording to the verified hard-crash shape) and `CHANGELOG.md`, per
  house style.

### Nice-to-have (explicitly deferred)

- User-supplied cache paths (`--vep_cache`/`--snpeff_cache` CLI flags + manifest
  fields) for users who already have caches — future slice.
- A `--no-annotation-cache` opt-out — deferred; revisit on a real report of
  pain.
- PON / germline-resource wiring for a real Mutect2 run (separately deferred in
  the roadmap).
- Dashboard surfacing beyond the existing QC panel / provenance panel.

## Technical Considerations

- **Mechanism (decided):** a per-assay enablement step inside `_dispatch_run`
  (`cli.py`, after `resolve_reference` and before `_inject_default_params` at
  `cli.py:716`). For `assay in VARIANT_ASSAYS`, compute the shared cache dir, mkdir
  (M2), and `params.setdefault("download_cache", True)` /
  `params.setdefault("outdir_cache", str(cache_dir))`. A test pins the ordering
  contract: a user-supplied `download_cache`/`outdir_cache` value in the incoming
  params survives the merge (setdefault semantics), so a future CLI flag can win.
- **Params → argv needs zero changes:** `build_nextflow_command`
  (`runner.py:1246-1247`) already turns every params key into `--key value`.
- **Rerun/resume is automatic:** `rerun` and `resume` re-enter `_dispatch_run`
  with the persisted assay, so the enablement re-runs (verified pattern:
  `test_rerun_reinjects_tools_via_persisted_assay`).
- **Where the cache dir lives:** `<runs-dir>/caches/annotation/<pipeline>@<revision>/`
  (absolute path — sarek requires absolute paths on cloud; harmless locally).
  The annotated VCF's `##VEP=… cache="…"` header (already parsed by
  `bundle.py:_extract_vep_cache`) self-describes the db version, so the bundle
  stays reproducible without the cache bytes. Cross-run concurrency on the same
  cache dir is tolerated (both downloads land; idempotent), noted as a known
  non-issue.
- **Verification side needs no change:** `_discover_qc` already discovers the
  first CSQ/ANN-declaring `*.vcf.gz` (`runner.py:368-378`), concordance resolves
  both layouts (`annotation_concordance.py:500-579`), provenance captures at
  `_finalize` (`self_heal.py:1722-1724`). The structural manifests
  (`structural.py:250-261`) require `*.vcf.gz` only — no manifest change.
- **Test blast radius:** `test_run_default_params.py` (exact-dict pins at
  :167-177 assert only the `tools` key — additive keys to `default_params` would
  trip them; the implementation must therefore merge at dispatch, not mutate the
  registry dicts), `test_somatic_end_to_end.py:100-102` (argv assertion),
  `test_annotation_registry.py`. New fixtures are argv/param-level; no real sarek.

## Risks & Open Questions

- **R1 (resolved by source verification, still unobserved in the field) — the
  current real-run failure shape is a hard crash.** sarek 3.5.1's
  `ANNOTATION_CACHE_INITIALISATION` calls `error(...)` when the cache dir does not
  exist (subworkflow source, verified), so a cache-less Contig variant run FAILs at
  cache initialisation — the roadmap's "verifier reports UNVERIFIED" wording was
  optimistic. The fix is identical either way; the honest-degradation contract
  (never a false pass) is unchanged. No real sarek run exists in CI or on the dev
  machine, so the *field* shape stays unobserved; a real-run smoke test remains a
  manual post-merge gate.
- **R2 — network dependency.** `download_cache` runs `vep_install`/snpEff
  downloads on the run machine and needs internet there (the pipeline's own
  reference downloads already assume this in `--genome` mode). A download failure
  fails the run honestly — never a false pass. If the download is partially
  complete, Nextflow re-runs it on the next attempt; the run dir is unaffected.
- **R3 — first-run cost.** Multi-GB cache download on the first variant run.
  Accepted (user decision): Default ON, shared cache dir so the cost is paid once.
- **R4 — cache dir on `--runs-dir` shareability.** If the user's runs dir is on
  NFS/cloud, the cache is shared accordingly; if it is per-machine, each machine
  pays the download once. Not a correctness issue.
- **R5 (new — wrong-build cache for custom references).** The download's target
  (species/assembly/version) resolves from `conf/igenomes.config` keyed on
  `params.genome`, whose sarek default is `GATK.GRCh38` — so an explicit
  `--fasta/--gtf` run with a *non-GRCh38* reference still downloads the GRCh38
  cache, and VEP would annotate against the wrong build (Contig has no reference
  build detection — C5's deferred detector). Accepted as out of scope with the
  honest note in the roadmap/CHANGELOG: GRCh38-keyed default; a custom-build user
  is expected to set `--genome` or supply their own cache (future slice).
- **R2's blast radius, stated plainly:** a network-less run machine means the
  cache download fails → the run fails at the download step → the self-heal loop
  diagnoses what it can (likely `tool_crash` or `download_failed`) and retries
  within its budget, then gives up honestly. This slice does **not** add a repair
  for it — out of scope — but the honest scope note names it so nobody reads
  "default ON" as "works offline".
- **Open:** whether sarek's `DOWNLOAD_CACHE` process requires `--outdir_cache`
  to be pre-created (we create it anyway — M2); whether a `germline_resource`/
  PON flag is needed for a *successful* somatic run's annotation step (no —
  annotation is downstream of calling; PON affects calling filters, separately
  deferred).

## Out of Scope

- User-supplied VEP/SnpEff cache paths as CLI flags or manifest fields.
- `--step annotate` restart-mode runs (documented as unnecessary; the annotation
  runs in the same invocation).
- PON / germline-resource wiring for real Mutect2 runs.
- Any change to the annotation verifiers, packs, `models.py`, or the signed
  record (this slice is launch-side only; params are already in the manifest's
  replay path — no signature break).
- Band calibration; any biological/clinical claim.
- No Layer-1 workflow authoring; no raw-read egress (only the pipeline's own
  annotation-DB download runs on the user's compute).

## Guardrail check (CLAUDE.md)

Pure Layer-2 launch-side enablement inside the founder's edge: it makes the
shipped verification harness *fire on real data* (moat: verify/reproduce + eval
data) and gets better as sarek/annotation tools improve, never redundant. No
Layer-1, no clinical claims, no new dependency, no raw-read egress, test-first.

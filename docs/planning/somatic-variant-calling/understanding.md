# Understanding — feat/somatic-variant-calling (deep dig)

Grounded in three read-only code-map agents (registry+planner, structural+run_qc,
samplesheet+preflight) over the worktree checkout, cross-checked against the official
nf-core/sarek 3.5.1 docs, plus one direct verification of the QC wiring. `path:line`
cited inline.

## What the work is really asking

Add **somatic (tumor–normal) variant calling** as a new assay (capability **C4**,
`CAPABILITY_ROADMAP.md:265-292`), consuming nf-core/sarek in somatic mode. Tight
first slice per the card: registry entry, planner routing, tumor/normal sample-sheet
shape + pre-flight validation, and a structural output manifest — test-first, no real
nf-core run in CI. Plausibility (VAF), panel-of-normals check, and the second-caller
concordance hook are **deferred** to follow-on slices.

## 🔴 The headline finding: somatic does NOT fit the clean 5-point `ADD_AN_ASSAY` recipe

`ADD_AN_ASSAY.md` frames a new assay as a **data change at five mapping points**
(registry, keywords, replicate flag, rule pack, wiring) with the planner, **runner,
and sample-sheet all assay-agnostic**. That holds for the six existing assays because
each is **one pipeline ↔ one assay** with a generic RNA-seq-shaped sample sheet.

**Somatic breaks all three of those assumptions.** It is a *second assay sharing one
pipeline* (`nf-core/sarek`), distinguished not by the pipeline name but by (a) the
**sample-sheet content** (a tumor/normal pair per patient) and (b) the **sarek
`--tools`** it invokes. That makes this a real engineering slice, not a data addition
— which is consistent with it being the "biggest feature" pick, but the PRD must scope
it honestly. Four concrete design problems fall out:

### Problem 1 — the `nf-core/sarek` pipeline-string collision (architectural)
`_ASSAY_BY_PIPELINE` (`registry.py:56`) keys by **pipeline string**, and germline
already owns `nf-core/sarek` (`registry.py:19-24`). A second sarek entry for somatic
makes `assay_for_pipeline("nf-core/sarek")` return whichever was **inserted last**.
That reverse-lookup is load-bearing:
- `cli.py:505` — `assay = assay_for_pipeline(effective_pipeline) or "rnaseq"` is where a
  **live run gets its assay label**. A collision here mislabels every sarek run.
- also `cli.py:850` (concordance gate), `cli.py:1296/1352` (benchmark/reference-set),
  `methods.py:103` (methods label).

**Implication:** routing to an assay by pipeline name is insufficient for somatic. The
assay must be carried on the run explicitly (e.g. persisted on the plan/run record and
threaded through, rather than re-derived from the pipeline string), or the registry
model must change so two assays can share one pipeline. **This is the central design
decision of the slice** and should be resolved in the PRD before planning.

### Problem 2 — no sarek mode/`--tools` param-injection seam
Sarek runs on **defaults** today; germline is *implicit* (never explicitly requested).
Grep for `somatic|tumor|--tools|--step|panel_of_normals` finds nothing in `src/`
except a comment. `PipelineEntry` (`models.py:152-158`) has only
`assay/pipeline/revision/description` — **no params/profile/tools field**. Params are
assembled solely from `resolve_reference` + `--input`/`--outdir` (`cli.py:375-464`;
`build_nextflow_command` `runner.py:160-192` just appends `--key value`). Sarek somatic
needs `--tools` (e.g. `strelka,mutect2`) and the tumor/normal structure. So a
**per-assay default-params seam is new work** — there is no place to hang
`--tools strelka,mutect2` for the somatic assay today. (Also note `resolve_reference`
passes `--gtf` regardless; sarek uses `--fasta` but not `--gtf` — a latent germline
quirk, `reference.py:1,21-41`.)

### Problem 3 — the sample sheet is RNA-seq-only
`SampleRow` (`samplesheet.py:11-15`) = `{sample, fastq_1, fastq_2, strandedness}`.
Sarek's schema (nf-core/sarek 3.5.1 usage docs) needs `patient, sample, status, lane,
fastq_1, fastq_2`, where **`status` 0=normal / 1=tumor**, and a **tumor/normal pair**
is "same `patient`, different `sample`, opposite `status`." Germline sarek runs today
are validated against the *wrong* (RNA-seq) columns and nobody noticed because sarek
tolerates it. Somatic needs a sarek-shaped row model / extended parser **plus** a
pairing validator: `status ∈ {0,1}`, ≥1 patient with both a normal and a tumor row,
refuse an unpaired tumor. Convention: return a `list[str]` of issues like
`validate_samplesheet` (`samplesheet.py:40-67`) so the existing refuse block at
`cli.py:382-388` prints them and exits 1.

### Problem 4 — routing keyword collision
No somatic/tumor keyword exists; `variant_calling` keywords are germline-flavored
(`registry.py:108-116`). A `somatic` keyword group ("somatic", "tumor"/"tumour",
"tumor-normal") must be added and, because `match_assay` is first-hit-wins substring
(`registry.py:151-161`), ordered so it can't misroute — and a non-collision test added
against germline (`ADD_AN_ASSAY.md:48-59`).

## 🟡 The structural-manifest wiring subtlety (verified directly)

The live self-heal runner calls `_discover_qc` (`runner.py:295`, body
`runner.py:38-79`), which runs: the assay rule pack over MultiQC, a **blanket**
`evaluate_structural(bams)` over every `**/*.bam`, and germline/rnaseq-only
plausibility. It uses `manifest_for("variant_calling")` **only as a VCF-locator glob**
(`runner.py:64-66`), **not** for present/gzip enforcement.

The manifest-consuming function `evaluate_against_manifest` runs via `run_qc()`
(`run_qc.py:42-81`) — and `run_qc()` has **no caller inside `src/contig`** (grep). So
the per-assay `ExpectedOutputs` `required`/`gzip` present-checks are exercised at
**`contig verify`** time and in tests, not automatically inside the live self-heal
loop. Germline's own `*.vcf.gz`-present check is therefore not enforced live either —
this is existing behavior, not a somatic bug.

**Decision for the slice:** adding a `somatic_variant_calling` entry to
`_ASSAY_MANIFESTS` (`structural.py:244-268`) is necessary but, by itself, only takes
effect at verify-time — mirroring germline exactly. If we want somatic present/gzip
enforcement inside the live loop we must additionally wire it into `_discover_qc`. The
honest, consistent-with-germline default is: **add the manifest, mirror the germline
verify-time contract, do not special-case the live loop** — and say so.

## Grounded somatic manifest (proposed, from sarek 3.5.1 output docs)

Sarek somatic outputs land in `variant_calling/<caller>/<tumor>_vs_<normal>/`. Sarek
has **no default caller** — callers are chosen via `--tools`, so `required` must match
only the callers this assay actually invokes (couples Problem 2 to the manifest). A
germline-mirroring minimal manifest:
```python
"somatic_variant_calling": ExpectedOutputs(
    required=["*.vcf.gz"],   # ≥1 intact somatic VCF; mirrors germline's minimal contract
    gzip=["*.vcf.gz"],
)
```
Note `check_index_present` only recognizes `.bai`/`.csi`, **not** `.tbi`
(`structural.py:58-60`), so enforcing VCF `.tbi` indexes would need a code change;
germline omits `indexed`, so mirror that and keep the manifest minimal.

## Every file a somatic assay must touch (the switch points)

Beyond the ADD_AN_ASSAY five, the assay-string is hard-referenced across:
`registry.py` (REGISTRY + `_ASSAY_KEYWORDS` + the `_ASSAY_BY_PIPELINE` collision),
`rule_pack.py:253` (`_RULE_PACKS`, hard-errors on miss), `structural.py:244`
(`_ASSAY_MANIFESTS`, hard-errors on miss), `methods.py:19` (`_ASSAY_LABEL`),
`concordance.py:37` / `count_concordance.py:47` (assay sets — untouched this slice),
`planner.py:26`/`datashape.py:22` (`_REPLICATE_ASSAYS` — somatic is NOT a replicate
assay, so leave out but pin with a test), `samplesheet.py` (new sarek schema),
`runner.py:50/64` and `cli.py:505/850/1296/1352` (assay gating / reverse-lookup).

## Guardrail check (CLAUDE.md) — clean

Layer-2 only (we consume sarek somatic, never author it); no raw-read egress
(deterministic, synthetic fixtures, no nf-core run in CI); **no clinical over-claiming**
— a somatic verdict is "ran correctly and reproducibly," research-use, never a cancer
diagnosis (`USE_CASE_UNIVERSE.md` bright line); test-first.

## Open questions for the PRD interview

1. **Assay-vs-pipeline model (Problem 1):** carry `assay` explicitly on the plan/run
   record vs. change the registry so two assays share one pipeline vs. a distinct
   registry key. Which?
2. **How far does slice 1 go?** Two honest cut-lines:
   - **(A) Launchable somatic run:** also add the `--tools`/somatic param seam
     (Problem 2) so a planned somatic run genuinely invokes sarek somatic. Bigger,
     but the assay actually *runs*.
   - **(B) Intake + verify scaffolding only:** registry + routing + sarek sample-sheet
     validation + structural manifest, deferring the `--tools` launch seam. Smaller,
     but a "somatic" run wouldn't yet differ from germline at launch.
3. **`--tools` default set** if we do (A): Strelka2 + Mutect2 (SNV/indel) is the common
   somatic pair; SV/CNV (Manta/ASCAT) deferred?
4. **Structural manifest wiring:** verify-time only (mirror germline) vs. also wire into
   the live `_discover_qc`?
5. **Demand-pull sanity check:** C4 is roadmap-push, not partner-pull
   (`USE_CASE_UNIVERSE.md` discipline). Confirm somatic over deepening a shipped assay
   before we plan.

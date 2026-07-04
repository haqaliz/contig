# PRD — Somatic (tumor–normal) variant calling assay (capability C4)

**Slug:** `somatic-variant-calling` · **Type:** feat · **Owner:** aliz · **Branch:**
`feat/somatic-variant-calling/aliz`

**Status: DRAFT — awaiting review-gate approval.** The four scope decisions below were
taken on best judgment while the user was away (recommended options, internally
consistent). Each is marked **[ASSUMED]** and may be flipped at the ⛔ review gate
before `tech-plan`.

---

## Problem Statement

Contig verifies three assays today (RNA-seq, single-cell RNA-seq, **germline** variant
calling). Cancer research runs on **somatic (tumor–normal)** variant calling — a
different analysis where variants are called by contrasting a tumor sample against its
matched normal. Contig cannot run or verify it: a user with tumor/normal FASTQs has no
somatic goal to route to, no sample-sheet validation for the paired structure, and no
somatic-aware verdict.

Somatic is **capability C4** on `docs/technical/CAPABILITY_ROADMAP.md:265-292` — the next
sequenced engine capability and the biggest unblocked lever, explicitly framed as
"depth-first: add one assay end to end." It is a natural extension of the shipped
germline sarek assay and reuses the shipped C1 (concordance) / C2 (self-heal) / C3
(plausibility) machinery on new terrain, compounding the failure-and-verification corpus
(moat #2).

**Evidence it's real:** somatic tumor–normal is the canonical cancer-research variant
workflow; nf-core/sarek supports it first-class (sarek 3.5.1 usage docs). It is listed
in `USE_CASE_UNIVERSE.md:72-74` as "the family closest to disease research."

**Honest caveat (demand-pull):** no named design partner requested somatic; C4 is
roadmap-push. The discipline (`USE_CASE_UNIVERSE.md:124-131`) prefers a partner ask.
Accepted **[ASSUMED: Proceed]** because it is the pre-designated next capability and the
`contig-next` handoff selected it; revisitable at the gate.

## Goals & Success Metrics

- **G1 — Routing.** A somatic goal phrase ("somatic variant calling", "tumor normal",
  "tumour/normal") routes to the `somatic_variant_calling` assay, and does **not**
  misroute to germline `variant_calling` (or vice versa). *Measured:* registry routing
  test + a non-collision test against germline.
- **G2 — Correct assay label.** A somatic run is labelled `somatic_variant_calling`
  end-to-end despite sharing the `nf-core/sarek` pipeline with germline. *Measured:* a
  test that a planned/executed somatic run carries the somatic assay, and a germline run
  is unaffected (the pipeline-string collision is fixed).
- **G3 — Sample-sheet pre-flight.** A malformed somatic sample sheet (missing
  `patient`/`status`, `status ∉ {0,1}`, a tumor with no matched normal) is refused at
  pre-flight with a specific message; a valid tumor/normal sheet passes. *Measured:*
  pre-flight validation tests over synthetic sheets.
- **G4 — Launchable somatic run.** A planned somatic run invokes sarek with the somatic
  caller set (`--tools`), so the run genuinely differs from germline at launch.
  *Measured:* a test asserting the assembled Nextflow command carries the somatic
  `--tools`, over an injected executor (no real nf-core run).
- **G5 — Structural verdict.** Somatic outputs have a structural manifest; a run missing
  a required somatic VCF FAILs, an intact one passes. *Measured:* structural manifest
  tests mirroring germline.

**Non-goal metrics (explicitly deferred):** VAF-distribution plausibility, panel-of-
normals presence, second-caller concordance accuracy, single-cell/other assays.

## User Personas & Scenarios

- **A — lone computational biologist** running a cancer cohort: has tumor/normal FASTQs,
  wants a verified somatic call set without hand-wiring sarek's somatic mode and sample
  sheet.
- **D — biotech researcher**: wants defensible provenance on a somatic run for a paper's
  methods, research-use only.

Scenario: user supplies a sarek-shaped sample sheet (patients each with a normal + tumor
row) and a reference, picks/searches the somatic goal → Contig validates the pairing,
launches sarek somatic with Strelka2+Mutect2, self-heals recoverable failures, and
returns a scoped verdict over the somatic VCFs.

## Requirements

### Must-have (slice 1)

- **M1 — Registry + routing.** Add a `somatic_variant_calling` registry entry (pipeline
  `nf-core/sarek`, revision `3.5.1` — same real tag germline pins) and a `somatic`
  keyword group ordered so it can't collide with germline (first-hit-wins substring,
  `registry.py:151-161`). `_REPLICATE_ASSAYS` is **not** touched (somatic is not a
  replicate assay; pin with a datashape test).
- **M2 — Resolve the sarek pipeline-string collision. [ASSUMED: persist assay on the
  plan/run].** Carry the resolved `assay` explicitly on the `Plan`/`RunRecord` and use it
  on the run path instead of re-deriving via `assay_for_pipeline(pipeline)` at
  `cli.py:505`. `_ASSAY_BY_PIPELINE` (`registry.py:56`) can no longer be a 1:1 reverse
  map for sarek; every `assay_for_pipeline` site that assumed 1 pipeline ↔ 1 assay
  (`cli.py:505/850/1296/1352`, `methods.py:103`) is audited and switched to the persisted
  assay where it drives behavior. Germline behavior must be unchanged (regression test).
- **M3 — Somatic sample-sheet shape + pre-flight.** A sarek-shaped row model / extended
  parser recognizing `patient, sample, status, lane, fastq_1, fastq_2`. A somatic
  validator (returns `list[str]` like `validate_samplesheet`, `samplesheet.py:40-67`, so
  the existing refuse block at `cli.py:382-388` prints + exits 1) asserting: required
  columns present; `status ∈ {0,1}`; ≥1 patient with both a normal (0) and tumor (1) row
  with distinct `sample`; refuse an unpaired tumor (a `status:1` patient with no matching
  `status:0`). Gate attaches at the `_dispatch_run` sample-sheet chokepoint,
  **somatic-assay-gated**. **Germline/RNA-seq sample-sheet validation is explicitly
  unchanged this slice** — germline sarek keeps flowing through the generic
  `validate_samplesheet` (retrofitting germline onto the sarek schema is out of scope).
  Edge cases the validator must define behavior for: **multi-tumor per patient**
  (relapse: several `status:1` rows sharing a patient — allowed), **tumor-only** (no
  normal at all — refuse for the somatic tumor–normal assay, with a message pointing at
  germline), and a **germline-shaped sheet supplied to the somatic goal** (missing
  `status` → refuse with the specific missing-column message).
- **M4 — Launchable somatic run (`--tools` seam). [ASSUMED: cut A; Strelka2+Mutect2].**
  Introduce a declarative per-assay default-params seam (e.g. a `default_params` field on
  `PipelineEntry`, empty for existing entries, `{"tools": "strelka,mutect2"}` for
  somatic) merged into `params` in the CLI run assembly (`cli.py:375-464`) before
  `--input`/`--outdir`, so `build_nextflow_command` (`runner.py:190`) emits
  `--tools strelka,mutect2`. Sarek infers somatic mode from the paired sample sheet +
  somatic-capable tools; no separate mode flag is required. Existing assays get an empty
  default (no behavior change).
- **M5 — Structural manifest. [ASSUMED: mirror germline, verify-time].** Add a
  `somatic_variant_calling` entry to `_ASSAY_MANIFESTS` (`structural.py:244-268`),
  minimal and germline-mirroring: `required=["*.vcf.gz"]`, `gzip=["*.vcf.gz"]`, no
  `indexed` (`check_index_present` doesn't recognize `.tbi`, `structural.py:58-60`). Like
  germline, this is enforced at `contig verify` time via `evaluate_against_manifest`; the
  live `_discover_qc` loop is **not** special-cased for somatic present/gzip (consistent
  with germline, `runner.py:38-79`). The germline-only VCF-plausibility branch at
  `runner.py:64-71` stays germline-only (somatic plausibility is deferred).
- **M6 — Methods label.** Add a `somatic_variant_calling` entry to `_ASSAY_LABEL`
  (`methods.py:19`) so the methods paragraph names the assay.
- **M7 — Round-trip + guardrail tests, test-first.** A test walking goal → assay →
  pipeline → persisted-assay → manifest/label; the sample-sheet pass/refuse cases; the
  `--tools` command-assembly assertion; a germline-unchanged regression. All synthetic
  fixtures, no real nf-core run in CI.
- **M8 — End-to-end acceptance (the roadmap's stated acceptance,
  `CAPABILITY_ROADMAP.md:285`).** One test that walks intake → plan → run (injected
  executor writing a synthetic sarek somatic output tree
  `variant_calling/<caller>/<tumor>_vs_<normal>/*.vcf.gz`) → verify, asserting the run is
  labelled `somatic_variant_calling` and yields a **scoped somatic verdict** over the
  somatic VCFs. This is the single test proving the assay is real end-to-end, not just
  unit-correct at each seam.
- **M9 — RunRecord / launch.json backward-compatibility.** Persisting `assay` (M2) adds a
  field to the reproducibility contract. It **must** be optional/defaulted so the ~12
  already-shipped bundles and legacy `launch.json` sidecars still `rerun`/`verify`
  without error (legacy record with no persisted assay → fall back to the current
  `assay_for_pipeline(...) or "rnaseq"` derivation). A regression test loads a
  pre-change-shaped record and asserts it still resolves.

### Should-have

- A clear skip/label so `contig methods` and reports read "somatic (tumor–normal),
  research use," never a clinical claim.
- Datashape awareness of tumor/normal pair counts surfaced in the `Plan` warnings
  (`planner.py:43-45`) — nice for intake but not required for the verdict.

### Nice-to-have (explicitly deferred to follow-on slices)

- VAF-distribution plausibility (C3-style), panel-of-normals presence check.
- Second-somatic-caller **concordance hook** (C1-style; Strelka2 vs Mutect2 makes this
  natural later — `concordance.py:37` `_CONCORDANCE_ASSAYS` untouched this slice).
- SV/CNV callers (Manta/ASCAT) and their output/verification surface.
- Seeded somatic-specific self-heal corpus cases beyond what structural QC needs.
- Fixing the latent `reference.py` `--gtf`-always quirk (sarek uses `--fasta` not
  `--gtf`; out of scope, note only).

## Technical Considerations

- **Architecture fit / the core deviation.** `ADD_AN_ASSAY.md` assumes one pipeline ↔
  one assay with a generic sample sheet and no runner change. Somatic violates all three
  (shared pipeline, paired sample sheet, `--tools` injection), so this is genuine
  engine work at the registry/runner/sample-sheet layer, not a pure data addition.
  M2 (assay model) and M4 (`--tools` seam) are the two net-new seams; both are designed
  to be assay-generic so future shared-pipeline assays reuse them.
- **Reproducibility/verification impact.** The persisted assay (M2) becomes part of the
  run record and must round-trip through `rerun`/`resume` and the `launch.json` sidecar
  (`cli.py:470-490`) so a somatic run reproduces as somatic. The `--tools` default
  (M4) must be captured in the reproduce manifest (it's a param, so it flows through
  params → launch.json already, but verify this).
- **Where it sits in the pipeline:** intake (sample-sheet pre-flight) → plan (routing +
  persisted assay) → run (sarek somatic via `--tools`) → verify (structural manifest,
  germline-mirroring).
- **No raw-read egress; deterministic; test-first** with synthetic fixtures. Sarek
  revision pinned to the real released `3.5.1` tag (no invented version).

## Risks & Open Questions

- **R1 — Collision-fix blast radius.** Switching the run path off `assay_for_pipeline`
  touches ~5 sites; a miss silently mislabels germline or somatic. *Mitigation:* a
  germline-unchanged regression test is a must-have (M2/M7); audit each site.
- **R2 — `--tools` slug correctness.** sarek expects lowercase caller tokens
  (`strelka`, `mutect2`); an unverified slug would launch the wrong/no caller. *Mitigation:*
  pin against sarek 3.5.1 params docs; the command-assembly test asserts the exact token.
- **R3 — Manifest under-enforcement.** Mirroring germline means somatic present/gzip is
  only checked at `contig verify` time, not in the live loop (existing behavior). If a
  design partner needs live enforcement, that's a follow-on (`_discover_qc` wiring).
- **R4 — Demand-pull.** Roadmap-push, not partner-pull (see Problem Statement). Revisit
  at the gate.
- **R5 — "Launchable" (cut A) is proven only against injected fixtures.** A real sarek
  somatic run may need extra reference assets Contig's `resolve_reference` doesn't wire —
  Mutect2 typically wants a **panel-of-normals** and a **germline resource**; sarek can
  run tumor–normal without a PON but may warn or lose sensitivity. So M4/G4 prove the
  `--tools` **command is correctly assembled**, not that a real somatic run completes on
  real compute. *Mitigation:* scope G4 honestly to command-assembly; add PON/germline-
  resource wiring to the deferred follow-on list; note it so a live run isn't a surprise.
- **R6 — Collision-fix blast radius (M2).** Switching the run path off
  `assay_for_pipeline` touches `cli.py:505/850/1296/1352` + `methods.py:103`; a missed
  site silently mislabels germline or somatic. *Mitigation:* enumerate each site's
  post-change contract in `tech-plan`; land M2 + its germline-unchanged regression as an
  early task so a regression can't hide inside the somatic diff; keep `assay_for_pipeline`
  as the legacy fallback (M9), don't delete it.
- **OQ1 (gate):** confirm the four **[ASSUMED]** decisions (proceed; cut A; persist-assay;
  Strelka2+Mutect2), or flip any.
- **OQ2 (gate):** is command-assembly-only proof (R5) acceptable for "launchable," or do
  you want PON/germline-resource wiring pulled into slice 1 (larger)?

---

## Areas to strengthen (self-critique — for the review gate)

| Dimension | Rating | Note |
|---|---|---|
| Problem definition | 🟢 | Clear, evidenced; demand-pull caveat stated honestly. |
| User understanding | 🟡 | Personas inherited from PRODUCT_SPEC; no *validated* somatic user (R4). |
| Success metrics | 🟡→🟢 | Were binary test-pass; M8 adds the end-to-end acceptance the roadmap names. |
| Scope clarity | 🟢 | Explicit out-of-scope + deferred list; cut-line A/B made explicit. |
| Edge cases & risks | 🟡→🟢 | Added multi-tumor / tumor-only / germline-sheet edge cases + R5/R6. |
| Feasibility signal | 🟡 | M2 blast radius + M9 backward-compat now called out; per-task effort lands in `tech-plan`. |
| Reproducibility/verify | 🟢 | M9 protects the RunRecord/launch.json contract; persisted assay must round-trip `rerun`/`resume`. |
| Layer-2 guardrail | 🟢 | Consumes sarek; no Layer-1 drift; research-use, no clinical claim. |

**The question I'd want answered before greenlighting:** persisting `assay` on
`RunRecord` changes a reproducibility contract that already has ~12 shipped bundles —
have we decided M2+M9 land as an *isolated, regression-tested first task* (so a germline
mislabel can't hide inside the somatic diff), and is command-assembly-only proof (R5)
genuinely enough to call cut A "launchable," or is that a scope we're quietly deferring
while claiming the assay "runs"?

## Out of Scope

- VAF/panel-of-normals plausibility, concordance hook, SV/CNV callers, single-cell and
  any other assay, live-loop manifest enforcement, the `reference.py --gtf` quirk, and
  **any clinical interpretation** — a somatic verdict is "ran correctly and
  reproducibly," research-use only, never a cancer diagnosis (`USE_CASE_UNIVERSE.md`
  bright line).

## Guardrail check (CLAUDE.md) — clean

Layer-2 only (consume sarek somatic, never author it); no raw-read egress; no clinical
over-claiming; test-first.

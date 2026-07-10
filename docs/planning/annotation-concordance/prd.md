# PRD: annotation-concordance (C7 M4 — VEP-vs-SnpEff annotation concordance)

Status: draft for review. Owner: aliz. Branch: `feat/annotation-concordance/aliz`.
Slug: `annotation-concordance`.
Sources: `docs/planning/_card/issue.md` (contig-next handoff), `_card/understanding.md`
(Phase-2 dig, validated by three read-only agents), the initiative PRD
`docs/planning/variant-annotation-assay/prd.md` (M4 row, line 85), and
`docs/technical/CAPABILITY_ROADMAP.md` C7.

Capability: **C7 milestone M4** — the fourth verification axis for the annotation
assay. M1 (germline structural verify + provenance, v0.25.0), M2 (somatic gate,
v0.26.0), M3 (annotation plausibility, both assays, v0.26.0) are shipped. M4 adds the
**concordance** axis (C1-style); M5 (surface + full eval fold-in) remains after.

## Problem Statement

Contig now runs VEP annotation on both variant assays and verifies structurally (M1/M2)
and for plausibility (M3) that the annotation ran. But a single annotator gives no
**independent corroboration**: if VEP mis-annotates a call set (wrong cache, wrong
transcript set, a silent tool bug), M1–M3 can all pass and the researcher gets a
plausible-but-wrong annotation with no second opinion.

The C1 concordance primitive answers exactly this: run a **second independent tool** on
the same data and treat agreement as corroboration, disagreement as an honest WARN.
Contig already does this for germline callers (`--concordance-vcf`), RNA-seq quantifiers
(`--concordance-counts`), and somatic callers (`somatic_site_overlap`, auto in the
verdict). Annotation is the one variant-assay verification family without it.

**For whom.** The variant-analysis personas (lone computational biologist, core
facility, biotech) running germline or somatic calling with annotation, who need a
defensible "two tools agree" signal in the verdict and Methods provenance — not a
clinical judgement (bright line, `USE_CASE_UNIVERSE.md:33-48`).

**Evidence it's real.** No incumbent (Galaxy, Terra, Seqera, DNAnexus, Latch, Basepair)
issues a cross-tool annotation-agreement verdict (`FEATURES.md:61-68`). It is the named
M4 milestone (`variant-annotation-assay/prd.md:85`, `CAPABILITY_ROADMAP.md:657-658`) and
the immediate next slice in an actively-shipping track.

## Goals & Success Metrics

- **G1 — A concordance axis auto-runs for both variant assays, no user input.** A run of
  `variant_calling` or `somatic_variant_calling` with both VEP and SnpEff enabled emits
  `kind="concordance"` annotation checks in the verdict, discovered in `_discover_qc`
  with no CLI flag (the somatic auto path, not the germline flag path).
  *Metric:* an integration-style test over synthetic dual-annotated fixtures shows the
  checks present in `record.qc_results` with `kind="concordance"`.
- **G2 — Two agreement metrics: consequence (WARN-capable) and gene-symbol
  (informational-only).** `consequence_concordance` = fraction of shared variants whose
  most-severe consequence term matches, **WARN-capped (< 0.90), never FAIL**.
  `gene_symbol_concordance` = fraction whose annotated gene symbol matches, **always
  PASS (informational-only)** — mirroring RNA-seq's informational `gene_overlap`
  (`count_concordance.py`), because VEP/SnpEff symbol sources diverge enough that a WARN
  would train the user to ignore the signal (resolved threshold question). It still
  reports its fraction and both tools; it just never pulls the verdict.
  *Metric:* a concordant fixture → PASS on both; a consequence-divergent fixture → WARN
  on `consequence_concordance` naming the metric and the two tools; a symbol-divergent
  fixture → PASS (informational) with the fraction reported, not WARN.
- **G3 — Never a false pass.** Only one annotator present, an unresolvable/absent
  annotation field, unreconcilable vocab, or fewer than the shared-record floor → the
  affected metric is `unverified` (value `None`), never `pass`.
  *Metric:* a single-annotator fixture and a below-floor fixture each yield UNVERIFIED,
  never PASS; a test asserts no code path emits a concordance PASS from missing inputs.
- **G4 — Both annotator versions captured into provenance.** The run records VEP and
  SnpEff tool+version as a pair, rendered in `contig methods` / the HTML provenance panel,
  and reproduced on rerun/resume.
  *Metric:* a fixture with both headers yields two provenance entries in the bundle.
- **G5 — No regression of M1/M2/M3.** The shipped structural + plausibility checks and
  their single-key CSQ-preference parser are untouched behaviorally.
  *Metric:* the existing annotation test suites stay green; M4's dual-key parse lives in
  its own module/path.

Non-goals for metrics: no FAIL severity, no exit-code change, no calibration on real
data this milestone (uncalibrated engineering defaults, consistent with the other three
concordance slices).

## User Personas & Scenarios

- **Lone computational biologist (A)** runs sarek somatic with annotation; the verdict
  card now shows "VEP vs SnpEff: 47/50 consequences agree (0.94)" — a corroboration line
  she can cite, or a WARN that tells her the two tools disagree enough to look closer.
- **Core facility (C)** wants an auditable, non-expert-legible signal that annotation was
  cross-checked; the provenance panel lists both tools + versions.
- **Biotech (D)** wants the two annotator versions pinned in the reproduce bundle for a
  defensible Methods section.

All research-use: the line is "two tools agree on the consequence/gene," never "this
variant is pathogenic."

## Requirements

### Must-have

- **M-1 Enable SnpEff alongside VEP.** Widen `default_params.tools` on both registry
  entries: germline `haplotypecaller,vep` → `haplotypecaller,vep,snpeff`
  (`registry.py:53`); somatic `strelka,mutect2,vep` → `strelka,mutect2,vep,snpeff`
  (`registry.py:40`). Injection stays non-destructive via the existing `setdefault`
  merge (`cli.py:295-316`) — a user's own `--tools` still wins — and re-applies on
  rerun/resume through the single `_dispatch_run` call site (`cli.py:555`). Update the
  stale narrating comments at `registry.py:29-39` / `:47-52`. Update the exact-string
  test assertions (`test_run_default_params.py`, `test_somatic_end_to_end.py:102`).
- **M-2 New concordance verifier** `verification/annotation_concordance.py`, cloned from
  `somatic_concordance.py`'s contract: a module-local `_concordance(...)` factory tagging
  `kind="concordance"`; key on `(CHROM,POS,REF,ALT)`; module-local `_WARN_BELOW = 0.90`
  and `_MIN_SHARED_VARIANTS = 10`; statuses limited to pass/warn/unverified (never fail).
- **M-3 Two annotation-set discovery layouts:**
  - **(primary) two separate VCFs** — a VEP-annotated VCF and a SnpEff-annotated VCF,
    each selected by a `vep` / `snpeff` **path component** below the run dir (mirroring
    somatic's `mutect2`/`strelka` selection), joined on the site key.
  - **(fallback) one VCF carrying both** `CSQ` and `ANN` INFO fields — parsed in a single
    dual-key pass. This path must NOT reuse M3's single-key driver (which prefers CSQ and
    ignores ANN); M4 owns a dual-key parse so M3 cannot regress (G5).
  - The verifier **records which layout it detected** (two-file vs single-VCF-both) in
    the result message / a debug breadcrumb, so a live run's actual sarek layout is
    visible rather than silently assumed. The single-VCF fallback is exercised by a
    dedicated synthetic fixture (it has no real-sarek CI trigger — gap-fix 2).
- **M-4 Consequence agreement** (`consequence_concordance`): per shared variant, collapse
  each tool's terms to a single most-severe consequence via the reused M3 primitives
  (`_variant_terms`, `_resolve_consequence_index`, `_most_severe_rank`, `_SEVERITY_RANK`),
  agreement = exact most-severe-SO-term match. WARN < 0.90; UNVERIFIED below the floor.
- **M-5 Gene-symbol agreement** (`gene_symbol_concordance`, **informational-only, always
  PASS**): extract the gene symbol per tool (CSQ `SYMBOL` subfield resolved from the
  header `Format:` string; SnpEff ANN `Gene_Name` at fixed index 3). Normalization is
  **fixed and minimal (gap-fix 1): case-fold + strip whitespace + treat empty/`.` as
  unresolvable. No alias table this milestone.** Agreement = symbol match over shared
  variants where both symbols are resolvable; a variant whose symbol is unresolvable on
  either side is excluded from the denominator. Any residual mismatch after case-folding
  counts as a **genuine disagreement** in the fraction (not UNVERIFIED). UNVERIFIED is
  reserved for the *unresolvable* case only: fewer than `_MIN_SHARED_VARIANTS` resolvable
  pairs. Because it is informational-only it reports its fraction but never WARNs/FAILs.
- **M-6 Auto-wire** both metrics into `_discover_qc` inside the existing
  `if assay in VARIANT_ASSAYS:` block (`runner.py:150-163`), extending the same
  `results` list. Clean `[]` skip when only one annotator is present; one UNVERIFIED on
  an ambiguous multi-file layout (mirroring `select_caller_vcfs`).
- **M-7 Provenance pair.** Capture both VEP and SnpEff tool+version. Extend the
  provenance capture (`bundle.compute_annotation_identity` + the `RunRecord` field, today
  singular at `models.py:297`) to a pair/list, serialized into the bundle and rendered in
  `contig methods` / HTML; re-derived on rerun/resume. Keep the singular
  `AnnotationProvenance` model shape per entry; the container becomes a list. **Back-compat
  (gap-fix 3):** a Pydantic field validator accepts EITHER a single object or a list and
  normalizes to a list, so pre-M4 bundles (`annotation_identity` as one object) still load,
  `contig verify`, and reproduce. Covered by a regression test loading a pre-M4 bundle.
- **M-8 Honest verdict contract.** Concordance is at most WARN, never changes the
  `verify` exit code (exit is driven only by output drift / signature mismatch). No
  pathogenicity or clinical claim is emitted; the message attributes everything to the
  two tools + versions.

### Should-have

- **S-1** Concordance results grouped under the existing `kind=="concordance"` display
  split (`report.py:101-109`) on the dashboard/HTML — should already work by kind, verify.
- **S-2** A `contig methods` line naming both annotators and the concordance outcome.

### Nice-to-have

- **N-1** A `--concordance-annotation` explicit CLI echo (the auto path covers the
  verdict; a flag is optional parity with the germline path). Deferred unless trivial.

## Technical Considerations

- **Reuse over new machinery.** The consequence collapse is entirely M3's primitives
  (`annotation_plausibility.py`); the concordance contract is entirely
  `somatic_concordance.py`'s shape. M4 writes a keyed two-set join and a gene-symbol
  extractor, nothing more novel.
- **Parser isolation (hard constraint, G5).** M3's `annotation_plausibility.py` prefers
  CSQ and single-keys per file. M4's single-VCF-both-fields fallback needs BOTH keys, so
  it must implement its own dual-key extraction (or a new shared helper that M3 is *not*
  switched onto in this milestone) — never mutate M3's driver in place.
- **Verification axes are the shipped three.** Structural (M1/M2), plausibility (M3),
  concordance (M4). No new verification primitive is invented; `kind="concordance"`
  already exists (`models.py:64`) and `overall_verdict` is kind-blind on status.
- **No models, no proprietary data.** VEP/SnpEff + their DBs are consumed as-is; a better
  base model makes disagreement-adjudication better, never redundant (`CLAUDE.md` #2/#3).
- **Reproducibility.** Widening `tools` flows through the persisted `launch.json` and the
  single `_dispatch_run` injection, so rerun/resume already re-apply it. The provenance
  pair must round-trip through the bundle and reproduce path.
- **Known resume quirk (pre-existing, flag not fix).** `resume` doesn't pass `assay=`, so
  a resumed somatic run re-injects the *germline* tools string
  (`assay_for_pipeline("nf-core/sarek")` → `variant_calling`). M4 widens both strings so
  the quirk's blast radius is unchanged; note it, don't fix it here.

## Data Model

- `RunRecord.annotation_identity`: today `AnnotationProvenance | None` (singular,
  `models.py:297`). M4 → a list/pair of `AnnotationProvenance` (one per annotator).
  Preserve backward-compatible deserialization of old singular bundles.
- Per-entry `AnnotationProvenance` (`models.py:206-216`: `tool`, `version`, `raw_header`)
  is unchanged.

## Artifact / Run Contracts

- New `kind="concordance"` `QCResult`s: `consequence_concordance`,
  `gene_symbol_concordance` (value = fraction rounded to 4dp, `expected_range=">= 0.90"`,
  message naming both tools + the shared count).
- UNVERIFIED sentinel: literal status `"unverified"` + `value=None` (no new constant),
  matching all sibling concordance modules.

## Risks & Open Questions

- **R1 — over-claiming on legitimate disagreement (the main risk).** VEP and SnpEff
  differ on transcript models and can legitimately assign different most-severe
  consequences to the same variant. Mitigation: WARN-cap (never FAIL), uncalibrated-but-
  loose 0.90 default, UNVERIFIED below the shared floor, and message wording that frames
  it as corroboration, not correctness. **No FAIL until calibrated on real data.**
- **R2 — gene-symbol vocab divergence (the added risk from the scope choice). RESOLVED:**
  VEP `SYMBOL` and SnpEff `Gene_Name` can draw from different symbol sources, so
  `gene_symbol_concordance` is **informational-only (always PASS)** — it reports its
  fraction but never pulls the verdict, spending the WARN budget only on the more
  diagnostic `consequence_concordance`. Normalization is fixed and minimal (case-fold +
  strip + empty/`.` → unresolvable, no alias table). UNVERIFIED is reserved for too-few
  resolvable pairs. This neutralizes the "trains users to ignore WARNs" failure mode.
- **R3 — sarek dual-annotator output layout is unverified against a real run.** The
  two-file-vs-one-file question is resolved *defensively* (M-3 handles both), but the
  actual sarek `--tools vep,snpeff` on-disk layout/file-naming is not exercised in CI
  (no real sarek run). Mitigation: path-component selection + UNVERIFIED on an
  unrecognized layout; the live-cache caveat (below) already means a real run may not
  produce a second annotated VCF, in which case the check honestly skips/UNVERIFIEDs.
- **R4 — live-cache caveat (carried from M1–M3).** Enabling `--tools …,snpeff` makes
  sarek *want* to annotate, but a real run may need a SnpEff cache
  (`--snpeff_cache`/`--download_cache`) Contig does not yet wire. When the second
  annotation is absent, M4 degrades to UNVERIFIED (never a false pass), so the slice is
  shippable on synthetic fixtures regardless.
- **R5 — provenance list migration.** Changing `annotation_identity` from singular to a
  list touches serialization and reproduce. Mitigation: tolerant deserialization of old
  bundles (accept a singular value → one-element list), covered by a test.
- **Open:** whether to also expose the explicit CLI echo (N-1) — default no.

## Out of Scope

- FAIL severity on any annotation concordance band (until calibrated on real data).
- M5 work beyond the provenance pair: the "corroborated by" verdict-card line, full
  DB-version (cache) provenance, and folding annotation outcomes into the C6 eval corpus.
- Wiring a SnpEff cache / `--step annotate` (the live-cache fix); M4 stays honest via
  UNVERIFIED when annotation didn't run.
- Non-sarek / standalone annotation pipelines.
- Research prioritization (ACMG, rare-disease inheritance, PGx, PRS) — deferred per the
  initiative's verify-only decision.
- Switching M3's plausibility parser onto a dual-key path (explicitly avoided, G5).

## Guardrail check (CLAUDE.md)

On-thesis Layer-2 verification, not Layer-1 authoring. No wet-lab/clinical credentials,
no proprietary data. Research-use only — concordance is corroboration, never a
pathogenicity/clinical verdict; UNVERIFIED is never rendered as PASS. Compounds moat #2.

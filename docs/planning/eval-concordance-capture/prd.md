# PRD: eval-concordance-capture

Complete the v0.51.0 C6 fold-in's capture side so the corroboration families
(concordance + the two plausibility gaps) are captured into
`RunRecord.verification_inputs` like every other scoreable family.

## Problem Statement

The C6 fold-in (v0.51.0) shipped labeled verification capture for seven families —
`multiqc`, `rnaseq_plausibility`, `rnaseq_composition`, `scrnaseq`, `methylseq`,
`ampliseq`, `mag`, `germline` — and explicitly deferred the rest: "concordance-family
capture deferred (PRD R4a)" (`CHANGELOG.md` v0.51.0; the deferral is a code comment at
`src/contig/verify_corpus.py:80-82`: *"PRD R4a: capture deferred, status DERIVATION in
scope"*).

Consequences of the gap, in the code:

1. A WARN/FAIL **somatic** or **annotation** run appends a pending verification case
   (`self_heal.py:1754-1765`, `should_capture_verification` at
   `verify_corpus.py:438-455`) whose `inputs` carry **none of the families that
   actually flagged it** — `concordance_somatic_overlap` (Mutect2 vs Strelka2,
   auto-wired at `runner.py:428`) and `somatic_plausibility` / `annotation_plausibility`
   (scoreable in the guard, `verify_corpus.py:72-73`) are never written by
   `_discover_qc`. The promoted case's re-derived verdict ignores the very checks that
   produced the label.
2. The guard's concordance families (`_CONCORDANCE_FAMILY_KINDS`,
   `verify_corpus.py:83-88`) are only reachable from hand-authored holdout fixtures;
   real-run concordance outcomes never feed the corpus — the compounding eval-data
   moat (moat #2, `CLAUDE.md`) stays thin for the C1 headline primitive.
3. Every C1 slice defers FAIL-severity "once thresholds are calibrated on real data"
   (`CAPABILITY_ROADMAP.md` C1). Calibration requires a labeled corpus of pre-band
   concordance inputs; capture is the unblocked prerequisite.

**What happens if we don't build this:** the R4a deferral stays open indefinitely,
the guard's coverage claim stays structurally incomplete for corroboration families,
and C1 calibration stays blocked on data nobody is collecting.

## Goals & Success Metrics

**Goal:** make every scoreable, run-dir-derived verification family capturable —
capture is complete for what the code can actually derive at record time.

Metrics (all test-pinned, none chasing a headline number):

- **Capture completeness:** `_discover_qc` writes `capture_inputs` entries for
  `concordance_somatic_overlap`, `concordance_consequence`, `somatic_plausibility`,
  and `annotation_plausibility` — the four families that are auto-wired but
  uncaptured today.
- **Round-trip:** a pending case appended from a synthetic WARN/FAIL somatic or
  annotation run carries those families in `inputs`, in the `{family: {sample:
  {metric: float}}}` contract shape (`models.py:363-370`), and promotes through
  `contig verify-case-promote` unchanged.
- **No composition move:** `verify-guard`, `eval-guard`, `heal-guard` baselines are
  unmoved (derivation and corpora are untouched; capture adds cases, not thresholds).
  The mutation control (`tests/test_verify_corpus.py:66-94`) still passes.
- **No contract change:** no signature break (capture only adds values to the
  existing additive `verification_inputs` field on new runs), no new dependency,
  stdlib-only, no real nf-core run or network in CI.

## User Personas & Scenarios

- **The founder / evaluation loop:** runs `contig verify-guard` and the corpus
  promote channel. Today a promoted somatic case's inputs say nothing about the
  checks that flagged it; after this slice the pending case is self-describing.
- **Design-partner lab (future):** their real WARN/FAIL runs append pending cases
  whose corroboration inputs ride the corpus — the compounding flywheel
  (`ROADMAP.md` Phase 3) starts for concordance without any user-visible change.
- No dashboard surface in this slice; no CLI surface change (`verification_inputs`
  is internal provenance, already rendered nowhere user-facing except the pending
  corpus).

## Requirements

### Must-have

- **M1 — Somatic concordance capture.** `evaluate_somatic_concordance` /
  `evaluate_somatic_concordance_from_run` gain a `capture_metrics`-style out-param
  (the germline precedent at `runner.py:339-344`) exposing the raw `shared` /
  `union` / `jaccard` currently discarded after stringification
  (`somatic_concordance.py:133-161`). `_discover_qc`'s somatic branch
  (`runner.py:428`) writes
  `capture_inputs["concordance_somatic_overlap"] = {"mutect2_vs_strelka2":
  {"value": jaccard, "n_shared": union}}` when computable — exactly the shape
  `_concordance_status` consumes (`verify_corpus.py:159-180`). Not captured (absent
  key) when no second caller / no PASS sites — never a fabricated value.
- **M2 — Annotation concordance capture.** Same out-param pattern for
  `evaluate_annotation_concordance_from_run` (shared/matches are internal at
  `annotation_concordance.py:170-198`); `_discover_qc`'s `VARIANT_ASSAYS` branch
  (`runner.py:378`) writes `capture_inputs["concordance_consequence"] =
  {"vep_vs_snpeff": {"value": agreement, "n_shared": shared}}`.
- **M3 — Somatic plausibility capture.** The somatic branch's plausibility metrics
  (`median_vaf`, `strelka_median_vaf`, `somatic_variant_count`, `normal_median_vaf`)
  write `capture_inputs["somatic_plausibility"] = {"sample": {metric: float}}`.
  `pon_applied` is excluded by design (non-numeric 3-state string; the
  `verification_inputs` contract is float-valued and `pon_applied` never enters
  `evaluate()`).
- **M4 — Annotation plausibility capture.** `annotation_real_fraction` and
  `annotation_consequence_distribution` write
  `capture_inputs["annotation_plausibility"] = {"sample": {...}}`.
- **M5 — Round-trip & guard integration pinned.** Tests prove a pending case from a
  synthetic WARN/FAIL somatic/annotation run carries all four families and
  re-derives through `evaluate_verify_case` to the same status the QCResult drove
  (band-sensitive via the live threshold imports at `verify_corpus.py:98-103`).
  **Per-kind, not once:** the `n_shared` semantics differ per family (somatic =
  union of PASS sites, consequence = shared variants), so each captured family
  gets its own status-consistency pin — a divergence between captured-input
  re-derivation and the QCResult's own status is a test failure, never a silent
  corpus lie. Holdout and baselines untouched.
- **M5b — Message stability pinned.** The stats out-params refactor
  `evaluate_somatic_concordance` / `evaluate_consequence_concordance`, which today
  embed the raw counts in the QCResult message before discarding them
  (`somatic_concordance.py:156-157`, `annotation_concordance.py:170-198`); the
  emitted messages must stay byte-identical (existing wiring tests may pin them).
- **M6 — Docs updated.** The fold-in's deferral signature (comment at
  `verify_corpus.py:80-82`), `_discover_qc` docstring (`runner.py:296-300`),
  `CHANGELOG.md` Unreleased, and the C6 section of `CAPABILITY_ROADMAP.md` all say
  R4a is closed for the run-dir-derived families.

### Should-have

- **S1 — Deferred families documented with a committed revisit trigger.** Germline
  (`concordance_genotype`), RNA-seq (`concordance_spearman`), single-cell
  (`concordance_spearman`) capture stays deferred with a named trigger: the day a
  second call set / count matrix is run-dir-derivable for those assays, or a
  verify-time capture channel that can touch the record without breaking the signed
  payload. Stated in the same three docs as M6.

### Nice-to-have

- **N1 — A `# sample keys` stability test** enumerating the four captured
  concordance/plausibility family keys so a fifth is a deliberate act (the
  `test_verify_capture.py` docstring list is the de-facto registry today).

## Technical Considerations

- **Capture contract:** `verification_inputs: dict[str, dict[str, dict[str, float]]]`
  (`models.py:363-370`), family → sample → metric → float. Empty normalizes to
  `None` at `runner.py:1291`. The out-param is threaded through
  `_discover_qc(run_dir, assay, *, capture_inputs)` (`runner.py:285-296`); absent the
  param nothing is collected (additive, back-compat).
- **Family keys must match the guard exactly:** `concordance_somatic_overlap`,
  `concordance_consequence` (`_CONCORDANCE_FAMILY_KINDS`, `verify_corpus.py:86-87`),
  `somatic_plausibility`, `annotation_plausibility` (`_FAMILY_PACKS`,
  `verify_corpus.py:72-73`). No guard-side change is needed — the scorer resolves
  them today.
- **Sample-key convention:** concordance families use stable pair labels
  (`mutect2_vs_strelka2`, `vep_vs_snpeff`) — `_concordance_status` iterates values
  only (`verify_corpus.py:168`), so any stable key works; plausibility families use
  sample names like every other family.
- **Stats exposure:** the two concordance evaluators currently discard the raw
  counts after message stringification; the `capture_metrics=` out-param on
  `evaluate_variant_plausibility` (`runner.py:339-344`) is the in-repo precedent.
- **Honesty on the WARN-only design:** concordance is at most WARN, `unverified`
  below the shared-genes floor, and the pseudobulk-washout of cross-tool
  cell-calling divergence is an unproven assumption (`CAPABILITY_ROADMAP.md` C1) —
  captured cases may rarely flip a verdict. That is accepted: capture is additive;
  the slice proves coverage with the mutation control, not a headline number.
- **Reproducibility impact:** `verification_inputs` is an existing additive signed
  field; adding values on new runs is back-compat by construction and breaks no
  existing signature (`canonical_record_bytes` full-dump, but only new runs carry
  the new keys). `rerun`/`resume` re-derive capture identically since it re-enters
  `run()`.
- **Test-first, no network:** synthetic fixtures (two-caller VCFs, annotated VCFs,
  STARsolo-shaped artifacts as needed); no real nf-core/sarek/VEP run in CI.

## Feasibility & Effort

**S–M slice.** Four `capture_inputs` writes (two concordance, two plausibility), two
stats out-params (`evaluate_somatic_concordance`, `evaluate_consequence_concordance`
— the only non-additive code, and the effort concentrates there), capture +
round-trip + status-consistency tests, docs (M6/S1). One focused worktree branch;
no new module, no dependency, no dashboard.

## Risks & Open Questions

- **R1 — Corpus-composition move (guarded against):** capture could alter
  `verify_history.jsonl` only via promote-time snapshots; baselines must stay
  byte-identical because derivation and holdout are untouched. Pinned by M5 +
  CI guards.
- **R2 — UNVERIFIED-capture semantics:** a located-but-unparseable concordance path
  yields no inputs (family absent) while the QCResult says `unverified` — consistent
  with every existing family (`if capture_inputs is not None and <metrics>`
  pattern), and `_concordance_status` re-derives `unverified` from a low `n_shared`
  exactly as the module does. No false pass.
- **R3 — Threshold drift:** `_CONCORDANCE_KIND_THRESHOLDS` imports module constants
  live; a future band change flips stored cases' re-derived status (the mutation
  control pins this is intended). This slice changes no thresholds.
- **OQ1 — `somatic_plausibility` sample key:** the Mutect2 VCF has one tumor sample;
  capture keys by sample name from the VCF header (`##tumor_sample=`), falling back
  to the pair label if unresolvable. (Settled as a design detail, not a question.)
- **OQ2 — None:** germline/count/sc deferral trigger (S1) is the only open scope
  decision and it is settled per the interview.

## Out of Scope

- Germline, RNA-seq, and single-cell concordance **capture** (deferred with the S1
  revisit trigger; their second sets exist only at verify time).
- A verify-time capture channel that mutates the signed record post-finalize.
- FAIL severity / band calibration for any concordance or plausibility family — this
  slice only starts collecting the data calibration needs.
- `.h5ad`/AnnData parsing; `fraction_agreeing`/`gene_overlap` guard families
  (no scorer family exists for them today — out of scope, not silently dropped).
- Any dashboard surface, any CLI surface change, any `FailureClass`, any new
  dependency.

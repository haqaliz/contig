# Phase 1 (M2) report — enable somatic annotation + gate structural verifier + gate provenance

Slug/aspect: `annotation-plausibility` / `verify` · Branch: `feat/annotation-plausibility/aliz`
Scope: Phase 1 (M2) ONLY, per `docs/planning/annotation-plausibility/verify/plan_20260710.md`.
Phases 2–5 (CSQ/ANN plausibility parser, rule pack, wiring, docs) were NOT touched.

## Summary

The germline annotation structural verifier + `AnnotationProvenance` capture shipped
in C7 M1 is now enabled and gated identically for the somatic assay. No new
verification algorithm was written — this is pure enablement (somatic sarek now
runs `vep`) plus widening two existing gates from germline-only to both variant
assays.

## Files changed

- `src/contig/registry.py`
  - Somatic `PipelineEntry.default_params` changed from `{"tools": "strelka,mutect2"}`
    to `{"tools": "strelka,mutect2,vep"}`. Comment updated to explain the C7 M2
    rationale. Ordering (`somatic_variant_calling` entry before `variant_calling`,
    so `_ASSAY_BY_PIPELINE`'s last-write-wins keeps `"nf-core/sarek" -> "variant_calling"`
    as the legacy fallback) is unchanged.
  - Added a shared module constant `VARIANT_ASSAYS = ("variant_calling",
    "somatic_variant_calling")`, since the two-assay pair is now referenced in two
    different modules (`runner.py` and `self_heal.py`) — hoisted per the plan's
    instruction rather than duplicating the literal tuple. Placed in `registry.py`
    since both strings originate from that module's `PipelineEntry.assay` values,
    and both consumers already depend on `contig.registry` for `assay_for_pipeline`.
- `src/contig/runner.py`
  - Imported `VARIANT_ASSAYS` from `contig.registry`.
  - Widened the annotation-structural gate in `_discover_qc`
    (previously `if assay == "variant_calling":`) to `if assay in VARIANT_ASSAYS:`.
    The "first VCF whose header declares CSQ/ANN wins" `rglob` scan is untouched
    (reused verbatim) — only the gating condition changed.
  - No plausibility block was added (that is Phase 4, out of scope here).
- `src/contig/self_heal.py`
  - Imported `VARIANT_ASSAYS, assay_for_pipeline` from `contig.registry`.
  - In `_finalize`, the previously-unconditional
    `record.annotation_identity = compute_annotation_identity(run_dir)` is now
    gated: resolve `resolved_assay = record.assay or assay_for_pipeline(record.pipeline)`
    (mirrors the exact pattern already established in `methods.py:119` for the
    same disambiguation problem — somatic and germline share the `nf-core/sarek`
    pipeline string, so the pipeline-derived fallback alone can't tell them apart;
    `record.assay` is preferred and is always populated for anything dispatched
    through the current `run_pipeline`/`self_heal_run` path). Capture fires when
    `resolved_assay is None or resolved_assay in VARIANT_ASSAYS`. The `None` arm is
    the plan's explicit safety net for a legacy/foreign-pipeline record where
    neither field resolves — in that case we still attempt the capture rather than
    silently dropping provenance for what might be a genuine variant run;
    `compute_annotation_identity` itself already degrades to `None` when nothing is
    found, so this arm can never fabricate a false provenance record. In the
    current codebase every record reaching `_finalize` has `record.assay` set (it's
    threaded through from `self_heal_run`'s `assay` param, default `"rnaseq"`), so
    the `None` arm is a defensive fallback, not something exercised by the live
    dispatch path today — but it is covered by the concern below.

## Tests added / modified

- `tests/test_annotation_registry.py` (extended): `test_somatic_default_params_enable_vep`
  (asserts `vep`, `strelka`, `mutect2` all present) and
  `test_inject_does_not_override_user_tools_somatic` (asserts `_inject_default_params`
  does not clobber a user-supplied `--tools` for somatic).
- `tests/test_annotation_somatic_gate.py` (new):
  - `test_annotated_somatic_run_verifies` — a synthetic gzipped VEP-annotated VCF at
    `results/annotation/tumorA_vs_normalA/mutect2/tumorA_VEP.ann.vcf.gz`; asserts
    `_discover_qc(tmp_path, assay="somatic_variant_calling")` yields
    `annotation_present: pass` and `annotation_complete: pass` (value `1.0`).
  - `test_unannotated_somatic_run_yields_no_false_pass` — an un-annotated somatic
    VCF; asserts no `annotation_*` check reports `pass` (mirrors
    `test_annotation_integration.py`'s germline counterpart verbatim: when no VCF
    declares CSQ/ANN at all, the structural block skips rather than emitting an
    explicit UNVERIFIED — the "no false pass" guarantee, not "always non-empty").
  - `test_non_variant_assay_does_not_capture_annotation_provenance`,
    `test_germline_variant_assay_captures_annotation_provenance`,
    `test_somatic_variant_assay_captures_annotation_provenance` — drive the REAL
    seam: `self_heal_run(...)` end-to-end with a fake executor, over a run dir that
    already carries an "incidental" VEP-annotated VCF before the run executes.
    Confirms `record.annotation_identity` is `None` for `assay="rnaseq"` and
    populated (`tool == "VEP"`) for both `variant_calling` and
    `somatic_variant_calling`.
- `tests/test_run_default_params.py` and `tests/test_somatic_end_to_end.py`
  (pre-existing tests updated, not new coverage): five assertions that pinned the
  OLD somatic default (`"strelka,mutect2"`) were updated to the new
  `"strelka,mutect2,vep"` value — this is the direct, intended consequence of the
  registry change and mirrors exactly how the equivalent germline tests were
  updated in C7 M1 (`test_germline_sarek_run_injects_annotation_tools` already
  expected `"haplotypecaller,vep"`).

## Validation

- `uv run pytest tests/test_annotation_registry.py tests/test_annotation_somatic_gate.py tests/test_annotation_integration.py tests/test_annotation_provenance.py -q`
  → all green.
- Full `uv run pytest -q` → all green, exit code 0 (1266 passed, 1 skipped;
  pre-existing skip, unrelated to this change).
- Confirmed no baseline/corpus files (`src/contig/data/*baseline*`, corpus files)
  changed — `git diff --stat` shows only `registry.py`, `runner.py`, `self_heal.py`,
  and the listed test files.

## Concerns / notes for the integrator

- `docs/planning/_card/issue.md` was already modified in the worktree before this
  phase started (pre-existing dirty state from card setup, unrelated to M2). It was
  left untouched and is NOT part of this phase's commit.
- The `resolved_assay is None` fallback-to-capture arm in `self_heal.py` is
  currently unreachable via the live `self_heal_run` dispatch path (every record
  reaching `_finalize` has `record.assay` populated, defaulting to `"rnaseq"`), so
  it is a defensive safety net rather than something the current engine exercises
  in practice. It is still directly testable/correct as written; flagging in case
  the integrator wants a more targeted regression test against a hand-built
  `RunRecord`/`_finalize` call with `assay=None` and an unregistered pipeline
  string (not added here since driving the real seam was preferred per the task
  instructions, and the real seam always populates `record.assay`).
- No changes were made to `src/contig/verification/rule_pack.py`,
  `annotation_plausibility.py`, or any plausibility logic — those are Phase 2+ and
  out of scope for this phase.

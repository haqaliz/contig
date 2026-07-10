# Understanding: annotation-germline-structural-verify (Phase 2 deep dig)

Dig date: 2026-07-10. Validated against the worktree code by two read-only agents.

## What the work really is

C7 milestone **M1**: enable nf-core/sarek's built-in annotation step (VEP → `CSQ`)
on the germline `variant_calling` assay, add a structural verifier that proves the
annotation **ran** (every variant carries an annotation record), and capture the
annotation tool + version into provenance (C5 `reference_identity` pattern), rendered
in `contig methods`. Research-use only — verify it EXECUTED, never adjudicate
pathogenicity. WARN-capped; UNVERIFIED (never a false pass) when no annotated VCF.

The PRD (`variant-annotation-assay/prd.md`) and the task-by-task TDD plan
(`variant-annotation-assay/plan-m1.md`) already exist and are authoritative. This dig
**validates the plan against current code** rather than re-deriving it.

## Verdict: the plan is sound. Four wiring corrections + one caveat to record.

### Confirmed as the plan assumes
- `QCResult` accepts `check/status/message/value/kind`; `QCStatus` includes
  `pass/warn/fail/unverified`; `QCKind` includes `structural`. (`models.py:55,64,67`)
- `ReferenceIdentity` at `models.py:192`; `AnnotationProvenance` inserts cleanly after it.
- `RunRecord.reference_identity` at `models.py:283`; `assay` at `models.py:290`;
  `Literal` + pydantic `BaseModel` imported at top.
- `_discover_qc(run_dir: Path, assay: str = "rnaseq")` at `runner.py:106`; the
  `if assay == "variant_calling":` block at `runner.py:133` uses
  `run_dir.rglob(pattern)` — the plan's added rglob loop is consistent.
- `_finalize` sets `record.reference_identity = compute_reference_identity(...)` at
  `self_heal.py:1260`; bundle import to extend is `self_heal.py:25`.
- `_reference_clause` composition site is inside `render_methods` at `methods.py:121-127`.
- `somatic_plausibility.py` is the correct mirror: its own gzip-transparent `_open_text`,
  assay-gated in `_discover_qc`, WARN-capped, UNVERIFIED-when-absent.
- `PipelineEntry.default_params` exists (`models.py:152`); somatic entry injects
  `{"tools":"strelka,mutect2"}`; germline entry currently has NO `default_params`
  (asserted by `test_run_default_params.py:166`) — exactly the pre-change state.
- `_inject_default_params` (`cli.py:295`) uses `params.setdefault` — non-clobbering;
  called in `_dispatch_run` (`cli.py:555`) which is shared by run/rerun/resume, so it
  is re-injected on reproduce (asserted by `test_rerun_reinjects_tools_via_persisted_assay`).
  `build_nextflow_command` (`runner.py:302`) serializes `{key:value}` → `--key value`.

### Plan corrections REQUIRED before implementing (Agent A)
1. **`methods.py` public renderer is `render_methods(record)`, NOT `methods_text`.**
   Plan Task 3's snippet imports/calls `methods_text` — will `ImportError`. Use
   `render_methods`; append `_annotation_clause(record)` into the `render_methods`
   composition (after `_reference_clause`).
2. **Test helper is `_record(**overrides)` in `tests/test_methods.py:19`, NOT
   `_minimal_target`.** Plan Tasks 3/5 fixtures must use `_record(...)` (min required
   RunRecord fields: `run_id`, `pipeline`, `pipeline_revision`, `target`,
   `input_checksums`).
3. **`QCResult` has a 6th field `expected_range`** (between `value` and `kind`).
   Harmless for construction (defaulted); only matters if a test asserts an exact
   field set. Do not assert "exactly five fields."
4. **`sha256_file` is defined in `contig.models`, re-exported via `bundle.py:14`.**
   Cosmetic — the plan's import extension of `bundle.py:14` still works.

### Sarek annotation caveat — RESOLVED (Agent B)
- **CI slice is SAFE.** M1 tests only assert (a) the germline registry entry's
  `default_params` carries `tools` containing `vep`, and (b) `_inject_default_params`
  merges it non-destructively into argv. Both are backed by confirmed, already-tested
  machinery and need no VEP cache. No real VEP/sarek runs in CI.
- **Real-run caveat to record (do NOT silently assume a cache):** `src/` has ZERO
  VEP/SnpEff cache or `--step annotate` wiring. On a live sarek 3.5.1 run,
  `--tools haplotypecaller,vep` may not produce annotated output without a
  `--vep_cache`/`--snpeff_cache`/`--download_cache` (and possibly `--step annotate`),
  none of which Contig currently plumbs. The mitigating design intent: the structural
  verifier degrades to **UNVERIFIED (never a false PASS)** when annotation output is
  absent — so a missing cache surfaces honestly. Record this in the PRD Technical
  Considerations / as an M1 caveat; the live cache wiring is a legitimate follow-on.
- **Subtlety worth a note:** because `_inject_default_params` is whole-value
  `setdefault`, a germline user who passes their own `--tools haplotypecaller` (no
  `vep`) keeps their value and silently drops the annotation default. Correct
  non-override behavior, but it means the annotation default only applies when the
  user specifies no `tools` at all. Acceptable for M1; note it.

## Guardrail check
On-thesis Layer 2 (run + verify an annotation step; consume VEP/SnpEff, never author
pipelines). Research-use only, bright line honored (no pathogenicity/clinical verdict).
Inside the founder's edge. No drift to flag.

## Open decisions for the review gate
- Confirm VEP (`CSQ`) as the M1 default annotator (plan assumes `haplotypecaller,vep`);
  SnpEff `ANN` is supported by the same parser shape but not the default.
- Confirm we ship M1 CI-only with the real-run cache caveat recorded (recommended),
  rather than expanding scope to wire a VEP cache path now (that's a follow-on).

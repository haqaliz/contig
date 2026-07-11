# Task 3 report — Phase 3: locator + gate (`runner.py`)

Branch: `feat/rnaseq-mapping-composition-plausibility/aliz`
Commit: `2849fc8` — `feat(verify): wire RNA-seq read-composition gate into _discover_qc (additive, honest-absent) [rnaseq-composition]`

## What was done

Wired the already-merged `parse_read_distribution` parser (Task 1) and
`RNASEQ_COMPOSITION_PACK` (Task 2) into `_discover_qc` so a real RNA-seq run's
read composition (exonic / intronic / unassigned fractions) is checked,
following strict TDD (RED test additions first, confirmed failing, then the
implementation matching the plan's Phase 3 GREEN step verbatim).

### Files changed

- `src/contig/runner.py`
  - Import `parse_read_distribution` from `contig.verification.rnaseq_metrics`
    (added next to the other verification-module imports, ~line 42).
  - Added `RNASEQ_COMPOSITION_PACK` to the existing
    `from contig.verification.rule_pack import (...)` block (~line 46).
  - Added `_locate_rnaseq_composition_qc(run_dir) -> dict[str, dict[str, float]]`
    beside the other `_locate_*` helpers (right before `_locate_mag_qc`). Rglobs
    `*.read_distribution.txt`, derives the sample id from the filename, and for
    a sample with multiple files prefers the one whose path (relative to
    `run_dir`) has a `results` component — else the first in sorted order.
    Parses exactly one file per sample; a located-but-unparseable file yields
    an empty dict (not a dropped sample).
  - Added a new `if assay == "rnaseq":` gate block in `_discover_qc`,
    immediately after the existing MultiQC-driven rnaseq plausibility gate
    (`if assay == "rnaseq" and multiqc is not None: ...`). It iterates
    `_locate_rnaseq_composition_qc(run_dir)`; when a sample has metrics it runs
    `evaluate({sample: sample_metrics}, RNASEQ_COMPOSITION_PACK)`; when a
    sample was located but yielded no usable metric it appends one
    `rnaseq_composition_qc:<sample>` QCResult with `status="unverified"`,
    `value=None`, `kind="metric"`. No artifact at all → the block's loop body
    simply never runs (silent skip). The block carries a leading comment
    explaining: additive to the MultiQC gate above, why a dedicated gate
    (fractions not in MultiQC general-stats), `rnaseq` deliberately stays OUT
    of `_DEDICATED_METRIC_ASSAYS`, honest-absent behavior, and that the two
    rnaseq gates are kept as separate `if` blocks (mirrors the germline
    dual-gate precedent) rather than merged.
  - `_DEDICATED_METRIC_ASSAYS` was NOT touched; the structural manifest was
    NOT touched; `launch.json`/schema were NOT touched; the existing MultiQC
    rnaseq plausibility gate was NOT modified.

- `tests/verification/test_run_qc.py`
  - Added 5 new tests under a new "RNA-seq read-composition QC ingestion gate"
    section at the end of the file, using the plan's fixture content
    (`_READ_DISTRIBUTION_HEALTHY`, matching the committed
    `tests/fixtures/rnaseq/WT_REP1.read_distribution.txt` content) plus a
    deliberately-different `_READ_DISTRIBUTION_WORK_COPY` for the AC6 dedup
    assertion, and a `_write_read_distribution(run_dir, relative_dir, sample,
    text)` helper mirroring the existing `_write_*` helpers in the file:
    1. `test_discover_qc_emits_rnaseq_composition_for_rnaseq_assay` — healthy
       artifact under `results/star_salmon/rseqc/read_distribution/` →
       `exonic_fraction:WT_REP1` / `intronic_fraction:WT_REP1` /
       `unassigned_fraction:WT_REP1` all `status == "pass"`.
    2. `test_discover_qc_rnaseq_composition_not_applied_to_other_assays` —
       same file present, `assay="variant_calling"` → none of
       `exonic_fraction:` / `intronic_fraction:` / `unassigned_fraction:` /
       `rnaseq_composition_qc:` appear.
    3. `test_discover_qc_rnaseq_composition_unparseable_is_unverified` —
       garbage file under rnaseq → exactly one
       `rnaseq_composition_qc:WT_REP1`, `status == "unverified"`,
       `value is None`.
    4. `test_discover_qc_rnaseq_composition_no_file_skips_silently` — no
       `*.read_distribution.txt` anywhere → no composition check of any kind
       emitted.
    5. `test_discover_qc_rnaseq_composition_prefers_results_over_work_copy` —
       AC6: both a `results/.../WT_REP1.read_distribution.txt` (healthy
       values) and a `work/ab/cd/WT_REP1.read_distribution.txt` (very
       different values: assigned tags 500000 vs 129802, CDS_Exons tag count
       100000 vs 129779) present → exactly one `exonic_fraction:WT_REP1`
       result, and its value equals `129779 / 129802` (the `results/` copy's
       exonic fraction over assigned tags), not the `work/` copy's `0.2`.

  No existing test bodies were changed. However, the new block was
  inadvertently inserted in the middle of the pre-existing
  `test_discover_qc_mag_gate_not_applied_to_other_assays` (C7), which
  displaced its trailing `assert not any(r.check.startswith("mag_qc:") for r
  in results)` assertion down onto the end of
  `test_discover_qc_rnaseq_composition_prefers_results_over_work_copy` (AC6),
  where it was meaningless (that test has no mag artifacts). This has been
  fixed: the `mag_qc:` assertion is restored to
  `test_discover_qc_mag_gate_not_applied_to_other_assays`, and the orphaned
  copy is removed from the AC6 test. The pre-existing rnaseq alignment +
  dup/rRNA MultiQC-path tests
  (`test_discover_qc_emits_rnaseq_plausibility_for_rnaseq_assay`,
  `test_discover_qc_does_not_emit_rnaseq_plausibility_for_non_rnaseq_assay`,
  etc.) were left untouched and still pass.

## TDD evidence

**RED** — ran the new tests before implementing `runner.py` changes:

```
uv run pytest tests/verification/test_run_qc.py -k "rnaseq_composition" -q
```
→ 3 of 5 failed (`test_discover_qc_emits_rnaseq_composition_for_rnaseq_assay`,
`test_discover_qc_rnaseq_composition_unparseable_is_unverified`,
`test_discover_qc_rnaseq_composition_prefers_results_over_work_copy`); the
other 2 (non-rnaseq-assay and no-file skip) trivially passed since they assert
absence and the gate didn't exist yet — expected shape for an additive
feature's negative-space assertions.

**GREEN** — after adding the imports, `_locate_rnaseq_composition_qc`, and the
gate block (verbatim per the plan's Phase 3 GREEN step):

```
uv run pytest tests/verification/test_run_qc.py -k "rnaseq_composition" -q
```
→ `.....` (5 passed)

## Validation

```
uv run pytest tests/verification/test_run_qc.py -q
```
→ all tests in the file pass (no output truncation issue at file scope):
`................................................................` (all dots,
no failures).

```
uv run pytest -q
```
→ ran clean (all dots across the run, per-file summary line suppressed on the
full run in this environment, as flagged in the task brief).

```
uv run pytest -rN 2>&1 | grep -E "passed|failed"
```
→ `1477 passed, 1 skipped in 11.62s`

Baseline on this branch before this task was 1472 passed, 1 skipped. This task
added exactly 5 new tests and broke nothing: 1472 + 5 = 1477, skip count
unchanged. Confirmed no regressions to the existing rnaseq gate, and no
duplicate-emission across assays.

## How AC6 (published-tree preference) was confirmed

`test_discover_qc_rnaseq_composition_prefers_results_over_work_copy` writes
two `WT_REP1.read_distribution.txt` files with deliberately different content:
- `results/star_salmon/rseqc/read_distribution/WT_REP1.read_distribution.txt`
  — the healthy fixture (`Total Assigned Tags 129802`, `CDS_Exons` tag count
  `129779` → exonic fraction ≈ `0.9998`).
- `work/ab/cd/WT_REP1.read_distribution.txt` — a synthetic "unhealthy" copy
  (`Total Assigned Tags 500000`, `CDS_Exons` tag count `100000` → exonic
  fraction `0.2`).

The test asserts exactly one `exonic_fraction:WT_REP1` result exists (proving
dedup — no double-count from the two files) and that its value is
`pytest.approx(129779 / 129802, rel=1e-4)` — the `results/`-copy value, not
`0.2`. This directly exercises the `"results" in {q.lower() for q in
p.relative_to(run_dir).parts}` preference branch in
`_locate_rnaseq_composition_qc`, since `sorted(run_dir.rglob(...))` would
otherwise return `results/...` before `work/...` alphabetically anyway — so
the test's differing content across the two copies is what actually proves
the preference logic fired rather than sort-order coincidentally agreeing
with it.

## Concerns

None outstanding. Scope was kept to Phase 3 exactly as specified: no new
`FailureClass`/model/persisted-record field, no exit-code change,
`launch.json`/schema untouched, `_DEDICATED_METRIC_ASSAYS` untouched, the
MultiQC-driven rnaseq plausibility gate untouched and left as a separate
block from the new composition gate. Pre-existing unrelated worktree diffs
(`docs/planning/_card/issue.md`, `docs/planning/_card/understanding.md`,
`uv.lock`) were present before this task started and were deliberately left
unstaged/uncommitted — only `src/contig/runner.py` and
`tests/verification/test_run_qc.py` were staged and committed.

## Fix — displaced assertion

A subsequent task review found that the new rnaseq-composition test block
above had been inserted in the middle of the pre-existing
`test_discover_qc_mag_gate_not_applied_to_other_assays` (C7), which used to
end with two assertions (`assembly_n50:` and `mag_qc:`). The insertion left
that test ending at the `assembly_n50:` assertion only, and the orphaned
`assert not any(r.check.startswith("mag_qc:") for r in results)` line ended
up dangling at the end of the unrelated
`test_discover_qc_rnaseq_composition_prefers_results_over_work_copy` (AC6)
test, where it was meaningless (that test has no mag artifacts).

Fixed by restoring the `mag_qc:` assertion as the final assertion of
`test_discover_qc_mag_gate_not_applied_to_other_assays` and removing the
orphaned copy from the end of the AC6 test, which now correctly ends on its
real assertion (`exonic_fraction:WT_REP1` value from the `results/` copy).
No production code (`src/`) and no other test was touched.

Covering-test run:

```
uv run pytest tests/verification/test_run_qc.py -q
```
```
................................................................         [100%]
64 passed in 0.16s
```

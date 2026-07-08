# Task 1 report — `reference_not_bgzf` FailureClass + detector branch + corpus

**Phase:** Phase 1 of `plan_20260708.md` · **Aspect:** `recompress-reference` ·
**AC covered:** AC1 (spec.md) · **Branch:** `feat/self-heal-bgzip-reference/aliz`

## Files changed

- `src/contig/models.py` — added `"reference_not_bgzf"` to the `FailureClass` Literal
  (between `"missing_index"` and `"bad_param"`).
- `src/contig/detect.py` — new narrow detector branch in `diagnose_failure`, inserted
  after the `platform_unsupported` branch and before the terminal `tool_crash`
  fallthrough. Anchors case-insensitively on the faidx-specific primary token
  `"cannot index files compressed with gzip"` (via the existing `_matching_lines`
  helper), deliberately NOT on the bare `"please use bgzip"` (tabix/bcftools emit that
  phrase for VCFs — a different fix). Evidence includes the matched line(s) plus any
  `"could not build fai index ..."` line. Confidence 0.85.
- `src/contig/data/detector_corpus.jsonl` — +1 golden case `"reference-not-bgzf"`
  (`source: "synthetic"`, event `SAMTOOLS_FAIDX`/`FAILED`/`exit:1`, real faidx
  `log_text`, `expected_class: "reference_not_bgzf"`).
- `src/contig/data/detector_corpus_holdout.jsonl` — +1 disjoint holdout twin. Initially
  named `"reference-not-bgzf-holdout"` per the task brief, but the repo enforces a
  stricter convention (`tests/test_eval_holdout.py::test_holdout_case_ids_prefixed`
  asserts every holdout `case_id` starts with `"holdout-"`), so it was renamed to
  `"holdout-reference-not-bgzf"` to satisfy that existing guard. Same real faidx
  log_text, trivially varied path (`/data/genome.fa.gz.fai` vs `/work/ref.fa.gz.fai`)
  to keep the two `log_text` values distinct, `source: "holdout:synthetic"`.
- `src/contig/data/holdout_baseline.json` — refrozen twice via
  `uv run contig eval-guard --update-baseline`: once after adding the holdout case, and
  again after the case_id rename changed the held-out corpus sha. Final baseline:
  84.6% accuracy over 13 held-out cases (detector `rules`).
- `tests/test_detect.py` — +2 tests (see below), inserted right after the bwa-mem2
  missing-index negative test and before the "broader failure classes" section, mirroring
  the file's existing structural order (each detector branch's positive test then a
  negative/guard test for the sibling classes).

No changes to `repair.py`, `self_heal.py`, or any other assay — out of Task 1 scope,
deferred to Phases 2+.

## Tests added

```python
def test_gzip_reference_is_reference_not_bgzf() -> None:
    events = [TaskEvent(process="SAMTOOLS_FAIDX", status="FAILED", exit=1)]
    log = (
        "[E::fai_build_core] File truncated at line 1\n"
        "[E::fai_build3_core] Cannot index files compressed with gzip, please use bgzip\n"
        "[faidx] Could not build fai index /work/ref.fa.gz.fai"
    )
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "reference_not_bgzf"
    assert any("cannot index files compressed with gzip" in e.lower() for e in d.evidence)


def test_vcf_please_use_bgzip_without_faidx_token_is_not_reference_not_bgzf() -> None:
    events = [TaskEvent(process="TABIX", status="FAILED", exit=1)]
    log = "[tabix] was bgzip used to compress this file? please use bgzip"
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class != "reference_not_bgzf"
```

## RED (failing for the right reason)

Ran before the `models.py`/`detect.py` changes:

```
$ uv run pytest tests/test_detect.py -k "reference_not_bgzf" -v
...
tests/test_detect.py F.                                                  [100%]

=================================== FAILURES ===================================
__________________ test_gzip_reference_is_reference_not_bgzf ___________________
    d = diagnose_failure(events, log_text=log)
>   assert d.failure_class == "reference_not_bgzf"
E   AssertionError: assert 'tool_crash' == 'reference_not_bgzf'
E
E     - reference_not_bgzf
E     + tool_crash

tests/test_detect.py:310: AssertionError
=========================== short test summary info ============================
FAILED tests/test_detect.py::test_gzip_reference_is_reference_not_bgzf - Asse...
================== 1 failed, 1 passed, 45 deselected in 0.12s ==================
```

The positive test failed by falling through to the pre-existing `tool_crash`
fallthrough (right reason — the class/branch did not exist yet); the guard test
(negative case) passed trivially since nothing classifies the VCF-style line as
`reference_not_bgzf` either before or after.

## GREEN

After adding the `FailureClass` member and the detector branch:

```
$ uv run pytest tests/test_detect.py -v
============================= test session starts ==============================
collected 47 items
tests/test_detect.py ...............................................     [100%]
============================== 47 passed in 0.07s ==============================
```

## Validation

### `uv run contig eval-detector`

```
Detector eval: 24/24 correct (accuracy 100.0%)
  bad_param: precision 1.00  recall 1.00  (support 2)
  conda_solve_failed: precision 1.00  recall 1.00  (support 1)
  container_pull_failed: precision 1.00  recall 1.00  (support 1)
  container_unavailable: precision 1.00  recall 1.00  (support 1)
  disk_full: precision 1.00  recall 1.00  (support 1)
  download_failed: precision 1.00  recall 1.00  (support 1)
  missing_index: precision 1.00  recall 1.00  (support 9)
  missing_reference: precision 1.00  recall 1.00  (support 1)
  oom: precision 1.00  recall 1.00  (support 1)
  permission_denied: precision 1.00  recall 1.00  (support 1)
  platform_unsupported: precision 1.00  recall 1.00  (support 1)
  reference_not_bgzf: precision 1.00  recall 1.00  (support 1)
  time_limit: precision 1.00  recall 1.00  (support 1)
  tool_crash: precision 1.00  recall 1.00  (support 1)
  unknown: precision 1.00  recall 1.00  (support 1)
```

24/24 (was 23/23), guard stays at 100%.

### `uv run contig eval-guard` (before refreeze)

```
Held-out set changed (sha 9198198959f9 != baseline ba791e75e7b8); the delta crosses different sets — refreeze with --update-baseline.
Guard: accuracy 84.6% vs baseline 83.3% (delta +1.3pp) over 13 held-out cases [rules]
  MISS holdout-qc-anomaly-1: expected qc_anomaly, predicted tool_crash
  MISS holdout-no-progress-1: expected no_progress, predicted tool_crash
Held-out accuracy improved (84.6% > baseline 83.3%); consider --update-baseline to lock it in.
```

The new holdout case classified correctly, raising held-out accuracy — a nudge, non-failing.

**Deliberate refreeze (first pass, before the case_id rename):**

```
$ uv run contig eval-guard --update-baseline
Baseline updated: accuracy 84.6% over 13 held-out cases (detector=rules, sha 9198198959f9...)
```

Running the full suite (`uv run pytest`) at this point surfaced a pre-existing guard I
had not anticipated: `tests/test_eval_holdout.py::test_holdout_case_ids_prefixed` asserts
every holdout `case_id` starts with `"holdout-"`. My initial holdout `case_id`
(`"reference-not-bgzf-holdout"`) violated that convention (it ends with, not starts
with, `holdout`). Renamed to `"holdout-reference-not-bgzf"` (still disjoint from the
golden case's `"reference-not-bgzf"`), which changed the held-out corpus sha again, so
`tests/test_eval_holdout.py::test_guard_default_committed_baseline_passes_clean` failed
next (committed baseline sha no longer matched the shipped held-out sha). Refroze a
second time:

```
$ uv run contig eval-guard --update-baseline
Baseline updated: accuracy 84.6% over 13 held-out cases (detector=rules, sha d6f6fb43b09b...)

$ uv run contig eval-guard
Guard: accuracy 84.6% vs baseline 84.6% (delta +0.0pp) over 13 held-out cases [rules]
  MISS holdout-qc-anomaly-1: expected qc_anomaly, predicted tool_crash
  MISS holdout-no-progress-1: expected no_progress, predicted tool_crash
Guard PASS: accuracy 84.6% ≥ baseline 84.6%.
```

Final committed `holdout_baseline.json` corresponds to this second (final) refreeze —
sha `d6f6fb43b09b...`, 13 held-out cases, 84.6% accuracy.

### Final whole-suite run

```
$ uv run pytest
........................................................................ [ 23%]
...
1212 passed, 1 skipped in 11.58s
```

Baseline was `1210 passed, 1 skipped`; +2 new tests in `test_detect.py` → `1212 passed,
1 skipped`, all green.

## Commit

```
ab1e1b46cdbc6ebb66ef184016d70635112f70a9
feat(detect): classify plain-gzip (non-BGZF) reference as reference_not_bgzf [C2]
```

6 files changed (`src/contig/models.py`, `src/contig/detect.py`,
`src/contig/data/detector_corpus.jsonl`, `src/contig/data/detector_corpus_holdout.jsonl`,
`src/contig/data/holdout_baseline.json`, `tests/test_detect.py`), 78 insertions(+),
23 deletions(-) (the deletions are the baseline-refreeze rewrite, not code removal).

Pre-existing unrelated worktree modifications (`docs/planning/_card/issue.md`,
`docs/planning/_card/understanding.md`, `uv.lock`) were present before this task started
and were deliberately left unstaged/uncommitted — out of Task 1 scope.

## Concerns / deviations from the brief

- The task brief's example holdout `case_id` (`"reference-not-bgzf-holdout"`) does not
  satisfy the repo's own `test_holdout_case_ids_prefixed` guard (must **start** with
  `"holdout-"`, not merely contain/end with it). Used `"holdout-reference-not-bgzf"`
  instead — still disjoint from the golden case_id, same real log_text, same
  `expected_class`. Flagging in case Phase 7's heal-scenario or later docs reference the
  originally-suggested case_id.
- `eval-guard --update-baseline` was run twice (see above) because the case_id rename,
  done to satisfy the pre-existing guard, changed the held-out corpus sha after the first
  refreeze. The committed baseline reflects the final, correct state.

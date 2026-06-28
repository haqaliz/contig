# Task 2 Report — evaluate_rnaseq_plausibility (Phase 2)

Date: 2026-06-28  
Branch: `feat/rnaseq-plausibility/aliz`  
Commit: `89f43b7`

---

## Status

DONE

---

## Changes

### New files

| File | Purpose |
|------|---------|
| `src/contig/verification/rnaseq_plausibility.py` | `evaluate_rnaseq_plausibility()` — pure evaluator |
| `tests/verification/test_rnaseq_plausibility.py` | 9 TDD tests (written before production code) |

### No files modified

Phase 1's `RNASEQ_PLAUSIBILITY_PACK` in `rule_pack.py` was already in place. No runner wiring — that is Phase 3.

---

## Implementation summary

`evaluate_rnaseq_plausibility(metrics: dict[str, dict[str, float]]) -> list[QCResult]` in `src/contig/verification/rnaseq_plausibility.py`:

- Takes the already-parsed `{sample: {metric: value}}` dict (same shape as `qc_ingest.parse_multiqc_general_stats_file`). Pure function, no file I/O.
- Mirrors `evaluate_variant_plausibility` in `variant_metrics.py`.
- Computable metrics go through the shared `evaluate()` (band logic and `"<check>:<sample>"` naming stay single-sourced in `rule_pack.py`).
- Each absent plausibility metric gets an explicit `QCResult(status="unverified", value=None, kind="metric")` — never silently omitted. The shared `evaluate()` silently skips absent metrics, so this honest branch lives in the wrapper.
- WARN-capped pack (`RNASEQ_PLAUSIBILITY_PACK` has no `fail_*` keys) means no result can ever be `"fail"`.
- Local `_rule_by_check()` helper mirrors the germline module's — not abstracted across modules per the plan's REFACTOR note.

---

## Tests

File: `tests/verification/test_rnaseq_plausibility.py`

| Test name | What it asserts |
|-----------|----------------|
| `test_duplication_rate_inband_is_pass` | `percent_duplication=30.0` → `duplication_rate:S1` pass, kind metric, value 30.0 |
| `test_duplication_rate_outofband_is_warn_never_fail` | `percent_duplication=95.0` → warn, status is never fail |
| `test_duplication_rate_missing_is_unverified` | absent `percent_duplication` → unverified, value None, kind metric |
| `test_rrna_contamination_inband_is_pass` | `percent_rRNA=2.0` → `rrna_contamination:S1` pass, kind metric, value 2.0 |
| `test_rrna_contamination_outofband_is_warn_never_fail` | `percent_rRNA=25.0` → warn, status is never fail |
| `test_rrna_contamination_missing_is_unverified` | absent `percent_rRNA` → unverified, value None, kind metric |
| `test_both_metrics_absent_gives_two_unverified_no_pass` | `{"S1": {}}` → exactly 2 results, all unverified, zero pass |
| `test_multisample_inband_and_missing` | S1 has `percent_duplication` (pass), S2 has neither (unverified) — asserts iteration over all samples |
| `test_empty_metrics_returns_empty_list` | `{}` → empty list, no crash |

---

## Test command and output

```
uv run pytest tests/verification/test_rnaseq_plausibility.py -v
```

```
collected 9 items

tests/verification/test_rnaseq_plausibility.py .........   [100%]

9 passed in 0.05s
```

Full suite:

```
uv run pytest -q
```

```
825 passed, 1 skipped in 10.12s
```

Baseline was 816 passed + 1 skipped. The 9 new tests account for the difference; no regressions.

---

## Open calibration note (R1)

Metric slugs (`percent_duplication`, `percent_rRNA`) and thresholds (`warn_above=80` / `warn_above=10`) are best-effort nf-core/rnaseq MultiQC general-stats keys and illustrative engineering defaults, uncalibrated on real run data. The UNVERIFIED-when-absent guarantee makes a wrong or missing slug safe: the check emits `"unverified"` rather than a spurious pass. Calibration deferred to Phase 3 / R1.

---

## Commit

SHA: `89f43b7`  
Message: `feat(verify): evaluate_rnaseq_plausibility with honest UNVERIFIED-when-absent`

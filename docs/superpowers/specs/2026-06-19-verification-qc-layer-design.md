# Verification / QC Layer — Design

Date: 2026-06-19
Status: approved (build)

## Goal

Close the trust gap exposed by the first real run: a *failed* `nf-core/rnaseq`
run produced a `RunRecord` whose `verdict` read `pass` (because `qc_results` was
empty). Verification is the moat (VISION, ARCHITECTURE §6) — a run that *ran* is
not a run that is *correct*. This layer turns captured runs into *verified* runs.

Scope this iteration: **MultiQC ingestion + an RNA-seq rule pack + an honest,
conservative verdict.** TDD'd entirely against fixtures (no live Docker).

## Components

### 1. Honest verdict (contract change in `src/contig/models.py`)
`RunRecord.verdict` becomes conservative, using data the record already holds
(`events` + `qc_results`). New `Verdict` type adds `"unverified"`:

```
run has a failed task?  -> "fail"        # didn't complete -> output untrustworthy
any QC check = fail?    -> "fail"
any QC check = warn?    -> "warn"
QC present, all pass?   -> "pass"
no QC checks at all?    -> "unverified"   # never claim verified beyond what we checked
```

`overall_verdict(qc_results) -> QCStatus` is unchanged (pure QC reduction). The
run-level logic lives in the `RunRecord.verdict` property so `models.py` gains no
new dependencies and the record stays self-contained. Run-success is derived via
`RunSummary.from_events(self.events)`.

### 2. `src/contig/verification/qc_ingest.py` (agent)
`parse_multiqc_general_stats(json_text|path) -> dict[str, dict[str, float]]`
mapping `sample -> {metric: value}` from MultiQC's `report_general_stats_data`.
Pure parse; TDD against a fixture `multiqc_data.json` snippet.

### 3. `src/contig/verification/rule_pack.py` (agent)
The RNA-seq rule pack is **data, not code** (versioned, auditable — §6.3):
a list of checks `{check, metric, warn_below, fail_below, message}`.

`evaluate(metrics, rule_pack) -> list[QCResult]` applies the pack across samples,
producing one typed `QCResult{check,status,value,expected_range,message}` per
sample/metric. Initial checks (illustrative, tunable — flagged as such; founder
has no wet-lab credentials, so thresholds are conservative defaults, not claims):
- `uniquely_mapped_percent`: fail < 40, warn < 60
- `percent_assigned` (or `reads_mapped`): fail/warn bands
- library-size skew across samples (max/min ratio)

### 4. Integration (orchestrator)
`evaluate_run_qc(multiqc_json, rule_pack) -> list[QCResult]` ties ingest -> rules.
Attaching the result to a `RunRecord` drives the verdict. Proven on the real
`runs/first-real` record: verdict flips `pass` -> `fail` (failed tasks present).

## Out of scope (YAGNI)
Auto-running QC inside `run_pipeline` (runs die before MultiQC; wire later),
structural/format checks, tool-native beyond MultiQC general-stats, cross-sample
sex-check/relatedness.

## Build order
1. Verdict contract change in `models.py` (strict TDD, watched failing) — keystone.
2. Fan out two parallel agents: `qc_ingest.py`, `rule_pack.py` (independent; both
   depend only on the `QCResult` contract; TDD with fixtures).
3. Integrate `evaluate_run_qc`; prove the honest verdict on the real record.

## Testing
Strict TDD throughout; real code over mocks; fixtures for MultiQC JSON and metrics
dicts. Every behavior watched failing before implementation.

# PRD: cross-run benchmark, failure clustering, corpus coverage, guided escalation

Status: approved, in build. Target branch: master (commit and push per feature as it goes green).

The last four buildable FEATURES items, in one pass. Two engine streams + one
dashboard stream own disjoint files; the orchestrator wires the choose CLI and
integrates.

## Decisions (locked with the user)

1. Cross-run benchmark: compare a run against a designated reference for its
   (pipeline, assay) by QC metric values within a tolerance plus structural shape
   (robust to run-to-run non-determinism), not bit-for-bit checksums.
2. Guided escalation: when a self-heal decision is ambiguous (low-confidence
   diagnosis or several viable fixes), the run pauses and presents the ranked fixes
   as a choice; the human picks one.
3. Clustering: group corpus/pending cases by failure class plus a normalized log
   signature.
4. Coverage: per-class support, a thin-coverage flag (fewer than 3 cases), and
   confirmed-cases-over-time.

## File ownership (no two streams touch the same file)

- Engine-Insight (benchmark + clustering + coverage): NEW benchmark.py, corpus.py,
  eval_history.py, cli.py, src/contig/data/ reference registry, + their tests. Does
  NOT touch models.py, self_heal.py, repair.py, lifecycle.py.
- Engine-Heal (guided escalation): self_heal.py, repair.py, models.py, lifecycle.py,
  + their tests. Does NOT touch cli.py, corpus.py, benchmark.py, eval_history.py.
- Dashboard: dashboard/** + e2e fixtures.
- Orchestrator: wire `contig approve <id> --choose N` in cli.py against
  lifecycle.write_approval, integrate, commit.

The choose CLI flag is the only cross-file wiring; the orchestrator does it.

---

## Pinned contracts

### A. Cross-run benchmark (Engine-Insight + Dashboard)

A reference registry at src/contig/data/reference_runs.jsonl (committed), one entry
per (pipeline, assay): `{pipeline, assay, reference_run_id, metrics: {check: value},
recorded_at}`, where metrics are the reference run's numeric QC values.
`contig benchmark set <run-id> [--runs-dir]` records the run's QC metrics as the
reference for its (pipeline, assay) (assay via registry.assay_for_pipeline).
`contig benchmark <run-id> [--tolerance 0.1] [--runs-dir] [--json]` loads the run,
finds the reference for its (pipeline, assay), and compares each shared numeric QC
check within the relative tolerance, plus a structural-shape comparison (the same
QC check names present). JSON: `{reference_run_id, tolerance, matched: int,
drifted: int, checks: [{name, run_value, reference_value, within_tolerance,
delta}], status: "match" | "drift" | "no_reference"}`. No reference => a clear
"no reference set for this pipeline/assay" (not an error). Dashboard: a benchmark
section on the run page (or a small route) showing run vs reference per metric.

### B. Failure-pattern clustering (Engine-Insight + Dashboard)

corpus.cluster_failures(cases) -> a list of clusters, each `{failure_class,
signature, count, case_ids}`. `signature` is a normalized fingerprint of a case's
log_text: lowercase, strip absolute paths, numbers, hashes, and timestamps, then
keep the most salient matched lines and hash them, so the same systemic failure
mode groups even across runs. `contig clusters [--corpus PATH] [--json]` prints
clusters worst-first (largest count). Dashboard: a clusters view (on /eval or
/pending) listing the recurring modes.

### C. Corpus coverage (Engine-Insight + Dashboard)

corpus.coverage_report(cases) -> `{total, per_class: {class: count}, thin:
[classes with fewer than 3 cases], by_source: {source_kind: count}}`, plus a
confirmed-over-time series from the eval history where available.
`contig coverage [--corpus PATH] [--json]`. Dashboard: a coverage panel on /eval
(per-class bars, thin-coverage flags).

### D. Guided escalation (Engine-Heal provides; orchestrator wires CLI; Dashboard)

In the self-heal loop, when the decision is AMBIGUOUS (the diagnosis confidence is
below a threshold, or there are multiple viable non-safe candidate patches and no
single safe one), instead of the binary gate, write pending_approval.json with an
`options` array: `options: [{index, kind, risk, rationale, expected_signal}]`
(ranked best-first), alongside the existing single-patch fields for back-compat,
plus a `decision_kind: "choice"`. Poll approval.json which may carry
`{decision: "approve" | "reject", choice: <index>}`. On approve with a choice,
apply options[choice] (param/env/reference/resource as today) and continue; on
reject or timeout, stop. The existing single-patch gate (one needs_confirmation
patch) is unchanged (decision_kind "single"). lifecycle.write_approval(runs_dir,
run_id, decision, choice=None) records the choice. The orchestrator adds
`contig approve <id> --choose N` (approve and pick option N). Dashboard: when
pending_approval has options, the gate renders the ranked choices (pick one, then
approve); otherwise the existing approve/reject.

---

## Verification

- Engine: strict TDD (RED before GREEN). Full `uv run pytest` green (currently 674).
  No network; benchmark/clustering/coverage read run bundles and the corpus only;
  escalation tests inject the poll/clock so they never sleep.
- Dashboard: tsc + lint clean; Playwright green with CONTIG_AUTH_DISABLED=1; new
  fixtures under e2e/fixtures, provisioned by the global setup, never the real runs
  dir.
- Cross-layer: confirm the benchmark JSON, the pending_approval options shape, and
  the clusters/coverage JSON match what the dashboard reads.

## Style / security constraints (carried)

- No em dash, en dash, or hyphen-as-pause anywhere (code, comments, docs, commits).
- Any user value reaching the CLI is validated (charset, no leading dash) and passed
  as `--opt=value` with a `--` terminator before positionals.
- The choice index is validated against the options length; an out-of-range choice
  is rejected, not applied.

# PRD: detector-improvement proof, self-heal coverage, estimate, provenance, multi-tenant

Status: approved, in build. Target branch: master (commit and push per feature as it goes green).

Five items in one pass. Three streams own disjoint files; contracts pinned. The
shared EvalSnapshot.detector field is already added to models.py so the two engine
streams never edit the same file.

## Decisions (locked with the user)

1. LLM detector proof: build the comparison harness (eval-history tagged by
   detector, a side-by-side rules-vs-llm view); the user runs the real eval with
   their own key. No secret handled here.
2. Self-heal coverage: BOTH deeper (param/env/reference patches truly applied and
   verified) and broader (new failure classes for common nf-core failures), each
   backed by a corpus case.
3. Pre-run estimate: data-driven from past runs' recorded resource_usage for the
   same pipeline, with a sample-count heuristic fallback when there is no history.
4. Provenance: an RO-Crate export plus a deterministic methods-section generator
   (templated over the bundle, no LLM).
5. Multi-tenant: per-user run isolation (owner-tagged runs, filtered per user,
   admins see all) plus a documented deploy guide (Dockerfile + env). No live host.

## File ownership (no two streams touch the same file)

- Engine-Heal (self-heal coverage): detect.py, repair.py, self_heal.py, models.py
  (FailureClass additions), corpus.py, src/contig/data/detector_corpus.jsonl,
  + their tests. Does NOT touch cli.py, eval_history.py.
- Engine-Insight (eval harness + estimate + provenance): eval_history.py, NEW
  estimate.py, NEW provenance.py, NEW methods.py, cli.py, + their tests. Does NOT
  touch models.py (uses the pre-added EvalSnapshot.detector; new models live in its
  own modules), detect.py, repair.py, self_heal.py, corpus.py.
- Dashboard: dashboard/** + e2e fixtures.
- Orchestrator: full verification, commits.

---

## Pinned contracts

### A. Detector-comparison harness (Engine-Insight + Dashboard)

EvalSnapshot.detector (already on the model, default "rules"). eval_history
snapshot_from_report records the detector name; `contig eval-detector --detector
<name> --snapshot` tags the snapshot with that name. So a user with a key runs
`contig eval-detector --detector llm --snapshot` to record an llm-tagged point.
Dashboard /eval: a side-by-side of the latest snapshot per detector (accuracy and
per-class), so rules vs llm is a direct comparison; the existing trend stays.

### B. Pre-run estimate (Engine-Insight + Dashboard)

NEW estimate.py: `estimate_run(pipeline, n_samples, runs_dir, *, rate_cpu_hour=0.0,
rate_mem_gb_hour=0.0, currency="USD") -> EstimateReport` (EstimateReport defined in
estimate.py, NOT models.py). Data-driven: scan runs_dir for prior FINISHED runs of
the same pipeline, derive per-sample totals from their resource_usage and sample
counts, scale to n_samples; fall back to a transparent heuristic when there is no
history. Reuse cost.py for the cost figure. JSON shape:
`{basis: "history" | "heuristic", pipeline, n_samples, n_prior_runs,
est_runtime_sec, est_peak_mem_mb, est_total_cpu_hours, est_cost, currency,
rate_cpu_hour, rate_mem_gb_hour, note}`.
`contig estimate --pipeline X --input <sheet> [--runs-dir] [--rate-cpu-hour
--rate-mem-gb-hour --currency] [--json]` (n_samples from the sheet). Dashboard:
show the estimate (runtime + cost) on the launch form before launch, via a small
read-only API route shelling `contig estimate --json`.

### C. Provenance export + methods (Engine-Insight + Dashboard)

NEW provenance.py: `to_rocrate(record) -> dict` building an RO-Crate
ro-crate-metadata.json (JSON-LD) subset: the run as a Dataset, the pipeline as a
SoftwareApplication (name + version), inputs and outputs as File entities with
their checksums, and the verdict and QC as properties. NEW methods.py:
`render_methods(record) -> str`, a deterministic citation-ready methods paragraph
templated from the bundle (pipeline + revision, assay, key params, container
digests, the verdict and QC summary). No LLM, no network.
`contig export <id> [--rocrate] [--output PATH]` (writes/prints the RO-Crate JSON),
`contig methods <id> [--output PATH]`. Dashboard: download buttons on the run page
(RO-Crate JSON, methods text) via read-only API routes shelling the CLI.

### D. Self-heal coverage (Engine-Heal)

Deeper: `apply_patch` (self_heal.py) applies `param`, `env`, AND `reference`
patches so an applied patch actually changes the re-run (param merges into params,
env into the target/env, reference swaps the reference param), and the loop checks
each patch's `expected_signal`. Confirm the applied change reaches the next run's
config/command (test via the injected executor capturing the command/params).
Broader: add new FailureClass values to models.py for common nf-core failures
(e.g. `disk_full` for "No space left on device", `download_failed` for staging or
network download errors, plus one or two more you can detect cleanly and that are
distinct from the existing taxonomy), with detect.py needles, repair.py proposers
(a retry is `safe`; a destructive cleanup is `needs_confirmation`), and a labeled
corpus case per new class in detector_corpus.jsonl. Keep `contig eval-detector`
accuracy at 1.0 (the regression guard).

### E. Multi-tenant isolation + deploy (Dashboard)

At dispatch, tag each run with its owner (the Auth0 user `sub` and email) via a
`runs/<id>/owner.json` `{owner, email}` written by the dispatch routes. `listRuns`
returns only the current user's runs; the admin role sees all; a run with no
owner.json (e.g. a CLI-launched run) is visible to admins only. `getRun` returns
404/forbidden for a run the user does not own (unless admin). Under the auth bypass
(CONTIG_AUTH_DISABLED or no Auth0 env) the owner is a synthetic local admin and
everything is visible, so local use is unchanged. Add a Dockerfile (multi-stage
Next build) and a deploy section in dashboard/README (env, the runs volume, a
reverse proxy note). The engine is unchanged; ownership lives entirely in the
dashboard.

---

## Verification

- Engine: strict TDD (RED before GREEN). Full `uv run pytest` green (currently 527).
  No network in any test (LLM, downloads); inject fakes.
- Dashboard: tsc + lint clean; Playwright green with CONTIG_AUTH_DISABLED=1; new
  fixtures under e2e/fixtures, provisioned by the global setup, never the real runs
  dir. The isolation specs run under the bypass (admin sees all) plus a unit-level
  ownership-filter test.
- Cross-layer: confirm the estimate JSON, eval-snapshot detector tag, and export
  outputs match what the dashboard reads.

## Style / security constraints (carried)

- No em dash, en dash, or hyphen-as-pause anywhere (code, comments, docs, commits).
- Any user value reaching the CLI is validated (charset, no leading dash) and
  passed as `--opt=value` with a `--` terminator before positionals.
- Ownership denies cross-user access by default; secrets only from env, never
  logged or committed; the methods generator and RO-Crate export are offline.

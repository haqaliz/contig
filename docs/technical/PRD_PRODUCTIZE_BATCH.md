# PRD: live validation, Auth0, LLM detector, resource and cost, three assays

Status: approved, in build. Target branch: master (commit and push per feature as it goes green).

Five items in one pass. Three build streams own disjoint files; the orchestrator
runs the live validation after the code lands. Cross-module shapes are pinned.

## Decisions (locked with the user)

1. Live validation on a single-node Linux host (a plain Linux box, no AWS): a FULL from-scratch
   nf-core run on the local backend on real data, exercising self-heal, output
   verify, and notifications end-to-end, then tear everything down. aws_batch stays
   code-tested until the user has AWS. This is an orchestrator task after the build.
2. Auth0: authentication AND role-based authorization (free tier; Contig stays open
   source). Login gate on all routes; roles gate the action routes. Env-configured,
   a dev bypass for tests/local, documented.
3. LLM detector: provider-agnostic (Claude or OpenAI selected by env), behind the
   existing Detector interface, OPTIONAL (unregistered without a key), mock-tested.
4. Resource actuals + cost: per-task duration, peak memory, and cpu from the trace
   into the record; a configurable rate cost model; a contig cost command; shown on
   the run page.
5. Three new assays at once: methyl-seq (nf-core/methylseq), 16S amplicon
   (nf-core/ampliseq), shotgun metagenomics (nf-core/mag), each with a QC rule pack,
   plus an "add an assay" onboarding doc.

## File ownership (no two streams touch the same file)

- Engine-A (assays + LLM detector): detect.py, registry.py, datashape.py,
  src/contig/verification/* (rule packs), corpus.py, NEW docs/technical/ADD_AN_ASSAY.md,
  + their tests. Does NOT touch cli.py, models.py, self_heal.py, runner.py, bundle.py.
- Engine-B (resource + cost): models.py, cli.py, self_heal.py, runner.py, bundle.py,
  events.py, NEW src/contig/cost.py (or resources.py), + their tests. Does NOT touch
  detect.py, registry.py, verification/*, datashape.py, corpus.py.
- Dashboard (Auth0 + cost display + llm selector): dashboard/** + e2e fixtures.
- Orchestrator: full verification, commits, and the single-node Linux host live validation.

No cross-file CLI wiring is needed this round: the existing `eval-detector
--detector` flag already resolves any name in the detector registry (so "llm" works
once Engine-A registers it), and the cost command lives entirely in Engine-B.

---

## Pinned contracts

### A. LLM detector (Engine-A; Dashboard reads the name)

In detect.py register an "llm" detector in DETECTORS. It selects a provider from
`CONTIG_LLM_PROVIDER` (claude | openai) and reads the matching key
(`ANTHROPIC_API_KEY` / `OPENAI_API_KEY`). It is OPTIONAL: if no provider/key is
configured, "llm" is NOT registered (or get_detector("llm") raises a clear error
naming the missing env), and the test suite stays green WITHOUT any network. The
detector maps the failure (events + log) to a Diagnosis via a single prompt;
tests inject a fake client (monkeypatch), never the real API. corpus.evaluate_detector
works with it unchanged. Dashboard adds "llm" to the detector selector; selecting it
without a key shows the existing graceful not-available branch.

### B. Resource actuals + cost (Engine-B; Dashboard reads)

models.py: a TaskResource model `{process: str, name: str | None, realtime_sec:
float, peak_rss_mb: float, pct_cpu: float}` and `RunRecord.resource_usage:
list[TaskResource] = []`. Parsed from trace.txt (columns realtime, peak_rss, %cpu,
already present; resolve by header name) and populated at _finalize. Durations like
"2m 3s" and sizes like "1.2 GB" are parsed to seconds and MB.

`contig cost <id> [--runs-dir] [--rate-cpu-hour X] [--rate-mem-gb-hour Y]
[--currency USD] [--json]`: applies the rates to the recorded resource usage and
reports total and per-task cost. Rates default to 0 (local is free). JSON shape:
`{currency, rate_cpu_hour, rate_mem_gb_hour, total, by_task: [{name, realtime_sec,
peak_rss_mb, cost}]}`. A record with no resource_usage reports a zero/empty cost.

Dashboard: a resources-and-cost card on the run detail page showing per-task
duration and peak memory and a total cost at the default (or entered) rates, read
from run_record.json resource_usage and/or `contig cost --json`.

### C. Auth0 (Dashboard; self-contained)

Use the Auth0 Next.js SDK. Env: `AUTH0_SECRET`, `AUTH0_DOMAIN` (or
`AUTH0_ISSUER_BASE_URL`), `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET`, `APP_BASE_URL`.
Middleware protects every route (redirect to login when unauthenticated). Roles come
from a namespaced claim (e.g. `https://contig/roles`); a non-admin/viewer is read
only and the ACTION routes (dispatch, launch, cancel, resume, approve, corpus
promote, verify trigger) require the writer/admin role and return 403 otherwise. A
dev/test bypass: when `CONTIG_AUTH_DISABLED=1` (or no Auth0 env is set) the
middleware is a no-op and everyone is an admin, so local dev and the Playwright
suite work without a real tenant. Document setup in the dashboard README.

### D. Three assays (Engine-A)

registry.py entries (real released nf-core tags): methylseq, ampliseq, mag, with
match_assay keywords (methylation/bisulfite/wgbs; 16s/amplicon/microbiome/dada2;
metagenome/metagenomics/shotgun/mag). Mind keyword ordering so a substring does not
misroute. datashape.py: set replicate expectations appropriately (these are not
bulk-replicate assays). src/contig/verification: METHYLSEQ_RULE_PACK (bisulfite
conversion rate, mapping efficiency, duplication), AMPLISEQ_RULE_PACK (read
retention through DADA2, feature/ASV count, sample read depth), MAG_RULE_PACK
(assembly size or N50, bin completeness, contamination), each wired into
rule_pack_for and using the existing data-driven evaluate(). Metric keys are
plausible documented names; note in-code where an exact MultiQC slug is unverified.
docs/technical/ADD_AN_ASSAY.md: the onboarding recipe (registry entry + keywords +
datashape + rule pack + rule_pack_for; the single mapping points; no engine rewrite).

---

## Verification

- Engine: strict TDD (RED before GREEN). Full `uv run pytest` green (currently 441).
  No test may hit the network (LLM) or real AWS; inject fakes, env-gate optionals.
- Dashboard: tsc + lint clean; Playwright green with auth disabled via
  CONTIG_AUTH_DISABLED (document it); new fixtures under e2e/fixtures, provisioned by
  the global setup, never the real runs dir.
- Live validation (orchestrator): a real from-scratch nf-core run on a single-node Linux host, the
  new verify and notifications exercised, a PASS bundle saved locally as proof, the
  box restored to its prior state (portable JRE, uv venv, swap, run dirs removed).

## Style / security constraints (carried)

- No em dash, en dash, or hyphen-as-pause anywhere (code, comments, docs, commits).
- Any user value reaching the CLI is validated (charset, no leading dash) and passed
  as `--opt=value` with a `--` terminator before positionals.
- Secrets (LLM keys, Auth0 secrets) come only from env, never logged or committed.
  Auth action routes deny by default without the writer role (except the dev bypass).

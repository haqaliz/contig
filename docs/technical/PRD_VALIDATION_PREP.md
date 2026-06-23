# PRD: partner-ready demo, deployment scaffolding, team workspaces

Status: approved, in build. Target branch: master.

The remaining buildable items that turn a finished tool into a validated one. Two
streams own disjoint areas; the orchestrator integrates and generates the demo
artifact.

## Decisions

1. Team workspaces are the one code feature: shared visibility on top of the
   existing per-user ownership, driven by an Auth0 namespaced claim, with the
   local/dev bypass unchanged.
2. The demo package and the deployment scaffolding are docs, config, and a
   generated sample artifact, not new engine features.

## Ownership

- workspaces-agent: dashboard/** only (lib/auth0.ts, lib/ownership.ts, lib/runs.ts,
  the run list/detail/compare pages, a header workspace indicator, e2e). Plus a
  short workspaces section in dashboard/README.
- devx-agent: NEW demo/** (the partner demo package) and NEW deploy/** plus
  dashboard/docker-compose.yml and a deploy section addition to dashboard/README.
  May run the engine (uv run contig) read-only to generate the sample artifact.
  Does NOT touch src/contig/** or dashboard/lib or dashboard/app code.
- Orchestrator: integrate, verify the demo artifact (sign + render + verify),
  commit, push.

To avoid a dashboard/README collision, workspaces-agent edits the Authentication
section only; devx-agent appends a Deployment section. If both must touch it, the
orchestrator merges.

---

## A. Team / shared workspaces (workspaces-agent)

A workspace is a shared run pool a lab sees together, layered on the existing
ownership model (owner-tagged runs, Auth0 roles, the CONTIG_AUTH_DISABLED bypass).

- lib/auth0 ViewerIdentity gains `workspaces: string[]`, read from a namespaced
  claim `https://contig/workspaces` (overridable via AUTH0_WORKSPACES_CLAIM). The
  bypass viewer has workspaces [] but isAdmin true (sees all, unchanged).
- owner.json gains an optional `workspace` field, written at dispatch from the
  viewer's first workspace when present (none otherwise). The dispatch routes set it.
- lib/ownership canViewRun(run, viewer): isAdmin OR owner === viewer.owner OR
  (run.workspace is set AND viewer.workspaces includes it). listRuns and getRun use
  it; a run the viewer cannot see reads as absent (404), unchanged for the solo case.
- A small header indicator shows the viewer's workspace membership (read-only for
  v1; no workspace switcher needed yet). Document the claim in dashboard/README
  Authentication.
- Tests: under the bypass everything is visible (admin); a pure ownership-filter
  unit test covers own vs workspace-shared vs neither vs admin. Keep tsc + lint
  clean, Playwright green with CONTIG_AUTH_DISABLED=1.

## B. Partner-ready demo package (devx-agent), under demo/

- demo/DEMO.md: a scripted walkthrough of the money story (launch a run, watch the
  self-heal fire, get an honest verdict, show the signed reproducible report), with
  exact CLI commands and the dashboard click path. Include a guaranteed self-heal
  path: a short generator command/script that makes a run OOM-fail then self-heal to
  PASS (use the existing injected-executor pattern from the test suite, e.g. an OOM
  exit then a clean exit), so the self-heal moment always fires on camera.
- demo/sample-run/: a generated, SIGNED self-heal PASS bundle (run_record.json +
  signature.json), produced with CONTIG_SIGNING_KEY set, so it is a real artifact a
  partner can verify with contig verify.
- demo/sample-report.html: render_run_report_html of that bundle (contig show
  --html), the shareable artifact, committed so it can be opened offline.
- demo/WHAT_THIS_PROVES.md: a one-page sheet mapping each demo step to the moat
  (run-and-verify, self-heal, reproducibility, the eval flywheel).
- demo/OUTREACH.md: a short cold-outreach script plus a design-partner session guide
  (what to watch, what counts as a yes) aligned to the ROADMAP Phase 0 exit gate.

## C. Deployment scaffolding (devx-agent), under deploy/ + dashboard/

- dashboard/docker-compose.yml: bring up the dashboard (the existing Dockerfile)
  with the runs directory mounted and the env wired (CONTIG_*, AUTH0_*), behind the
  reverse proxy.
- deploy/Caddyfile (or nginx.conf): a reverse-proxy example terminating TLS and
  forwarding to the dashboard; note the auth/headers.
- deploy/ENV.md: the full env checklist for a real deployment (Auth0 tenant setup,
  the roles and workspaces claims, CONTIG_RUNS_DIR, the signing key, SMTP).
- Append a Deployment section to dashboard/README pointing at compose + deploy/.
  Make clear the CLI/engine must be reachable from the dashboard container (the
  dashboard shells contig), and that this is self-hostable and free.

---

## Verification

- Dashboard: tsc + lint clean; Playwright green with CONTIG_AUTH_DISABLED=1.
- Demo artifact: the orchestrator confirms contig verify on demo/sample-run reports
  signed + signature_ok true, and the HTML renders.
- No secrets committed (no real keys in compose/env examples, use placeholders).

## Style / security constraints (carried)

- No em dash, en dash, or hyphen-as-pause anywhere.
- Workspace visibility denies by default; the claim is read from env-configured
  Auth0; secrets only from env, never committed.

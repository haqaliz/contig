<img src="public/logo.svg" alt="Contig" width="80" />

# Contig Dashboard

A Next.js (App Router, TypeScript) dashboard for Contig. It reads run bundles
(`run_record.json`), live run state, the failure corpus, and the eval history
directly from disk, and shells out to the `contig` CLI for actions (launch,
cancel, resume, approve, verify), so it needs no separate backend. Tailwind v4 +
shadcn/ui (on Base UI).

It started as the read-only "Run Inspector" and now covers the full Layer-2 loop:
launch a run, watch it live, steer the self-heal, verify and reproduce the result,
compare runs, curate the failure corpus, and track the detector over time.

> It runs the CLI on your machine and can launch and cancel real pipelines.
> Authentication is off by default for local use (see Authentication below); with
> no Auth0 env configured the dashboard treats every caller as an admin, so do not
> expose an unconfigured instance to a network.

## What it does

- **Runs** (`/runs`): every run bundle with its honest verdict (pass, warn, fail,
  unverified), pipeline and revision, task counts, and whether self-heal kicked
  in. Filter, search, and sort. Header actions: **Run test profile**, **New run**,
  and **Compare runs**. A live "In progress" section lists runs that are still
  going.
- **New run** (`/runs/new`): a launch form (goal, sample-sheet path, an iGenomes
  key or a fasta + gtf pair, optional resource caps). Preview the plan, then
  launch. After the plan preview it shows a **pre-run estimate** (runtime and cost)
  derived from past runs of that pipeline (or a transparent heuristic with no
  history) via `contig estimate --json`. `?from=<id>` pre-fills it from a past
  run's launch manifest.
- **Run detail** (`/runs/<id>`): the verdict explained in plain language with the
  deciding QC checks, an output-integrity badge (verified, drift detected, or not
  captured) with a **Verify** action, a **resources and cost** card (per-task
  wall-clock duration and peak memory from the run's recorded `resource_usage`,
  with a total cost at the default or entered rates via `contig cost --json`), the
  QC results (per-sample and cross-sample drill-down), the detect to diagnose to
  patch to outcome repair timeline, the pinned provenance, **Reproduce exactly** /
  **Edit and relaunch**, and **Export and cite** (download the run's RO-Crate
  metadata JSON via `contig export --rocrate` and a citation-ready methods
  paragraph via `contig methods`, both generated offline).
- **Live run view**: while a run is in flight the page polls a snapshot (elapsed,
  tasks completed, currently running steps, live self-heal attempts) with a
  collapsible log tail and a **Cancel** button. If the self-heal loop proposes a
  risky patch the run pauses and the page shows **Approve** / **Reject** (a
  destructive patch needs a second confirm). A cancelled or interrupted run offers
  **Resume** (re-runs from the cached tasks).
- **Compare** (`/runs/compare`): pick two runs and diff verdict, pipeline, params,
  checksums, container digests, task counts, and QC, with a reproduced or not
  reproduced summary.
- **Pending** (`/pending`): review auto-captured failure cases and confirm or
  correct their label, promoting them into the golden corpus (moat #2).
- **Detector** (`/eval`): the failure detector scored against the labeled corpus
  (accuracy, per-class precision/recall, current misses), a **detector selector**
  (rules, rules-strict, and the optional **llm** detector) that scores any
  registered detector, a **side-by-side detector comparison** (the latest snapshot
  per detector, so rules vs llm is direct: overall accuracy and per-class recall),
  and an accuracy-over-time trend with per-class deltas. The detector stays in
  Python (the moat); the page shells out to `contig eval-detector --json`. The llm
  detector is optional: with no provider or key configured it resolves to the
  existing graceful "not available" branch. To add an llm-tagged point for the
  comparison, run `contig eval-detector --detector llm --snapshot` with a provider
  and key configured.
- **Notifications**: a header activity bell reads `notifications.jsonl` and shows
  recent run events; a run waiting for your approval links straight to it.

## Run it

From `dashboard/`:

```bash
npm install      # first time only
npm run dev      # http://localhost:3000
```

By default it reads `../runs` and runs `uv run contig` from the repo root. If the
CLI is unavailable, pages that need it degrade gracefully. Environment overrides:

| Variable | Default | What it controls |
|---|---|---|
| `CONTIG_RUNS_DIR` | `../runs` | Where run bundles, status, and `notifications.jsonl` are read |
| `CONTIG_CMD` | `uv run contig` | The CLI used for read-only calls (e.g. eval-detector) |
| `CONTIG_DISPATCH_CMD` | `uv run contig` | The CLI used to launch and control runs, and for estimate, export, and methods (dispatch, cancel, resume, approve, verify, cost, estimate, export, methods) |
| `CONTIG_EVAL_HISTORY` | shipped path | The eval-history file the trend reads |

## Authentication

Auth0 provides authentication and role-based authorization, configured entirely
from env so Contig stays open source with no tenant baked in. The boundary is
`proxy.ts` (Next 16's renamed middleware): it gates every route, redirects an
unauthenticated request to login, and rejects a write (action) request that lacks
the writer role. The action routes (dispatch, launch, cancel, resume, approve,
reproduce, verify, corpus promote) also re-check the role themselves, so
authorization never rests on the proxy matcher alone.

Roles come from a namespaced claim on the user (set by an Auth0 Action or rule),
`https://contig/roles` by default. A user with the **writer** or **admin** role
may run the action routes; any other authenticated user is read-only (a viewer).

To turn auth on, set these in the environment (never commit real values):

| Variable | What it is |
|---|---|
| `AUTH0_SECRET` | A 32-byte hex secret for cookie encryption (`openssl rand -hex 32`) |
| `AUTH0_DOMAIN` | The tenant domain, e.g. `your-tenant.us.auth0.com` (or set `AUTH0_ISSUER_BASE_URL`) |
| `AUTH0_CLIENT_ID` | The Auth0 application's client id |
| `AUTH0_CLIENT_SECRET` | The Auth0 application's client secret |
| `APP_BASE_URL` | This app's URL, e.g. `http://localhost:3000` |
| `AUTH0_ROLES_CLAIM` | Optional: override the namespaced roles claim (default `https://contig/roles`) |

The SDK mounts its own routes at `/auth/login`, `/auth/logout`, and
`/auth/callback`; add the callback and logout URLs to the Auth0 application's
allow-lists. The header shows the logged-in user with a logout link.

**Dev/test bypass.** When `CONTIG_AUTH_DISABLED=1`, or when no Auth0 env is
configured, the proxy is a no-op: every route is reachable and the caller is
treated as an admin, so local dev and the Playwright suite run with no real
tenant. The header then shows a synthetic "Local admin" account. Run the e2e
suite with the bypass on:

```bash
CONTIG_AUTH_DISABLED=1 npx playwright test
```

**Per-user run isolation.** With auth on, each dispatch tags its run with the
owner's identity in `runs/<id>/owner.json` (`{owner, email}`, where `owner` is the
Auth0 `sub`). The run list and run detail are then scoped to the current user: a
user sees only the runs they own; the **admin** role sees all; a run with no
`owner.json` (for example a CLI-launched run) is admin-only; and a run the user
does not own reads as absent (a 404), so it never leaks. Under the bypass the
viewer is the synthetic local admin, so local dev and the suite see every run.
Ownership lives entirely in the dashboard; the engine is unchanged.

## Deploy

The repo ships a multi-stage `Dockerfile` that builds the dashboard into a lean
Next.js standalone server image (`output: "standalone"` in `next.config.ts`). The
image serves the dashboard only; it does not bundle the `contig` engine CLI or the
runs directory, because those live on the user's compute. Build and run it:

```bash
docker build -t contig-dashboard .
docker run --rm -p 3000:3000 \
  -e CONTIG_AUTH_DISABLED=1 \
  -v /path/to/runs:/runs \
  -e CONTIG_RUNS_DIR=/runs \
  contig-dashboard
```

- **The runs volume.** Mount the host runs directory into the container and point
  `CONTIG_RUNS_DIR` at the mount, so the dashboard reads the same bundles, status,
  `notifications.jsonl`, and `owner.json` files the engine writes.
- **The CLI.** Read-only and action routes shell out to `contig`. Point `CONTIG_CMD`
  and `CONTIG_DISPATCH_CMD` at a reachable CLI (a host binary on the mounted path,
  a sidecar container, or `uv run contig` in an image that also has the engine and
  Nextflow). With no CLI reachable, pages that need it degrade gracefully but
  launch and verify will not work.
- **Auth.** For anything network-reachable, configure the Auth0 env above and set
  `APP_BASE_URL` to the public URL; do **not** expose an unconfigured instance,
  since the bypass treats every caller as an admin. Set `CONTIG_AUTH_DISABLED=1`
  only for a trusted, local, single-user deployment.
- **Reverse proxy.** The container listens on `:3000` over plain HTTP. Put a
  reverse proxy (nginx, Caddy, a cloud load balancer) in front for TLS termination
  and to forward `Host` / `X-Forwarded-*` headers; set `APP_BASE_URL` to the
  externally visible URL so the Auth0 callback and logout URLs line up.

## Testing

- `npx tsc --noEmit` and `npm run lint` for types and lint.
- `npx playwright test` for the end-to-end suite. It runs against synthetic run
  fixtures in `e2e/fixtures/`, provisioned into the runs directory only for the
  duration of the suite (global setup and teardown) so they never clutter a real
  dashboard. `PW_PORT` runs the suite on an isolated port when another app holds
  3000.

## Layout

- `lib/types.ts`: TypeScript mirror of the engine's serialized models.
- `lib/runs.ts`: server-only disk access and CLI shell-outs (bundles, status,
  progress, corpus, eval, notifications, dispatch, cancel, resume, approve,
  verify, cost).
- `lib/auth0.ts` + `proxy.ts`: the Auth0 client, the role helpers and the
  `requireWriter` action-route guard, and the route-gating proxy with its
  dev/test bypass (see Authentication above).
- `lib/derive.ts`: pure, client-safe helpers over a run record (verdict
  explanation, task counts, QC sorting).
- `components/`: the verdict card, QC panels, repair timeline, live run view,
  approval gate, notifications bell, output-integrity card, and the shared UI.
- `app/runs`, `app/runs/new`, `app/runs/[id]`, `app/runs/compare`, `app/pending`,
  `app/eval`: the views. `app/api/runs/[id]/*`: the action routes.

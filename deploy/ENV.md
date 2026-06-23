# Deployment environment checklist

Everything Contig needs to run as a real, network-reachable, multi-user
deployment. Contig stays open source with no tenant baked in, so all of this is
supplied from the environment, never committed. Every value below is a
PLACEHOLDER: replace it with your own, and keep secrets in your platform's secret
store, not in a checked-in file.

The hard rule: never commit a real secret. The only key committed anywhere in
this repo is the throwaway demo signing key under demo/sample-run, and it is
explicitly a discarded demo key, not a credential.

---

## 1. Where runs live

| Variable | Example placeholder | What it controls |
|---|---|---|
| `CONTIG_RUNS_DIR` | `/var/lib/contig/runs` | The directory holding run bundles, live status, `notifications.jsonl`, and `owner.json`. The dashboard reads it; the engine writes it. In docker-compose this is a mounted volume the dashboard and the engine both see. |
| `CONTIG_CMD` | `uv run contig` | The CLI the dashboard uses for read-only calls (for example eval-detector). |
| `CONTIG_DISPATCH_CMD` | `uv run contig` | The CLI the dashboard uses to launch and control runs (dispatch, cancel, resume, approve, verify, cost, estimate, export, methods). Must be reachable from wherever the dashboard runs, because the dashboard shells out to it. |

The dashboard shells out to the `contig` CLI; it does not embed the engine. The
CLI (and Nextflow, and a container runtime) must be reachable from the dashboard's
process. See the Deployment section of dashboard/README.md for the three ways to
arrange that.

---

## 2. Signing (tamper-evident run records)

| Variable | Example placeholder | What it controls |
|---|---|---|
| `CONTIG_SIGNING_KEY` | `<64-hex-char Ed25519 private key>` | When set, every run record is signed and a `signature.json` sidecar is written next to it, so `contig verify` can confirm the record was not edited after the run. Absent or empty means runs are unsigned. |

Generate a keypair with `uv run contig keygen`. Set `CONTIG_SIGNING_KEY` to the
printed private key in the engine's environment (the process that runs `contig
run`), and keep it secret; share only the public key with anyone who needs to
verify. Rotating the key changes which public key verifies future runs; past runs
stay verifiable with the public key they were signed under.

---

## 3. Email notifications (optional, best effort)

Set all six to have Contig email a run's terminal event (finished, failed). All
of it is best effort: a misconfigured or unreachable mail server never crashes a
run. Leave them unset to disable email entirely (the dashboard activity bell and
the optional webhook still work).

| Variable | Example placeholder | What it is |
|---|---|---|
| `CONTIG_SMTP_HOST` | `smtp.example.com` | The mail server hostname |
| `CONTIG_SMTP_PORT` | `587` | The mail server port |
| `CONTIG_SMTP_USER` | `contig@example.com` | The SMTP username |
| `CONTIG_SMTP_PASSWORD` | `<smtp app password>` | The SMTP password or app token (a secret) |
| `CONTIG_SMTP_FROM` | `contig@example.com` | The From address on the notification |
| `CONTIG_SMTP_TO` | `lab-alerts@example.com` | Where notifications are sent |

---

## 4. Authentication and authorization (Auth0)

For anything network-reachable, configure Auth0. With no Auth0 env configured (or
with `CONTIG_AUTH_DISABLED=1`), the dashboard treats every caller as an admin and
the gate is a no-op, so do not expose an unconfigured instance. Set
`CONTIG_AUTH_DISABLED=1` only for a trusted, local, single-user deployment.

### 4a. Tenant and application setup

1. Create an Auth0 tenant (the free tier is enough), then create a Regular Web
   Application in it.
2. In the application settings, add the dashboard's callback and logout URLs to
   the allow-lists. The SDK mounts its routes at `/auth/callback`, `/auth/login`,
   and `/auth/logout`, so for a deployment at `https://dashboard.example.com`:
   - Allowed Callback URLs: `https://dashboard.example.com/auth/callback`
   - Allowed Logout URLs: `https://dashboard.example.com`
3. Note the tenant domain, the client id, and the client secret for the variables
   below.

### 4b. Core Auth0 variables

| Variable | Example placeholder | What it is |
|---|---|---|
| `AUTH0_SECRET` | `<32-byte hex from: openssl rand -hex 32>` | Secret used to encrypt the session cookie (a secret) |
| `AUTH0_DOMAIN` | `your-tenant.us.auth0.com` | The tenant domain (or set `AUTH0_ISSUER_BASE_URL` instead) |
| `AUTH0_CLIENT_ID` | `<auth0 application client id>` | The application's client id |
| `AUTH0_CLIENT_SECRET` | `<auth0 application client secret>` | The application's client secret (a secret) |
| `APP_BASE_URL` | `https://dashboard.example.com` | This app's externally visible URL, so the Auth0 callback and logout URLs line up. Behind the reverse proxy, this is the public https URL, not the container's internal `:3000`. |

### 4c. The roles claim (who may run actions)

Authorization is role based. A user with the `writer` or `admin` role may run the
action routes (launch, cancel, resume, approve, verify, and so on); any other
authenticated user is read-only. Roles arrive on the user as a namespaced claim,
set by an Auth0 Action or rule.

| Variable | Example placeholder | What it is |
|---|---|---|
| `AUTH0_ROLES_CLAIM` | `https://contig/roles` | The namespaced claim the dashboard reads roles from. Defaults to `https://contig/roles`; only set this to override the namespace. |

In an Auth0 post-login Action, add the user's roles under this exact claim name,
for example:

```js
exports.onExecutePostLogin = async (event, api) => {
  const roles = event.authorization?.roles ?? [];
  api.idToken.setCustomClaim("https://contig/roles", roles);
  api.accessToken.setCustomClaim("https://contig/roles", roles);
};
```

### 4d. The workspaces claim (shared run visibility)

A workspace is a shared run pool a lab sees together, layered on top of per-user
ownership. A viewer's workspace membership arrives as a second namespaced claim;
a run tagged with a workspace is visible to any viewer who belongs to it.

| Variable | Example placeholder | What it is |
|---|---|---|
| `AUTH0_WORKSPACES_CLAIM` | `https://contig/workspaces` | The namespaced claim the dashboard reads workspace membership from. Defaults to `https://contig/workspaces`; only set this to override the namespace. |

Add the user's workspaces under this claim in the same post-login Action, as a
string array, for example:

```js
api.idToken.setCustomClaim("https://contig/workspaces", ["acme-lab"]);
api.accessToken.setCustomClaim("https://contig/workspaces", ["acme-lab"]);
```

A user with no workspaces claim simply sees only their own runs (the solo case),
unchanged. The admin role continues to see every run.

---

## 5. Putting it together

- For local single-user use: set `CONTIG_AUTH_DISABLED=1` and `CONTIG_RUNS_DIR`,
  skip the rest. This is the open, no-tenant default.
- For a real deployment: set the runs variables, the Auth0 block (4b through 4d),
  and `APP_BASE_URL` to the public https URL behind the reverse proxy; add signing
  (section 2) for tamper-evident records and SMTP (section 3) for email. Put the
  Caddy or nginx proxy from this directory in front for TLS.

dashboard/docker-compose.yml wires these for a self-hosted bring-up. Fill its
values from your secret store; never commit real secrets into it.

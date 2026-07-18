# Card: feat reproduce-env-resurrection

**Type:** feat · **Owner:** aliz · **Branch:** `feat/reproduce-env-resurrection/aliz`

No GitHub issue — this unit of work came from `/contig-next`. The recommendation below is the source brief.

## Brief

**C8 slice 2 — environment resurrection for `contig reproduce`** (walking skeleton).

Slices 1 (v0.40.0) and 1.5 (v0.41.0) made `contig reproduce` *read* real repos: it runs a
repo's script and reports a per-claim verdict (`REPRODUCED` / `WITHIN-TOLERANCE` / `DIVERGED`
/ `UNVERIFIED`) over scalar numeric claims, binding values from a repo-written `results.json`
or from a JSON output-locator. But it can only reproduce repos that already **run** — an
uncooperative repo whose environment is missing a dependency just exits non-zero and degrades
to UNVERIFIED.

This slice attacks the **dominant reproduction-failure class**: `ModuleNotFoundError` /
`ImportError` + dependency installs are ~76% of reproduction failures
(`CAPABILITY_ROADMAP.md:1121-1124`; `docs/planning/reproduce-published-work/prd.md:117`).
The roadmap names environment resurrection as "the load-bearing piece" and scopes it as
**slice 2 (ImportError → install → retry)**.

### What to build (walking skeleton)

When a reproduced repo's run exits non-zero and its captured output shows a
`ModuleNotFoundError` / `ImportError` naming a missing module:
1. Detect the missing module name from the captured error text.
2. Install it through an **injected installer seam** (never a real network install in CI —
   mirror C2's injectable `IndexBuilder` / scripted-executor pattern).
3. Retry the run once, under a bounded budget.
4. Re-classify the claims against the retried run's output.

Reuse C2's self-heal pattern and the existing injected `executor` seam in
`src/contig/verification/reproduce.py:244` (`run_reproduction`).

### Scope / honesty contract (unchanged)

- An unresolvable environment degrades to **`UNVERIFIED`**, never a false reproduce.
- Test-first, with a scripted executor + scripted installer — **no real repo, no network, no
  real installs in CI** (standing determinism contract, `prd.md:140`).
- Bounded retries so the loop provably terminates (C2 discipline).
- Layer-2 only (run/self-heal/verify/reproduce). No Layer-1 workflow authoring. No raw-read
  egress. Stdlib-only runtime dep contract (`pydantic`/`typer`/`cryptography`) preserved —
  the installer is an injected seam, not a new dependency.

### Known caveat (must resolve early)

The current `executor` seam is typed `Callable[[list[str], Path], int]` — it returns **only
an exit code**, not stderr/stdout. So an `ImportError` cannot be detected today. The first
real step is to **widen the executor contract to surface captured output** (or add a
captured-output seam) before detection is possible. Small, real contract extension — not a
blocker.

The one genuine go/no-go the PRD flags (`prd.md:201`): does running an uncooperative repo
actually surface the `ModuleNotFoundError` in a catchable form? The scripted-executor walking
skeleton is exactly what pins that down in CI.

### Explicitly deferred (later slices)

- Trace-based version pinning / observed-version resolution (install the *right* version, not
  just the module).
- Multi-module / iterative resolution (install one, hit the next missing import, repeat) —
  keep the first slice to a single install + single retry; generalize later.
- Paper-parsing, figure/plot & table-cell claims, TSV/CSV locator, remote `<doi|url>`,
  dashboard card, C6 eval fold-in (unchanged from the slice-1/1.5 deferral lists).

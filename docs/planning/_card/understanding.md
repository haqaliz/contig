# Phase 2 dig — feat reproduce-remote-intake (C8 slice 6)

Grounded in the worktree at `origin/master` (v0.46.0). Every claim below is line-cited;
anything unverified is labelled as such.

## What the work is really asking

Make `contig reproduce` able to take a **remote git URL** instead of only a local directory,
fetch it, record the **resolved commit** so the reproduction is itself re-runnable, and hand
the checkout to the already-shipped engine unchanged.

## Current state (verified)

- **Intake is local-only and validated first.** `cli.py:781-784` is the entire intake:
  `repo_path = Path(repo)`; `if not repo_path.is_dir(): "No such repo directory" → Exit(1)`.
  Everything downstream (`--results` containment `:789-794`, locator containment `:836-847`,
  the engine's `repo_root` `reproduce.py:874`) keys off that path.
- **`ReproduceRecord` has no revision field.** `models.py:669-678`: `reproduce_id`, `repo`,
  `run_command`, `claims_sha256`, `claim_results`, `exit_code`, `created_at`, `interpreter`,
  `tool`, `repair_history`. `repair_history: list[RepairStep] = []` (`:678`) is the slice-2
  precedent for an **additive, defaulted** field that keeps older bundles loading.
- **The re-runnable manifest omits any revision.** `bundle.py:89-96` writes `reproduce.json`
  with `reproduce_id`, `repo`, `run_command`, `claims_sha256`, `created_at`. For a remote
  repo, `repo` alone (a URL whose default branch moves) is **not** re-runnable — the
  strongest argument for pinning the commit, and a reproduce-guarantee argument rather than a
  nice-to-have.
- **Seam conventions are uniform.** `runner.py:567-578` declares three seams as plain callable
  aliases — `Executor`, `IndexBuilder`, `Installer`, all `Callable[[list[str], Path], int]`,
  each commented "tests inject a fake, so no real tool runs in CI". Defaults (`:594-647`) all
  use `subprocess.run` with an **argv list, no shell, `check=False`**, converting failure to a
  returned exit code rather than an exception. `_pip_install_argv` (`:635-637`) is the "fixed
  argv, no interpolation" pattern to copy. `default_command_executor` (`:608-619`) is the odd
  one out: it returns `(exit_code, combined_output)`.
- **Run-scoped scratch dirs are established.** `self_heal.py:635` (`run_dir/healed_index/star`)
  and `:795` (`run_dir/healed_reference`) — a fetched checkout should follow the same shape.
- **Dependency contract.** `pyproject.toml:30-34`: runtime deps are exactly `pydantic`,
  `typer`, `cryptography`. Git would be an **external binary** invoked via subprocess (like
  samtools/STAR), not a Python dependency — so the stdlib-only contract holds.
- **No network code exists anywhere in `src/contig/` except `default_installer`'s pip**
  (`runner.py:640-647`). This slice adds the second network surface in the codebase.
- **CI has no marker infrastructure.** `.github/workflows/ci.yml:20` is a bare `uv run pytest`;
  `pyproject.toml:58-60` sets only `testpaths`/`addopts` — **no custom markers**. Manual gates
  elsewhere are done by *injected seams*, not skip markers (the only `skipif`s are
  signing-key ones: `tests/test_bundle.py:172`, `tests/test_reproduce_bundle.py:18`). A
  network-free suite must therefore be achieved **by construction**, not by excluding tests.

## The finding that most shapes the design

**The fetch must happen BEFORE `run_started_at` is stamped, and this is a correctness
requirement, not a style preference.**

`cli.py:853-858` stamps `run_started_at = time.time()` after all validation and before the
executor. The v0.46.0 freshness guard (`reproduce.py:880-919`) marks any artifact whose
`mtime < run_started_at` UNVERIFIED, precisely so a repo that **commits its outputs** cannot
report a false `REPRODUCED`.

A `git clone` writes every file at clone time. Therefore:

- **Clone before the stamp** → every author-committed artifact has `mtime < run_started_at`
  → correctly stale → the guard keeps working exactly as designed. ✅
- **Clone after the stamp** → every author-committed artifact looks *fresh* → the guard is
  silently disabled for remote repos → **reintroduces the exact false-`REPRODUCED` hole
  v0.46.0 just closed**, and reintroduces it only on the path (real published repos) where it
  matters most. ❌

This ordering deserves an explicit regression test: *a cloned repo with a committed
`results.json` whose value exactly matches the claim must report UNVERIFIED, not REPRODUCED.*

## Affected areas

| Area | File | Change shape |
|---|---|---|
| Intake + ordering | `cli.py:781-784`, `:853-858` | branch local-path vs URL; fetch before stamp |
| New seam | `runner.py:567-578`, `:594-647` | `Fetcher` alias + `default_fetcher` + `_git_clone_argv` |
| Record | `models.py:669-678` | additive defaulted fields (source URL, resolved commit) |
| Manifest | `bundle.py:89-96` | carry the pin so a remote reproduction is re-runnable |
| Docs | `CHANGELOG.md`, `CAPABILITY_ROADMAP.md` C8 §1047-1390 + table row `:1404` + the now-stale "no network" at `:1377`, `docs/USAGE.md` (`:59`, `:214`-~`:312`) | standard shipped-slice sweep. **Not `FEATURES.md`** — its table (`:248-256`) stops at C6 and the last slice left it untouched |

## Ambiguities / open questions for the PRD

1. **Seam signature.** `int` (like `IndexBuilder`) or `(int, str)` (like
   `default_command_executor`)? Git's stderr is the only useful diagnostic for a failed clone,
   which argues for `(int, str)`.
2. **How is the commit resolved?** A second `git rev-parse HEAD` through the same seam, or
   `git clone` then read `.git/HEAD`/refs? The former needs the seam to return stdout.
3. **Opt-in flag shape and default.** Mirror `--allow-install`'s posture
   (`reproduce-env-resurrection/prd.md:123-124`: "Absent the flag, the command never installs,
   never hits the network, never mutates the environment"). Name TBD (`--allow-fetch`?).
4. **URL validation.** Needs a scheme allowlist and, critically, **refusal of any URL starting
   with `-`** (git would read it as an option — argv injection). Charset-guard precedent:
   `reproduce.py:44` `_SAFE_PACKAGE_TOKEN_RE`. Whether `file://` and `git+ssh` are allowed is
   a product decision.
5. **Where does the checkout live?** `runs_dir/<reproduce_id>/source/` (bundle-local, follows
   the `healed_*` precedent) vs a temp dir. Bundle-local is inspectable after the fact but
   bloats the bundle.
6. **Ref/tag/commit pinning on the way in** — does the user get `--rev`, or only "clone the
   default branch and record what we got"? Recording is required; requesting is optional.
7. **Shallow vs full clone.** `--depth 1` is faster but complicates `rev-parse` semantics and
   makes a `--rev` of an older commit impossible.
8. **Is `git` present?** An absent binary must be an honest pre-run refusal, never a traceback.

## Contradictions / corrections to the brief

- The brief said to mirror "`runner.Installer` / `runner.IndexBuilder`" — accurate
  (`runner.py:572-578`), **but** those return bare `int` while the reproduce executor returns
  `(int, str)`. "Mirror the seam" is therefore ambiguous; see open question 1.
- The brief implied there might be prior-dig blockers on remote intake. **There are none.**
  Every prior C8 PRD lists remote `<doi|url>` as a scope deferral only
  (`reproduce-output-locator/prd.md:124`, `reproduce-env-resurrection/prd.md:148-149`,
  `reproduce-notebook-locator/prd.md:158`, `reproduce-freshness-guard/prd.md:231`), and
  `reproduce-freshness-guard/prd.md:159` states plainly: *"Extending freshness to
  remote/`<doi|url>` intake — that intake does not exist yet."* Deferred for scope, never for
  feasibility.
- Every prior PRD's primary persona **already assumes a cloned repo as a manual human step**
  (`reproduce-env-resurrection/prd.md:70`, `reproduce-output-locator/prd.md:60`,
  `reproduce-notebook-locator/prd.md:64`: "Clones a public repo, runs its script…"). This
  slice automates a step the product design already presumed; it does not change the persona.
- My own earlier assumption that kallisto/STARsolo-style tests are excluded by a **pytest
  marker** was wrong: there is no marker infrastructure (`pyproject.toml:58-60`). Those tools
  stay out of CI by seam injection alone.

## Guardrail check (CLAUDE.md)

On-thesis Layer 2: intake for run → self-heal → verify → reproduce. No NL→workflow authoring,
no wet-lab/clinical dependency, no proprietary data. The one genuinely new risk is **executing
third-party code Contig itself fetched** — which is why the opt-in gate and the argv-injection
refusal are requirements, not polish.

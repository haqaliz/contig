# PRD: reproduce-remote-intake (C8 slice 6)

Status: draft for review. Owner: aliz. Branch: `feat/reproduce-remote-intake/aliz`.
Sources: `docs/planning/_card/issue.md` (contig-next handoff brief),
`docs/planning/_card/understanding.md` (Phase-2 dig),
`docs/technical/CAPABILITY_ROADMAP.md` C8 (`:1047-1404`).
Capability: **C8 (Reproduce & verify existing published work) — the intake half**.

## Problem Statement

`contig reproduce` can read a repo's numbers five ways (flat `results.json`, JSON pointer,
TSV/CSV cell, stdout/log regex, notebook cell) and guards every one of them against stale
artifacts (v0.40.0 → v0.46.0). All of that binding machinery sits behind an intake that
accepts **only a local directory**: `cli.py:781-784` is the whole of it —
`if not repo_path.is_dir(): "No such repo directory" → Exit(1)`.

So the workflow the product was designed around — every prior C8 PRD's primary persona
"clones a public repo, runs its script…" (`reproduce-env-resurrection/prd.md:70`,
`reproduce-output-locator/prd.md:60`, `reproduce-notebook-locator/prd.md:64`) — has a
human-performed first step that Contig never sees. Two concrete costs:

1. **A remote reproduction is not re-runnable.** `bundle.py:89-96` writes `reproduce.json`
   with `repo`, `run_command`, `claims_sha256`, `created_at` — and `ReproduceRecord`
   (`models.py:669-678`) carries no revision field at all. Hand-clone
   `github.com/x/y` today, and the bundle records a path like `./y` or a URL whose default
   branch moves under it. **Nothing in the bundle says which commit produced the verdict.**
   A signed, re-runnable bundle over an unpinned tree is a weaker guarantee than it looks.
2. **The C8 acquisition channel is manual.** "I ran 50 published papers' code — here is how
   many reproduced" (`CAPABILITY_ROADMAP.md:1353-1355`) is a batch over 50 URLs. Today it is
   50 hand-clones, so it hasn't been run, so the slice-4 `occurrence`/`group` selectors stay
   gated on "a counted post-merge experiment over 5 real repos" (`:1211`) and the C6 corpus
   stream (`:1379`) stays empty.

**Evidence this was deferred for scope, not feasibility:** every prior C8 PRD lists remote
`<doi|url>` as a scope deferral only (`reproduce-output-locator/prd.md:124`,
`reproduce-env-resurrection/prd.md:148-149`, `reproduce-notebook-locator/prd.md:158`,
`reproduce-freshness-guard/prd.md:231`), and `reproduce-freshness-guard/prd.md:159` states it
plainly: *"Extending freshness to remote/`<doi|url>` intake — that intake does not exist yet."*
No dig has ever recorded a blocker.

### The honest framing: the pin is the feature, the clone is plumbing

A user can already run `git clone X && contig reproduce ./X`. Stripped of the commit pin,
this slice is a wrapper around `git clone` and would not be worth shipping. What it adds that
the user cannot get by hand is a **bundle that names the exact commit its verdict was
computed over**. Every requirement below is prioritized against that.

## Goals & Success Metrics

- **G1 — A remote reproduction is re-runnable in principle.** *Measured:* after
  `contig reproduce https://… --allow-fetch`, `reproduce_record.json` and `reproduce.json`
  both carry the source URL and a full 40-char commit SHA. Asserted in tests.
- **G2 — The local path is byte-identical.** *Measured:* every pre-existing reproduce test
  passes unchanged, and a local-dir invocation produces a record whose fields are unchanged
  except for the two new ones defaulting to `None`.
- **G3 — The freshness guard survives remote intake.** *Measured:* a cloned repo with a
  **committed** `results.json` whose value exactly matches the claim reports `UNVERIFIED`,
  not `REPRODUCED`. This is the headline regression test (see R2).
- **G4 — No network, no git, no real repo in CI.** *Measured:* the fetcher is an injected
  seam; the suite passes with no network. `.github/workflows/ci.yml:20` is a bare
  `uv run pytest` and `pyproject.toml:58-60` defines **no markers**, so this must hold by
  construction, not by test exclusion.
- **G5 — Zero new runtime dependencies.** *Measured:* `pyproject.toml` deps stay exactly
  `pydantic`, `typer`, `cryptography` (`:30-34`). Git is an external binary (the
  samtools/STAR precedent), not a Python dep.

**Explicitly not a metric this slice:** how many real published repos reproduce. That number
is what the slice *enables*; measuring it is the post-merge experiment.

## User Personas & Scenarios

- **A — lone computational biologist / reviewer (primary).** Unchanged from every prior C8
  slice, minus the manual clone: points Contig at a paper's GitHub URL and a claims file, and
  gets a per-claim verdict plus a bundle that names the commit.
- **B — Contig itself, running the acquisition experiment.** Iterates a list of URLs to
  produce the "N of 50 reproduced" post. Needs one-command intake and a per-run pin so the
  published table is auditable.

## Requirements

### Must-have

- **R1 — `https://` URL intake behind an opt-in flag.** `contig reproduce <https-url>
  --allow-fetch` clones into `runs_dir/<reproduce_id>/source/` and runs there. `--allow-fetch`
  is **off by default**, mirroring `--allow-install`'s posture verbatim
  (`reproduce-env-resurrection/prd.md:123-124`: "Absent the flag, the command never installs,
  never hits the network, never mutates the environment"). A URL **without** the flag is an
  honest pre-run refusal naming the flag — never a silent local-path attempt.
- **R2 — The fetch happens BEFORE `run_started_at` is stamped.** `cli.py:853-858` stamps the
  freshness boundary; `reproduce.py:880-919` marks any artifact older than it UNVERIFIED. A
  `git clone` writes every file at clone time, so:
  - clone **before** the stamp → author-committed artifacts are correctly stale ✅
  - clone **after** the stamp → every committed artifact looks fresh → **the v0.46.0
    false-`REPRODUCED` hole is silently reopened, and only for real published repos** ❌

  This is a correctness requirement, not sequencing preference. It gets a dedicated test
  (G3) whose fixture is a committed `results.json` with an *exactly matching* value — the
  shape that would otherwise report a perfect false reproduction.
- **R3 — The commit is resolved and recorded.** After the clone, `git rev-parse HEAD` runs
  through the same seam; the full SHA lands on `ReproduceRecord` and in `reproduce.json`.
  Additive, defaulted fields (`source_url: str | None = None`, `source_commit: str | None =
  None`), following `repair_history`'s back-compat precedent (`models.py:678`) so pre-slice-6
  bundles load unchanged. **If the SHA cannot be resolved, the run is refused** — an
  unpinned remote reproduction is the thing this slice exists to prevent, so it must not be
  the fallback.
- **R4 — A new injected `Fetcher` seam.** `Fetcher = Callable[[list[str], Path], tuple[int,
  str]]` in `runner.py` alongside the existing three (`:567-578`), with `default_fetcher`
  shelling out via `subprocess.run` — **argv list, no shell, `check=False`**, failure
  returned as an exit code, never raised (`:594-647`). It returns `(int, str)` rather than
  the `IndexBuilder`/`Installer` bare `int` for two reasons: git's stderr is the only useful
  diagnostic for a failed clone, and `rev-parse`'s **stdout is how the pin is read**. A
  `_git_clone_argv(url, dest)` builder mirrors `_pip_install_argv`'s fixed-argv discipline
  (`:635-637`).
- **R5 — URL validation refuses argv injection, pre-run.** Only `https://` is accepted. Any
  argument **starting with `-`** is refused outright (git would read it as an option — e.g.
  `--upload-pack=`, a remote-code-execution shape), as are `ssh`, `git://`, `file://`,
  `ext::`, and anything else non-`https`. Precedent for a charset guard:
  `reproduce.py:44` `_SAFE_PACKAGE_TOKEN_RE`. Every refusal is exit-non-zero with **nothing
  written**, consistent with the command's existing pre-run validation block
  (`cli.py:781-847`).
- **R6 — Shallow clone (`--depth 1`).** Faster and smaller on the real published repos this
  targets; `HEAD` still resolves to a full SHA, so the pin is unaffected.
- **R7 — Honest failure on every unresolved path.** Git binary absent, clone fails, host
  unreachable, bad URL, `rev-parse` fails → exit non-zero, **no record, no bundle**, with the
  cause named. Never a traceback, never a partial bundle, never a false `REPRODUCED`.
- **R9 — The run dir's creation order inverts; a failed fetch must not leave litter.**
  Today nothing creates `<runs_dir>/<reproduce_id>/` until **after** the run completes
  (`cli.py:873`, `bundle.py:83` `dest.mkdir(parents=True, exist_ok=True)`). A fetch must
  create it **before** the run — the first time this command writes anything to disk ahead of
  a verdict. Consequences to specify, not discover: a **failed** fetch must not leave an empty
  or half-cloned `<reproduce_id>/` behind (clean up, so "no record, no bundle" from R7 stays
  literally true on disk), and the checkout dir follows the C2 scratch convention exactly —
  **rmtree-then-mkdir** for idempotence (`self_heal.py:635-638` STAR, `:795-798` reference,
  `cli.py:519-523` harmonized GTF). The clone must also **refuse a non-empty destination**
  rather than clone into it (closes OPEN-2).
- **R8 — A DOI argument is refused by name.** An argument starting `doi:` or a bare `10.`
  prefix gets *"DOI intake is not supported yet; pass an https:// git URL"* rather than
  falling through to "No such repo directory". A wrong-shaped honest error beats a
  misleading one. **No DOI resolution is attempted** (see Out of Scope).

### Should-have

- **S1 — The record distinguishes source from checkout.** For a remote run, `repo` holds the
  **URL**, not the scratch checkout path — `reproduce.json` deliberately omits scratch paths
  already (`bundle.py:75-77`, mirroring `LaunchManifest`). The local checkout path is an
  implementation detail and should not be baked into a portable manifest.
- **S2 — The rendered output names the pin.** `render_reproduction` shows the source URL and
  short SHA, so a terminal reader sees what was reproduced without opening the bundle.

### Nice-to-have

- **N1 — `contig methods` / HTML surfacing of the pin.** Consistent with how
  `ReferenceIdentity` and `AnnotationProvenance` are rendered, but not load-bearing here.

## Technical Considerations

- **Where it sits:** intake, strictly upstream of the shipped engine. `run_reproduction`
  (`reproduce.py:838-851`) is **not modified** — it receives a local path exactly as today.
  Locators, containment guards, freshness guard, `--allow-install`, signing, bundle, and
  `--fail-on-diverged` are all reused unchanged. This is the main design constraint and the
  reason the slice is small.
- **Validation ordering (`cli.py:781-858`)** is the delicate part. Today: dir check →
  `--results` containment → `load_claims` → `--run` shlex validation → tolerance re-default →
  locator containment → sha/id/timestamp → **stamp** → run. The fetch must slot in so that
  *URL-shape refusals happen with the other pre-run refusals* (cheap, nothing written) while
  the *clone itself* happens after claims/`--run` validation (don't pay for a clone to then
  reject a malformed claims file) and **before the stamp** (R2). That ordering is the single
  most important thing the tech-plan must get right.
- **New security surface.** This is the first code path where Contig **fetches code it then
  executes**. Mitigations: the opt-in flag, the `https`-only allowlist, the leading-`-`
  refusal, fixed argv with no shell, and containment of the checkout inside the run dir. It
  is worth stating plainly in the CHANGELOG rather than burying it.
- **Bundle size, with a real trigger.** Bundle-local checkouts (chosen) make the reproduced
  tree inspectable but can make a run dir hundreds of MB; `runs/` is gitignored but not
  auto-pruned, and nothing in Contig prunes it today. Accepted, with a **committed revisit
  trigger** rather than a vague one: if the acquisition experiment (50 repos) exceeds ~10 GB
  of retained checkouts, add `--keep-source`-style opt-out or prune-on-success. Stated so the
  follow-on has a number, matching the walltime slice's discipline of committing a numeric
  revisit trigger.
- **The checkout is evidence, not attestation — state it, don't imply otherwise.**
  `bundle.py:87` signs the **record** (`_maybe_write_signature`), and nothing else. A
  bundle-local `source/` tree is therefore unsigned and unhashed: it sits next to a signed
  record and can be modified afterwards with nothing detecting it. This slice does **not**
  hash the tree (a recursive tree hash is its own slice, and the commit SHA already pins what
  was *fetched*). The docstring and CHANGELOG must say plainly that `source/` is a
  convenience copy for inspection, and that the **commit SHA — not the on-disk tree — is the
  attested fact**. Getting this wrong in the other direction (implying the checkout is
  verified) would be an over-claim of exactly the kind the verdict contract forbids.
- **Reproducibility impact — the point of the slice.** The bundle gains the one fact that
  makes a remote verdict auditable. Note the honest limit: recording a commit makes the
  reproduction re-runnable **in principle**; actually re-running at that commit needs `--rev`,
  which is deliberately a follow-on (see Out of Scope).
- **The engine signature stays untouched — deliberately.** Because `run_reproduction` takes
  `repo: str` positionally (`reproduce.py:839`), the CLI resolves a URL to a local checkout
  path *before* calling it. So there is **no `allow_fetch`/`fetcher` pair on the engine**,
  unlike `allow_install`/`installer`; the blast radius is `cli.py` plus a new seam in
  `runner.py`. This mirrors how the freshness slice landed ("no CLI signature change and no
  new flag were needed", `CAPABILITY_ROADMAP.md:1317`).
- **A doc assertion goes stale and must be amended, not left to rot.**
  `CAPABILITY_ROADMAP.md:1377` currently asserts C8 acceptance is "Deterministic, no network."
  That stays true *of CI* but stops being true of the command. The C8 section (`:1047-1390`),
  its sequencing row (`:1404`, whose trailing `**Deferred:**` clause lists remote
  `<doi|url>`), `CHANGELOG.md`, and `docs/USAGE.md` (command table `:59`; the reproduce
  section `:214`-~`:312`, whose `--allow-install` paragraph `:253-256` is the prose template
  for a new opt-in) all need updating. **`FEATURES.md` does not** — its capability table
  (`:248-256`) stops at C6 and its reproduce mentions are the *dashboard* bundle feature, not
  this command; the last shipped slice left it untouched.
- **Guardrail check (`CLAUDE.md`).** Layer 2 throughout — intake for run → self-heal → verify
  → reproduce. No NL→workflow authoring, no wet-lab/clinical dependency, no proprietary data.

## Risks & Open Questions

- **RISK-1 (highest): R2 gets implemented in the wrong order.** Clone-after-stamp is a
  one-line mistake that silently disables the freshness guard on exactly the runs it matters
  for, and every test would still pass unless the G3 test exists. **Mitigation:** write the
  G3 test first (TDD RED), before any fetch code.
- **RISK-2: shallow clone vs a future `--rev`.** `--depth 1` can't check out an arbitrary
  older commit. Accepted now; a `--rev` follow-on will need `--depth 1 --branch <ref>` or a
  targeted fetch. Recorded so the follow-on isn't surprised.
- **RISK-3: `git rev-parse` output parsing.** Must be stripped and validated as a 40-char hex
  SHA before being recorded — a fabricated or truncated pin is worse than none. Refuse rather
  than record something unvalidated.
- **RISK-4: no real-world exercise in CI, by design.** Like every C8 slice, correctness here
  is *reasoned and unit-tested*, not observed. The honest post-merge validation is the manual
  gate: clone ≥1 real public repo through the real seam, by hand, once.
- **RISK-5 (surfaced by self-critique): the pin has no in-product consumer yet.** With
  `--depth 1` and `--rev` deferred, **no code path reads `source_commit`** — only a human can
  act on it (`git checkout <sha>` by hand). So the slice's headline value is partly deferred
  to a follow-on that is not scheduled. Two honest readings: (a) recording the fact is
  necessary-but-not-sufficient and the follow-on is cheap once the field exists; (b) a
  recorded string nothing consumes is speculative work. This PRD takes reading (a) — the
  field is the schema change, and schema changes are the expensive half — but the disagreement
  is real and is flagged rather than hidden. **Decision needed at the review gate** (see the
  gate question).
- **OPEN-1:** should `--allow-fetch` also be required for a `file://`-style local clone later,
  or is the flag strictly "touches the network"? Leaning strictly-network, matching
  `--allow-install`'s framing.
- ~~**OPEN-2**~~ **resolved into R9.** Reproduce ids are microsecond-stamped
  (`cli.py:206-208`, `"run-" + …%H-%M-%S-%fZ`), so collision is effectively impossible; the
  clone refuses a non-empty destination regardless.

## Out of Scope

- **DOI resolution** (R8 refuses it by name). A DOI resolves to a landing page and only
  sometimes to a Zenodo/DataCite `codeRepository`; guessing a repo URL from a DOI is exactly
  the kind of heuristic that produces a confidently wrong reproduction.
- **`--rev` / requesting a specific ref.** Record-only this slice; consuming the recorded pin
  to replay is the natural follow-on.
- **ssh / `git://` / `file://` / non-git hosts (Zenodo tarballs, OSF, Figshare).**
- **Batch mode** (`contig reproduce --from urls.txt`). The experiment can shell-loop.
- **Paper-parsing to extract claims; figure/plot claims** (hard-blocked: no plot-hash, would
  break the stdlib-only contract, `CAPABILITY_ROADMAP.md:1337-1344`); **dashboard card**;
  **C6 eval fold-in** (blocked on a labeling design) — standing C8 deferrals, unchanged.
- **Credential handling / private repos.**

## Testing & Determinism

Test-first per the repo's standing discipline. Layers: pure URL-validation predicate → argv
builder → CLI ordering/refusals → the G3 freshness regression → record/manifest round-trip
with back-compat for a pre-slice-6 bundle. A scripted fake fetcher (mirroring the scripted
installer) populates an on-disk fixture tree and returns canned `rev-parse` output.
**No real git, network, or repo in CI** — enforced by seam injection, since the suite has no
marker infrastructure to exclude anything.

## Post-merge validation (manual, not CI)

Run the real path once by hand against ≥1 real public repo: confirm the clone lands, the SHA
is recorded, the claims bind, and — the important one — that a repo with committed outputs
reports `UNVERIFIED` rather than `REPRODUCED`.

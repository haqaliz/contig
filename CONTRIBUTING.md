# Contributing to Contig

Thanks for your interest. Contig is an agentic bioinformatics analyst focused on
**Layer 2** — running pipelines, self-healing failures, verifying outputs, and
guaranteeing reproducibility. The most valuable contributions harden that engine
and grow the data behind it. See [VISION.md](VISION.md) for the bet and
[docs/USAGE.md](docs/USAGE.md) for how the tool is used.

---

## Development setup

Contig is a Python 3.12 package managed with [`uv`](https://github.com/astral-sh/uv).

```bash
git clone https://github.com/haqaliz/contig.git
cd contig
uv sync                 # create the venv and install deps (incl. dev)
uv run pytest           # run the full test suite — should be green
```

For **live** pipeline runs you also need Nextflow, a Java runtime (`JAVA_HOME`),
and a running Docker daemon — see [docs/USAGE.md → Prerequisites](docs/USAGE.md#prerequisites).
The CLI and the test suite run without them.

### Package management (uv)

- `uv sync` — install/refresh the environment from `uv.lock`.
- `uv add <pkg>` / `uv add --dev <pkg>` — add a runtime / dev dependency (updates `pyproject.toml` + `uv.lock`).
- `uv run <cmd>` — run a command inside the project venv (`uv run contig …`, `uv run pytest`).
- Commit `uv.lock` with any dependency change so builds stay reproducible.

### Dashboard (Next.js)

The dashboard under `dashboard/` is a Next.js 16 app (App Router, TypeScript,
Tailwind, shadcn/ui on Base UI). It reads run bundles from disk and shells out to
the `contig` CLI; it needs no separate backend.

```bash
cd dashboard
npm install
npm run dev                          # http://localhost:3000 (reads ../runs)
npx tsc --noEmit && npm run lint     # types and lint, both must be clean
CONTIG_AUTH_DISABLED=1 npx playwright test   # the e2e suite (auth bypass for local/CI)
```

Notes for dashboard work: this shadcn is on **Base UI**, not Radix (compose with
`render={<Component/>}`, not `asChild`; a link styled as a button uses the
`ButtonLink` component). Next 16 route `params`/`searchParams` are Promises (await
them). Do not run `next build`/`next start` against a running dev server. The e2e
suite provisions synthetic run fixtures from `dashboard/e2e/fixtures/` only for the
duration of the run, so they never clutter the real `runs/` directory. Auth is off
by default (`CONTIG_AUTH_DISABLED` or no Auth0 env); see the dashboard README for
the Auth0 and deployment setup.

---

## Style

One hard rule across the whole repo (code, comments, docs, commit messages,
strings): **no em dash, no en dash, and no hyphen used as a pause or clause break.**
Use commas, colons, or parentheses instead; plain hyphens only inside compound
words and flag names. Beyond that, match the surrounding code's naming, comment
density, and idiom. User input that reaches the CLI or a subprocess is validated
(charset, no leading dash) and passed as `--opt=value` with a `--` terminator before
positionals; never build a shell string from user input.

---

## Project layout

```
src/contig/
├── cli.py            # Typer CLI — the contig commands
├── planner.py        # goal → pipeline matching (deterministic, replaceable)
├── registry.py       # curated pipeline registry
├── runner.py         # invokes Nextflow, streams events
├── nfconfig.py       # generates nextflow.config per backend (local, aws_batch, …)
├── reference.py      # genome/reference resolution (iGenomes key or FASTA+GTF)
├── samplesheet.py    # sample-sheet parsing + validation
├── datashape.py      # input shape checks (replicates, single/paired-end, …)
├── detect.py         # failure detector — classifies a failed task
├── repair.py         # repair strategies (e.g. resource patch for OOM)
├── self_heal.py      # detect → diagnose → patch → retry loop
├── verification/     # QC checks → PASS / WARN / FAIL / UNVERIFIED verdict
├── report.py         # run report + repair chain rendering
├── bundle.py         # the reproducible run_record.json bundle
├── corpus.py         # failure-corpus capture, promotion, eval
├── events.py         # run event model
├── models.py         # shared pydantic models
├── workspace.py      # runs/ workspace layout
├── progress.py       # progress display
└── data/
    └── detector_corpus.jsonl   # labeled failure corpus (golden)

tests/                # one test module per source module (test_*.py)
dashboard/            # Next.js dashboard (Tailwind + shadcn/ui) — see FEATURES.md
docs/                 # vision, research, roadmap, product, technical, business
.claude/skills/       # repo-local Claude Code workflow skills (begin/end/worktrees/…)
```

Every source module has a matching `tests/test_<module>.py`. Mirror that when you
add code.

---

## How we work (test-first)

Contig is built **test-first**. For any feature or bugfix:

1. Write a failing test that captures the desired behavior (RED).
2. Make it pass with the smallest change (GREEN).
3. Refactor with the suite green.
4. Keep `uv run pytest` green before every commit.

Contributors using Claude Code can drive this with the repo-local skills in
[`.claude/skills/`](.claude/skills): `contig-begin-fast` (isolate → plan →
implement) and `contig-end-fast` (clean up after merge). They are conveniences,
not a requirement.

### Strategic guardrail

Contig deliberately does **not** build Layer 1 (turning English into a
workflow) as a product — that's a commodity we consume. Contributions should
harden the run / debug / self-heal / verify / reproduce engine, not turn Contig
into a workflow generator. If a change drifts that way, call it out in the PR.

---

## What to contribute

- 🩹 **Failure cases** — the highest-leverage contribution. A real run that broke,
  with the diagnosis and fix, grows the corpus that makes the detector better.
  See [docs/USAGE.md → failure corpus](docs/USAGE.md#how-the-detector-improves-failure-corpus)
  and `contig corpus-promote`.
- 🧪 **QC checks** — new metric or structural verification checks that strengthen a verdict (under `verification/`).
- 🧬 **Curated assays** — a vetted assay to pipeline mapping plus its QC rule pack. The recipe is five small mapping points, no engine rewrite: see [docs/technical/ADD_AN_ASSAY.md](docs/technical/ADD_AN_ASSAY.md).
- ☁️ **Backends** — extending the `nfconfig.py` mapping for `gcp_batch` / `k8s` (`local`, `aws_batch`, and `slurm` are wired; `slurm` is live-validated).
- 🖥 **Dashboard** — UI for any of the above (run views, QC, the corpus, the eval flywheel); see the `dashboard/` notes above.
- 🐛 **Bugs & docs** — fixes, clarity, examples.

---

## Pull requests

1. Branch from `master` (convention: `<type>/<id>/<owner>`, e.g. `feat/sarek-qc/aliz`).
2. Keep the change focused; add/extend tests; `uv run pytest` must pass.
3. Match surrounding style and naming.
4. Open a PR with a clear description of *what* changed and *why*. Link the issue if there is one.

Found a bug or have an idea? Open an [issue](https://github.com/haqaliz/contig/issues)
first for anything non-trivial, so we can agree on the approach before you build.
The issue and pull-request templates will guide you (a **failure case** is the
highest-leverage one).

---

## Conduct and security

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md). For a
**security vulnerability**, do not open a public issue: follow [SECURITY.md](SECURITY.md)
to report it privately.

---

## License

License not yet finalized (open source intended). By contributing you agree your
contributions will be licensed under the project's eventual open-source license.

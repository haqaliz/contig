# PRD — reproduce-env-alias-map

Research-use reproduce hardening. C8 follow-on slice. Phase 3/4 output of
`contig-begin-fast` (worktree `feat/reproduce-env-alias-map/aliz`).

## Problem Statement

`contig reproduce --allow-install` (C8 env resurrection, slice 2) resurrects a
third-party repo one missing Python dependency from running: detect
`ModuleNotFoundError` → `pip install <module>` → retry once. Two gaps, both named
by the slice-2 PRD as the explicit next slice
(`docs/planning/reproduce-env-resurrection/prd.md:110-113,143-145`):

1. **Import-name ≠ package-name.** The install target is the detected module token
   verbatim. `cv2` → `pip install cv2` fails; the correct PyPI name is
   `opencv-python` (`sklearn`→`scikit-learn`, `PIL`→`pillow`, `yaml`→`pyyaml`,
   ...). A repo that is one name-mismatched dep from running stays `UNVERIFIED`.
2. **Single-install cap.** One install + one retry only
   (`verification/reproduce.py:865-871,1248-1250`); a repo needing two missing
   deps is not chased (pinned by
   `test_run_reproduction_does_not_chase_a_second_missing_module`,
   `tests/test_reproduce_env_resurrection.py:221-236`).

The dominant reproduction-failure class is missing dependencies (~76% of failures,
`docs/technical/CAPABILITY_ROADMAP.md` C8). Every recovered repo also feeds the
shipped `ReproduceCase` capture channel, so the fix compounds moat #2.

## Goals & Success Metrics

**Goal:** recover more real third-party repos under `--allow-install` without
weakening any honesty guarantee.

Measurable (unit + guard level, all deterministic, no network):

- An alias-mapped import installs its resolved package: `cv2` →
  `pip install opencv-python` (asserted on the recorded argv and on
  `Patch.operation`).
- An unknown import name installs verbatim (byte-identical to today).
- A repo needing two missing modules is resurrected in ≤ 2 installs; the loop
  provably terminates (seen-set + cap).
- Every unresolved path stays `UNVERIFIED` (never a false reproduce) and the
  repair record states exactly what was installed per attempt.
- `reproduce-guard` stays live: new scenarios with the mutation-control pin
  intact; baseline refrozen only as a deliberate act if the guarded number moves.

Honest metric: field recovery value is **reasoned, not observed** — the slice-2
real-repo smoke (the alias-map go/no-go, PRD R3) has never been run; a real-repo
smoke stays a manual post-merge gate.

## User Personas & Scenarios

- **A, lone computational biologist** (the C8 persona): wants to verify a paper's
  numbers by running its repo; hits `ModuleNotFoundError: No module named 'cv2'`,
  runs `--allow-install`, and today gets an honest but useless `UNVERIFIED`
  because `pip install cv2` fails. After: the run resurrects and produces a
  per-claim verdict.
- **C, core facility** running reproductions at throughput: cares that the repair
  record states the actual installed package (auditability) and that the loop can
  never spin.

## Requirements

### Must-have

- **M1 — Curated alias data file.** `src/contig/data/import_aliases.tsv`:
  `#`-comments, no header, exactly two tab-separated fields
  `import_name<TAB>package_name`, focused seed ~15 rows:
  `cv2→opencv-python`, `sklearn→scikit-learn`, `PIL→pillow`, `yaml→pyyaml`, plus
  common bioinformatics/general mismatch pairs (e.g. `pysam`, `biopython`,
  `h5py`, `anndata`, `scanpy`, `seaborn`, `statsmodels`, `matplotlib`, `scipy`,
  `pandas`, `numpy` — only rows where the names actually differ; name-matching
  imports need no row).
- **M2 — Loud loader + pure resolver.** New module mirroring the
  `contig_aliases.py` pattern (`src/contig/contig_aliases.py:32-106`):
  `_build_import_alias_map(lines)` unit-testable on synthetic lines; malformed
  row / conflicting duplicate → `ValueError`; exact duplicate silently deduped;
  missing file propagates `FileNotFoundError`; module-level map built at import;
  public `package_for_import(name) -> str`. **Case rule, pinned:** table keys
  are lowercase; lookup on `module.lower()` (the detector is case-preserving —
  `"Pandas"` → `"Pandas"` — so normalization happens at lookup, never at
  capture); the recorded `operation["install"]` carries the table's package
  name verbatim; unknown → verbatim (the honest default).
- **M3 — Alias-aware install target.** In `run_reproduction`, the install argv is
  built from the **resolved** package name (the call site
  `verification/reproduce.py:1233`: `installer(_pip_install_argv(target),
  repo_path)`). `Patch.operation` records `{"install": <resolved package>}` (the
  record states what was actually installed); the original import name and the
  mapping ride in `RepairStep.detail`.
- **M4 — Bounded iterative resolution.** The one-install-one-retry block
  (`reproduce.py:1217-1279`) becomes a bounded loop: each cycle is detect →
  resolve → install → retry; a retry that fails with a **new** missing module
  starts the next cycle; **≤ 2 installs per run**; a **seen-set** of installed
  modules makes re-detection of an already-installed module stop as
  `install_failed` (termination by construction, cap as belt-and-braces). A retry
  failing with no new module keeps the existing `retry_failed` path.
- **M5 — One `RepairStep` per install attempt.** Each cycle appends its own
  step; `reproduce-guard`'s scorer compares `repair_history[-1].outcome` (last
  wins) unchanged (`reproduce_guard.py:218-231`). No new outcome literal, no
  signed-field change, `RepairOutcome` Literal unchanged.
- **M6 — Guard extension.** The scripted installer (`reproduce_guard.py:152-157`)
  gains argv recording so scenarios can assert the resolved package; new frozen
  scenarios: alias-map heal (`cv2` → `opencv-python`), two-install heal, and a
  second-install-fail give-up; mutation-control pin preserved (a deliberate
  mismatch must still flip the match). **Baseline mechanics, stated:** adding
  scenarios changes `reproduce_scenarios.jsonl` → `corpus_sha` mismatch → the
  baseline is **refrozen deliberately** via `--update-baseline` even if the
  guarded rate holds at 13/14 (the house rule: refreeze is a deliberate act,
  never a hand-edit, and never contingent on the number moving).
- **M7 — Contracts preserved.** `--allow-install` flag, CLI shape, installer
  seam signature, and the `UNVERIFIED`-never-a-false-reproduce contract all
  unchanged; stdlib-only; no new dependency; no signature break.
- **M8 — Revisit trigger (committed).** After merge, run the manual real-repo
  smoke on 3–5 public repos that fail with name-mismatched imports (the slice-2
  gate finally run). If alias hits are ~0 across them, the seed is restated as
  taxonomy-only and no further alias breadth is added on push alone; if the
  multi-module iteration is what recovered repos, that is the demand signal for
  the next C8 slice.

### Should-have

- **S1 — Docstrings updated** to the bounded-loop contract (today they say
  "exactly one retry, no re-detection afterwards", `reproduce.py:863-871`).
- **S2 — Detail messages** name the mapping (`cv2` → `opencv-python`) so a user
  reading the bundle sees why the target differs from the error text.

### Nice-to-have

- **N1 — A `--no-alias-map` escape hatch** (declined unless a user asks; the
  deterministic table has no reason to be disabled).

## Technical Considerations

- **Integration point:** `run_reproduction`'s install branch
  (`verification/reproduce.py:1217-1279`); the resolver is called between
  `detect_missing_module` and `_pip_install_argv`. The installer seam
  (`runner.py:729,1082-1094`) is untouched — the resolved name flows through the
  existing fixed argv.
- **Loop shape:** the seen-set is per-run state inside `run_reproduction` (like
  the existing per-run caches, `reproduce.py:875-878`); no module/global state.
- **Data packaging:** plain pathlib `_DATA_PATH` (the `contig_aliases.py:29`
  precedent); ships via the existing hatchling `packages = ["src/contig"]`
  (pyproject.toml:55-56). No conftest/data-dir override exists — tests inject
  synthetic lines into the pure builder and read the packaged file through the
  public API (the `test_contig_aliases.py` precedent).
- **Verification impact:** none on the verdict; this is reproduce-path repair
  only. `ReproduceRecord.repair_history` already exists and is rendered by the
  dashboard reproduce page (a list — multiple steps render fine).
- **Guard honesty:** the scripted installer must not become a false-passer —
  scenarios keep explicit `installer_steps` rc lists; argv recording is additive.

## Risks & Open Questions

- **R1 (standing, disclosed):** the slice-2 real-repo smoke never ran; field
  value is reasoned, not observed. Mitigation: CI stays synthetic; a real-repo
  smoke (alias-mapped repo, two-dep repo) remains a manual post-merge gate.
- **R2 — Loop edge semantics:** a retry failing with the *same* module re-detected
  is `install_failed` (the install did not take — stopping is the honest read);
  a retry failing with a *different* module that is already in the seen set is
  also `install_failed`. Both must be pinned by tests, not left to inference.
- **R3 — Seed long tail:** the table is curated by hand from common knowledge, no
  measured frequency; unknown names degrade verbatim. This is the honest limit,
  stated, not softened.
- **R4 — `RepairStep.detail` shape:** confirm `detail` accepts a structured value
  (dict/JSON string) at plan time — the C2 slices record rich detail, so a dict
  is expected; pin it with a test.
- **R5 — Multi-step rendering:** confirm the dashboard reproduce page renders a
  multi-step `repair_history` (it renders a list; verify with the e2e fixture
  or a snapshot test).
- **Open:** exact module placement (`verification/import_aliases.py` vs
  top-level) and whether the guard's scripted installer argv-recording needs a
  scenario-field change or can assert from `installer_steps` — resolved in
  tech-plan.

## Effort & Rollout

- **Effort estimate (rough):** small slice — one data file + one resolver module
  (a day), the bounded-loop restructure of `run_reproduction` (a day), guard +
  scenarios + baseline refreeze (a day), tests throughout. ~3 days of focused
  work, single owner (`aliz`).
- **Rollout:** CI green (guards unmoved or deliberately refrozen) → merge →
  CHANGELOG entry in the house "Honest scope" style → the M8 real-repo smoke as
  a manual post-merge gate. No dashboard, no CLI surface, no user-facing
  announcement beyond the CHANGELOG.

## Out of Scope

- Version pinning from a traced execution; venv isolation; non-Python
  environments (R/conda/apt).
- Import→package resolution via `importlib.metadata`, PyPI queries, or any
  network — deterministic table only.
- Figure/plot claims, PDF-table extraction, locator niceties (standing C8
  deferrals, unchanged).
- Changing `--allow-install` defaults or the CLI surface.
- Layer 1: nothing here authors workflows; this is reproduce-path self-heal
  inside the moat (guardrail check: clean).

## Data Model / Artifact Contracts

- **No new model, no signed-field change.** `RepairStep`, `Diagnosis`, `Patch`,
  `ReproduceRecord.repair_history`, and `RepairOutcome` are reused as-is.
- **New artifact:** `src/contig/data/import_aliases.tsv` (packaged data file).
- **Record semantics:** `Patch.operation["install"]` = resolved PyPI package;
  `RepairStep.detail` = original import name + mapping. Old bundles (empty
  `repair_history`) load unchanged.
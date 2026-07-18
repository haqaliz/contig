# PRD — Environment resurrection for `contig reproduce` (C8 slice 2)

**Slug:** `reproduce-env-resurrection`
**Branch:** `feat/reproduce-env-resurrection/aliz`
**Capability:** C8 (`docs/technical/CAPABILITY_ROADMAP.md:1047-1148`) — the slice-2 "environment
resurrection" deferred by the v0.40.0 walking skeleton and the v0.41.0 output-locator.
**Parent PRDs:** `docs/planning/reproduce-published-work/prd.md` (slice 1),
`docs/planning/reproduce-output-locator/prd.md` (slice 1.5).
**Status:** Interview complete (3 shaping decisions locked); pending prd-generator critique +
review-gate approval.

---

## Problem Statement

`contig reproduce` (slices 1 + 1.5) can only report a verdict on a repo whose script **actually
runs**. When a cloned public repo's script exits non-zero, every claim short-circuits to
`UNVERIFIED` (`verification/reproduce.py:319-342`) — an honest "I couldn't check," but a dead end
for the most common reason real repos fail to run: a **missing dependency**. `ModuleNotFoundError` /
`ImportError` + dependency installs are **~76% of reproduction failures**
(`CAPABILITY_ROADMAP.md:1121-1124`; `docs/planning/reproduce-published-work/prd.md:117`). The C8
roadmap names environment resurrection "the load-bearing piece" and scopes it as **slice 2 —
ImportError → install → retry** (`CAPABILITY_ROADMAP.md:1073,1121-1124`).

This slice turns the shipped self-heal discipline (C2) at the reproduce path: detect a missing
Python module from the run's own error output, install it (opt-in), retry once, and re-classify —
so an uncooperative-because-under-provisioned repo can still reach a real per-claim verdict instead
of a blanket `UNVERIFIED`.

**Evidence it's real:** the ~76% figure above; the reproducibility-crisis numbers behind C8 (~3.2%
of 27,271 biomedical notebooks reproduce; `CAPABILITY_ROADMAP.md:1107-1112`); slice 1's own
greenlight question — the go/no-go for investing in slice 2 is *does running an uncooperative repo
surface the `ModuleNotFoundError` catchably?* (`reproduce-published-work/prd.md:201`), which this
slice answers with a scripted-executor walking skeleton. On-thesis Layer 2 (run/self-heal/verify).

## Goals & Success Metrics

- **G1 — A missing-dependency failure can self-heal into a real verdict.** With `--allow-install`,
  a repo whose first run exits non-zero with `ModuleNotFoundError: No module named 'X'` triggers
  detect → install `X` → retry once; on a successful retry the claims classify normally.
  *Measured:* an engine + CLI test with a scripted executor (fail-then-succeed) and a scripted
  installer yields `REPRODUCED`/`DIVERGED` per claim (not blanket `UNVERIFIED`) and records the
  repair.
- **G2 — Honest degradation preserved on every unresolved path.** No module detected, install
  refused (flag off), install fails, or the retry still exits non-zero → all claims `UNVERIFIED`,
  the slice-1 contract, **never a false reproduce**. *Measured:* one fixture per path asserts
  all-`unverified` + the final exit code recorded.
- **G3 — Off by default; zero behavior change without the flag.** Without `--allow-install`,
  behavior is byte-identical to slice 1.5 — a non-zero exit is all-`unverified`, no install, no
  network, no environment mutation. *Measured:* the existing reproduce suite stays green after the
  seam migration; a "missing module, flag off" test asserts no installer call and all-`unverified`.
- **G4 — The engine can see the repo's error output.** The executor seam surfaces captured
  combined stdout+stderr so the detector has text to match. *Measured:* the seam type is
  `Callable[[list[str], Path], tuple[int, str]]` and the detector runs on the captured string.
- **G5 — The repair is recorded and reproducible.** A successful (or attempted) resurrection is
  captured on the `ReproduceRecord` and survives the signed bundle round-trip with pre-slice-2
  back-compat. *Measured:* `repair_history` is populated on a healed run and empty (default) on a
  legacy bundle that loads unchanged.
- **G6 — Bounded, deterministic, no new runtime dependency.** Exactly one install + one retry per
  run (provable termination); the suite runs offline with scripted seams; runtime deps unchanged
  (`pydantic`/`typer`/`cryptography`). *Measured:* a budget test proves the loop makes at most one
  install and one retry; `pyproject.toml` runtime deps unchanged.

**Non-metric goal:** keep the `Claim`/`ClaimResult` contract stable; the only model growth is an
additive `ReproduceRecord.repair_history`, so slice 3+ (multi-module, version pinning, TSV locator)
extend rather than reshape.

## User Personas & Scenarios

- **A — lone computational biologist / reviewer** (primary). Clones a public repo, runs its script,
  hits `ModuleNotFoundError`. Instead of hand-installing and re-running, passes `--allow-install`
  and gets Contig to resurrect the one missing dep and produce the per-claim verdict + signed
  record. The ~76%-of-failures case made turnkey.
- **D — biotech researcher / core facility.** Wants a defensible, signed artifact that *also records
  what had to be installed* to make the repo run — provenance of the resurrection, not just the
  numbers.

## Requirements

### Must-have (slice 2)

- **M1 — Executor seam surfaces captured output.** Change the reproduce command-executor from
  `Callable[[list[str], Path], int]` to `Callable[[list[str], Path], tuple[int, str]]` returning
  `(exit_code, combined_output)`. `runner.default_command_executor` captures combined stdout+stderr
  (`subprocess.run(..., stdout=PIPE, stderr=STDOUT, text=True)`) and returns `(returncode, output)`.
  The single call site is `reproduce.py:319`. **This is the `default_executor`/`IndexBuilder` seam —
  NOT** the Nextflow `Executor` alias at `runner.py:566`; do not conflate them.
- **M2 — Missing-module detector (pure, no I/O).** A new function
  `detect_missing_module(output: str) -> str | None` scans captured text for `no module named 'X'` /
  `modulenotfounderror` / `importerror` (case-insensitive, mirroring `detect._matching_lines`),
  extracts the module via a compiled regex, and returns the **top-level package** (`sklearn.utils` →
  `sklearn`). No match → `None`. Modeled on `detect.py:_matching_lines` (23-31) and
  `self_heal._parse_missing_index` (97-126). Deterministic, no filesystem.
- **M3 — Opt-in install-and-retry, bounded to one attempt.** `run_reproduction` gains
  `allow_install: bool = False` and `installer: Installer = default_installer`. On a non-zero first
  exit **and** `allow_install`: run `detect_missing_module`; if a module is found and not already
  attempted (a one-shot guard mirroring self-heal's `built_paths` set, `self_heal.py:966,891-902`),
  call `installer([...], repo)`; if install exits 0, re-invoke `executor` **once** and fall through
  to normal classification on the retried result. Any other outcome (flag off, no module, install
  non-zero, retry non-zero) keeps the existing all-`unverified` short-circuit
  (`reproduce.py:321-342`). **Exactly one install + one retry** — provable termination.
- **M4 — Installer seam (injected, fixed argv, injection-safe).** A new
  `Installer = Callable[[list[str], Path], int]` alias + `default_installer` in `runner.py`, directly
  mirroring `IndexBuilder`/`default_index_builder` (`runner.py:571,612-622`). `default_installer`
  runs a **fixed** argv `[sys.executable, "-m", "pip", "install", <module>]` in the repo cwd and
  returns the exit code. The module string (from repo output, M2) is validated against a safe
  charset (`^[A-Za-z0-9._-]+$`) before it ever reaches an argv — a non-matching token is treated as
  "no installable module" → `UNVERIFIED`. No shell, no interpolation, no user-supplied install
  string.
- **M5 — Verbatim install target (no alias map this slice).** The install target is the detected
  module name as-is. Import-name≠package-name mismatches (`cv2`→`opencv-python`,
  `sklearn`→`scikit-learn`) let the install fail → that run stays `UNVERIFIED` (honest). The curated
  alias map is an explicit later slice (Nice-to-have).
- **M6 — Repair recorded on the record; bundle round-trips.** Add
  `repair_history: list[RepairStep] = []` to `ReproduceRecord` (mirroring `RunRecord.repair_history`,
  reusing the existing `RepairStep`/`Diagnosis`/`Patch` models unchanged). A resurrection attempt
  appends one `RepairStep` (attempt, diagnosis, patch, outcome, detail). The default empty list keeps
  pre-slice-2 bundles loading (back-compat, mirroring the `QCKind`/locator additive pattern).
  `exit_code` reflects the **final (retried) run's** exit.
- **M7 — CLI `--allow-install` flag (default off).** `contig reproduce` gains
  `--allow-install/--no-allow-install` (default `False`), passed as `allow_install=` with
  `installer=default_installer` into `run_reproduction` (`cli.py:812-821`). Help text states plainly
  that it installs packages and reaches the network. Absent the flag, the command never installs,
  never hits the network, never mutates the environment.
- **M8 — Verdict / model / bundle reuse otherwise unchanged.** `classify`, `reduce_reproduction`,
  `resolve_pointer`, the locator path, `ClaimResult`, `write_reproduce_bundle`, signing,
  `render_reproduction`, and `--fail-on-diverged` are reused as-is. The only model change is the
  additive `ReproduceRecord.repair_history` (M6).

### Should-have

- **S1 — Message + surface quality.** When a resurrection happens, the per-run outcome names it
  ("installed `numpy`, retried, run completed" / "installed `numpy`, retried, still exit 1 →
  unverified"). `render_reproduction` surfaces a one-line repair note when `repair_history` is
  non-empty. A no-flag missing-module case says why it's `UNVERIFIED` and hints at `--allow-install`.
- **S2 — `RepairStep` FailureClass/Patch shape settled honestly.** The `Diagnosis.failure_class` for
  a missing Python module reuses an existing `FailureClass` literal if one fits, else adds
  `missing_dependency`; `Patch(kind="env", operation={"install": <module>}, ...)`. Exact literal
  chosen in tech-plan (see R2); keep it consistent with the detector corpus vocabulary.

### Nice-to-have (explicitly later slices)

- **Curated import→package alias map** (`cv2`→`opencv-python`, …) — resolves common M5 mismatches.
- **Iterative multi-module resolution** (install one, hit the next missing import, repeat, still
  bounded) — this slice does single install + single retry only.
- **Version pinning from a traced execution** (install the *right* version, not just the module) —
  the "traced real execution / observed versions" piece of C8 (`CAPABILITY_ROADMAP.md:1121-1124`).
- **Non-Python environments** (R, conda, apt), TSV/CSV locator, paper-parsing, figure claims, remote
  `<doi|url>`, dashboard card, C6 eval fold-in — unchanged from prior deferral lists.

## Technical Considerations

- **The change is localized and mirrors shipped idioms.** New: a pure `detect_missing_module`; an
  `Installer` alias + `default_installer` in `runner.py` (copy of `default_index_builder`); a bounded
  install-retry wrap around `reproduce.py:319-342`; an additive `ReproduceRecord.repair_history`; a
  CLI flag. Everything downstream of "observed value" is untouched.
- **Reuses the C2 self-heal seam pattern exactly:** keyword-only injected `Callable[..., int]` with a
  real default (`IndexBuilder`), a `set`/one-shot already-attempted guard for provable termination
  (`built_paths`), evidence-text matching for detection (`_matching_lines`), and `RepairStep`
  recording (`_record_attempt`). This is why the slice fits: it is the reproduce-path instance of
  machinery already shipped and tested for the Nextflow path.
- **Reproducibility/verification impact:** widens *which repos* can reach a signed verdict (those a
  single dep-install away from running) **without weakening honesty** — `UNVERIFIED`-on-any-doubt is
  preserved on every unresolved branch, and the resurrection itself is recorded in the signed bundle
  (provenance of what was installed).
- **Safety posture:** install is opt-in (M7), argv is fixed and charset-validated (M4), and the
  module name derives from the **repo's own error text**, not user free-text. Running a third-party
  repo's script already executes arbitrary code, so installing its self-declared missing import under
  an explicit flag does not widen the trust surface materially — but the flag keeps the *environment
  mutation + network* side effect from ever being a surprise.
- **Determinism/CI:** no real repo, no network, no real pip. Tests inject a scripted executor
  (returns `(exit, output)`, fail-then-succeed) and a scripted installer (records the call, returns a
  scripted code), mirroring `tests/test_reproduce.py:_fake_executor` and self-heal's `index_builder`
  fakes.

## Data Model / Artifact Contracts

- **Executor seam:** `Callable[[list[str], Path], tuple[int, str]]` — `(exit_code, combined_output)`.
- **Installer seam:** `Installer = Callable[[list[str], Path], int]` — argv + repo cwd → exit code.
- **`ReproduceRecord` (extended, additive):**
  ```jsonc
  {
    "reproduce_id": "rp_…", "repo": "…", "run_command": "python fig2.py",
    "claims_sha256": "…", "claim_results": [ … ], "exit_code": 0,
    "created_at": "…", "interpreter": null, "tool": "contig",
    "repair_history": [                         // NEW, default []
      {"attempt": 1,
       "diagnosis": {"failure_class": "missing_dependency", "root_cause": "…",
                     "evidence": ["ModuleNotFoundError: No module named 'numpy'"],
                     "confidence": "…"},
       "patch": {"kind": "env", "operation": {"install": "numpy"}, "rationale": "…",
                 "risk": "…", "expected_signal": "…"},
       "outcome": "installed_and_retried", "detail": "installed numpy; retry exit 0"}
    ]
  }
  ```
  Pre-slice-2 bundles (no `repair_history`) load with the field defaulting to `[]`.
- **CLI:** `--allow-install/--no-allow-install` (default `False`).

## Risks & Open Questions

- **R1 — Seam migration touches every reproduce test fake.** Changing the executor return to
  `(int, str)` means the shared `_fake_executor` (`test_reproduce.py:281-292`) and all callers must
  return a tuple. Mechanical, but must land in one pass to keep the suite green (G3). *Mitigation:*
  update the shared fake once; the closure shape is unchanged apart from the return.
- **R2 — `FailureClass` vocabulary.** There may be no existing `FailureClass` literal for "missing
  Python module." Reuse the closest (e.g. an env/dependency class) or add `missing_dependency`.
  Adding a literal touches the detector-corpus vocabulary and possibly the C6 eval-guard baseline.
  *Resolve in tech-plan*; keep it a single, deliberate choice, and prefer reuse if a clean fit
  exists.
- **R3 — "Installed but still UNVERIFIED" is common on real repos.** Name≠package mismatches (M5),
  a second missing import after the first install (single-retry cap), or a non-import failure all
  leave the run `UNVERIFIED`. Honest framing: the win is "resurrects a repo one PyPI-name-matching
  dep away from running," not "runs any repo." The post-merge smoke (below) measures this on a real
  repo and is the go/no-go for slice 3 (alias map / iterative).
- **R4 — Which environment does `default_installer` mutate?** It installs into `sys.executable`'s
  environment — the same interpreter running the repo's `python …` command in the common case, but
  not guaranteed if the repo's `--run` invokes a different interpreter. This slice does not manage or
  isolate environments (no venv creation). *Flagged as an accepted limit*; venv isolation is a later
  slice. The injected seam means CI never exercises the real target.
- **R5 — Combined stdout+stderr vs separate streams.** Merging (STDOUT+STDERR) is simplest and
  matches `default_index_builder`; a repo that prints its results to stdout and its traceback to
  stderr still works because detection only scans for the import-error needles. Confirm merge is
  acceptable (it is for detection; the results file, not stdout, carries values).

## Out of Scope (explicit)

- **Alias map, iterative multi-module resolution, version pinning, venv/conda/R environment
  management** — later slices (Nice-to-have).
- **Any judgement on the paper's conclusions** — computation-vs-numbers only.
- **TSV/CSV locator, paper-parsing, figures/plots, remote fetch, dashboard card, C6 eval fold-in** —
  unchanged from the slice-1/1.5 deferral lists.
- **Auto-install without the flag** — rejected by design this slice (opt-in only).

## Post-merge validation (not a CI test)

Per the slice-1/1.5 greenlight discipline (`reproduce-published-work/prd.md:199-204`;
`reproduce-output-locator/prd.md:181-187`): after merge, run `contig reproduce --allow-install`
against **≥1 real cloned public repo** whose first run fails on a missing PyPI dependency whose
import name matches its package name, with a hand-written claims file, and confirm the resurrection
fires and the per-claim verdict is sensible. This is the honest proof env-resurrection earns its
keep and the go/no-go signal for slice 3 (alias map / iterative). Manual, offline-optional, not
gated in CI.

## Guardrail check (`CLAUDE.md`)

Layer 2 only (self-heal/run/verify a repo's execution; never NL→workflow, never a conclusions
verdict) ✅ · Moat = self-heal + verification/reproducibility infra + corpus (records the repair for
future C6 fold-in) ✅ · Gets better as base models improve (module/version diagnosis in later
slices) ✅ · Founder's edge / stdlib-only (injected installer, no new runtime dep) ✅ · No raw-data
egress (only hashes + claim diffs + the installed-package name leave the box; install is opt-in) ✅ ·
Test-first ✅.

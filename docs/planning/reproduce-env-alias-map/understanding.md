# Understanding — reproduce-env-alias-map

Phase 2 dig note (contig-begin-fast). Verified against the code in this worktree
(HEAD b0d2d4a, v0.55.1), not from memory.

## What the work is really asking

`contig reproduce --allow-install` (C8 env resurrection, slice 2) resurrects a
third-party repo one missing Python dependency from running: detect
`ModuleNotFoundError` → `pip install <module>` → retry once. Two known gaps, both
named in the slice-2 PRD as the explicit next slice (`docs/planning/reproduce-env-resurrection/prd.md:110-113,143-145`):

1. **Import-name ≠ package-name.** The install target is the detected module token
   verbatim (`cv2` → `pip install cv2`, which fails; should be `opencv-python`). The
   PRD's M5 says: "Import-name≠package-name mismatches (`cv2`→`opencv-python`,
   `sklearn`→`scikit-learn`) let the install fail → that run stays `UNVERIFIED`
   (honest). The curated alias map is an explicit later slice."
2. **Single-install cap.** One install + one retry only; a second missing import
   after the first install is not chased (`reproduce.py:865-871,1248-1250`; pinned by
   `test_run_reproduction_does_not_chase_a_second_missing_module`,
   `tests/test_reproduce_env_resurrection.py:221-236`).

The work: a curated import→package alias data file + loud loader (the
`contig_aliases.tsv` precedent, named in the brief), alias-aware install target,
and a bounded iterative resolution loop with provable termination — all under the
existing honest contract (unknown names install verbatim; any failure stays
UNVERIFIED, never a false reproduce).

## Code map (all verified file:line)

- **Install branch:** `verification/reproduce.py:1217-1279` inside
  `run_reproduction` (sig :838-851; keyword-only `allow_install: bool = False,
  installer: Installer = default_installer`).
  - `module = detect_missing_module(run_output)` (:1218) → `Diagnosis(
    failure_class="missing_dependency", confidence=0.8)` (:1220-1225) →
    `Patch(kind="env", operation={"install": module})` (:1226-1232) →
    `install_rc = installer(_pip_install_argv(module), repo_path)` (:1233).
  - Outcomes: `install_failed` (patch_applied=False, :1234-1246), `retry_failed`
    (patch_applied=True, :1252-1266), `installed_and_retried` (patch_applied=True,
    :1267-1277). `module is None` → nothing recorded, honest short-circuit
    (:1278-1279).
  - **The alias lookup goes between `detect_missing_module` and
    `_pip_install_argv`** (:1233) — one line in the install path.
- **`detect_missing_module`:** `reproduce.py:54-68` — regex
  `No module named 'X'` (:43), top-level split `.split(".")[0]` (:65) —
  `sklearn.utils` → `sklearn` — charset gate `_SAFE_PACKAGE_TOKEN_RE` (:44,66-67),
  case-preserving capture.
- **Installer seam:** `runner.py` — `Installer = Callable[[list[str], Path], int]`
  (:729), `_pip_install_argv(module)` → `[sys.executable, "-m", "pip", "install",
  <module>]` fixed argv, no shell (:1082-1084), `default_installer` (:1087-1094).
- **Record:** `ReproduceRecord.repair_history: list[RepairStep]` (models.py:828);
  `RepairOutcome = Literal["none", "installed_and_retried", "install_failed",
  "retry_failed"]` (models.py:845-847); `FailureClass` includes `missing_dependency`
  (models.py:262-274). A new outcome literal (if needed) is a `models.py` change —
  **no signed-field change** (RepairOutcome is a Literal, additive).
- **CLI:** `--allow-install/--no-allow-install` (cli.py:927-935); wired at
  cli.py:1179-1191.
- **Reproduce-guard:** scripted installer `reproduce_guard.py:152-157` pops
  `scenario.installer_steps` rc values and — importantly — **never inspects `cmd`
  (argv), only rc**; no steps → rc 1. Scenarios: `env-resurrection-heal` (line 11:
  `installer_steps: [0]`), `install-fail-giveup` (line 12: `installer_steps: [1]`).
  Scorer matches `record.repair_history[-1].outcome` (reproduce_guard.py:218-231).
  A multi-install scenario works by adding more rc values; argv-awareness in the
  scripted installer is a question for the PRD (the unit-test helpers already record
  argv: `tests/test_reproduce_env_resurrection.py:101-111`).
- **Tests:** `tests/test_reproduce_env_resurrection.py` (slice-2 home, `_Scripted
  Installer` records every `(cmd, cwd)`), `tests/test_reproduce.py`, `tests/test_
  reproduce_guard_driver.py`, `tests/test_cli_reproduce.py`, `tests/test_runner.py`
  (`_pip_install_argv` fixed argv incl. scikit-learn :28-43).

## Precedent to reuse (the `contig_aliases.tsv` pattern)

- Data file `src/contig/data/contig_aliases.tsv`: `#` comments, no header, exactly
  two tab-separated fields per row.
- Loader `src/contig/contig_aliases.py`: `_DATA_PATH = Path(__file__).parent /
  "data" / "contig_aliases.tsv"` (:29, plain pathlib — ships via hatchling
  packages=[src/contig]); `_build_alias_map(lines)` takes an iterable of lines so it
  is unit-testable on synthetic input (:32-84); module-level `_ALIAS_MAP` built at
  import (:94); public `alias_group(name)`.
- **Fail-loud contract:** malformed row (≠2 non-empty tab fields) → `ValueError`
  (:62-66); conflicting duplicate → `ValueError` (:75-82); exact duplicate silently
  deduped (:70-72); missing file propagates `FileNotFoundError` (:87-91).
- Tests: `tests/test_contig_aliases.py` — packaged file exercised through the public
  API, synthetic injection into `_build_alias_map`, `pytest.raises(ValueError,
  match=...)` for loud-loader cases.
- No duplicate risk: no import→package mapping exists anywhere in `src/` (verified
  by grep; `importlib.metadata` is only used for Contig's own version).

## Design questions for the PRD (from the dig)

1. **Iteration budget.** Max installs per run (2? 3?) and the termination rule.
   Proposal: installs ≤ 2-3, and a "seen modules" set so re-detecting a module that
   was already installed is treated as install-failure (stop), never re-chased — the
   same-module case is the loop-shaped failure.
2. **What the record says.** Per-attempt `RepairStep` (multiple steps in
   `repair_history`) vs one step with a detail summary. Multiple steps is the
   truthful shape; the guard compares `repair_history[-1].outcome`, so the last step
   wins. Decide whether `operation={"install": ...}` records the alias-resolved
   package name (it should — the record states what was actually installed; the
   alias mapping can ride in `detail`).
3. **Alias lookup normalization.** Keys lowercase, lookup on `module.lower()`? The
   detector is case-preserving (`"Pandas"` → `"Pandas"`); PyPI names are
   case-insensitive. Decide and pin.
4. **Guard extension.** Scripted installer never inspects argv; a multi-install
   scenario only needs more `installer_steps` rc values, but asserting the
   alias-mapped target in the guard may need argv-awareness or is left to unit
   tests. Don't weaken the mutation-control pin.
5. **Scope of the seed map.** How many curated rows ship (a focused seed: cv2,
   sklearn, PIL, yaml, pandas?, numpy (name matches), scipy, matplotlib, seaborn,
   statsmodels, scikit-learn, biopython, pysam, h5py, anndata...)? Long tail is
   acknowledged — unknown names stay verbatim.

## Open contradictions / flags

- None between brief and code. The brief's premise (single install + one retry,
  verbatim target) matches the code exactly.
- The slice-2 real-repo smoke (PRD R3, the alias-map go/no-go) has never been run —
  the CHANGELOG v0.55.x honesty notes say the manual gate carries a never-run
  checklist. The slice proceeds on the honest framing: reasoned, not observed;
  CI stays synthetic; a real-repo smoke remains a manual post-merge gate.
- Layer-2 check: this is pure reproduce/self-heal hardening inside the moat. No
  Layer-1 drift.
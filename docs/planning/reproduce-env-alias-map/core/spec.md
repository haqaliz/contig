# Spec — reproduce-env-alias-map / core

Single-aspect slice: everything in `docs/planning/reproduce-env-alias-map/prd.md`
lands in this one aspect (the feature is one cohesive change to the reproduce
install path + its guard).

## Problem slice

`contig reproduce --allow-install` installs the detected module token verbatim and
chases at most one missing module. Two gaps: import-name≠package-name mismatches
(`cv2`→`opencv-python`) fail the install, and a second missing module is never
chased. Both were named as the explicit next slice in the env-resurrection PRD.

## In-scope

- `src/contig/data/import_aliases.tsv` (~15 hand-curated rows) + loud loader +
  pure `package_for_import(name)` (the `contig_aliases.py` pattern).
- Alias-aware install target: `operation={"install": <resolved package>}`; detail
  string names import + package; unknown names verbatim.
- Bounded iterative loop: ≤ 2 installs, per-run seen-set, provable termination.
- One `RepairStep` per install attempt (`attempt` increments); last step wins for
  the guard; no new outcome literal, no signature break.
- Guard: scripted installer argv assertions + 3 new frozen scenarios + deliberate
  baseline refreeze (composition change disclosed).
- Docstrings, CHANGELOG, roadmap marker updates.

## Out-of-scope boundaries

- Version pinning, venv isolation, non-Python envs, network/PyPI resolution.
- `--allow-install` defaults, CLI surface, installer seam signature.
- Dashboard code changes (verify multi-step rendering only).

## Acceptance criteria (testable)

1. `package_for_import("cv2") == "opencv-python"`; `package_for_import("numpy") ==
   "numpy"` (verbatim); lookup case-insensitive.
2. A `cv2`-missing run installs `opencv-python` (asserted on recorded argv and
   `Patch.operation`), with `RepairStep.detail` naming both names.
3. Two missing modules are chased in ≤ 2 installs; a third detection is not
   installed; an already-installed module is never re-installed (seen-set).
4. Every give-up (install failure, retry failure, no module, seen re-detection)
   keeps the run `UNVERIFIED`, never a false reproduce.
5. `reproduce-guard` outcome-match stays 1.0 on all scenarios post-refreeze; the
   known-miss stays the only miss; mutation-control pins still flip on deliberate
   mismatch.
6. Full suite green; stdlib-only; `RepairOutcome`/signed fields unchanged.

## Dependencies & sequencing

1. Alias table + resolver (independent, testable in isolation).
2. `run_reproduction` loop restructure (consumes 1).
3. Guard scenarios + refreeze (consumes 2).
4. Docs + CHANGELOG (consumes all).

## Open questions / risks

- The slice-2 real-repo smoke never ran → field value reasoned, not observed;
  M8 revisit trigger committed in the PRD.
- `RepairStep.detail` is `str | None` — mapping rides in the detail string.
- Dashboard multi-step rendering: verify by reading the component, no change
  expected.
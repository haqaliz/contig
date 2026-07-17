# Understanding — feat/reproduce-published-work (C8, first slice)

Synthesis of the Phase 2 dig (three graphify-first mapping agents). All paths under
`src/contig/` in the worktree.

## What the work is really asking

Open capability **C8** — point the shipped run→self-heal→verify→reproduce engine at a
*third-party* repo and report, per stated numeric claim, whether the computation
reproduces it (`REPRODUCED` / `WITHIN-TOLERANCE` / `DIVERGED` / `UNVERIFIED`), ending in a
signed, re-runnable bundle. First slice must be **narrow**, test-first, no network.

The brief bundles two substantial pieces. The dig confirms they are separable:

1. **The `contig reproduce` surface + per-claim verdict** (walking skeleton): run a repo's
   script, read an explicit claims file, compare each regenerated scalar to its claim within
   tolerance, emit a per-claim verdict, write a signed bundle. Fully deterministic/testable.
2. **Environment resurrection** (the roadmap's "load-bearing" piece): when the script fails
   with `ModuleNotFoundError`/`ImportError`, self-heal by installing the dep and retry —
   reusing C2's self-heal seam pattern. This is the *hard, open* piece.

**Recommended first-slice boundary: build (1) end-to-end and defer (2).** A run whose env is
unresolved degrades **honestly to `UNVERIFIED`** — the honesty contract holds without the hard
piece. (2) becomes slice 2, converting some UNVERIFIEDs into REPRODUCED. This is the classic
narrow walking skeleton and matches the contig-next caveat ("keep the first slice narrow;
env-resurrection is the hard open piece"). To settle with the user in the interview.

## Affected areas (map)

**CLI / bundle / signing (reuse, low risk):**
- `cli.py:129` single flat Typer `app`; commands are `@app.command()` functions. Mirror `show`
  (`cli.py:698`) / `rerun` (`cli.py:640`) — positional `Argument` + `Option`s, load→render→
  `raise typer.Exit(code=1)` on error. `run`/`rerun` funnel into `_dispatch_run` (`cli.py:340`).
- `RunRecord` `models.py:316`; bundle dir `runs/<id>/` with `run_record.json` + `launch.json`
  (`LaunchManifest` `models.py:394`) + optional `signature.json`. `write_bundle` `bundle.py:26`
  is called at `_finalize` and **auto-signs** when `CONTIG_SIGNING_KEY` is set
  (`bundle.py:41`, `signing.py`). Verify via `_signature_status` `cli.py:1306`. → *A reproduce
  run that ends in `write_bundle` gets the "signed, re-runnable bundle" for free.*
- Tests: `tests/test_cli.py`, `CliRunner`, `_fake_run_executor` + `monkeypatch.setattr(
  "contig.cli.default_executor", ...)`, mirror `test_rerun_dispatches_identical_run_with_new_id`.
  No `conftest.py`; use `tmp_path`.

**Verdict / claim compare (the new surface):**
- **Reusable:** `benchmark._relative_delta` (`benchmark.py:195`) — `abs(run-ref)/abs(ref)`,
  abs-fallback when ref==0; `within = delta <= tolerance`, default rel tol `0.1`
  (`cli.py:1697`). A genuine scalar tolerance compare, directly reusable for a per-claim compare
  (claim = `reference_value`, regenerated = `run_value`).
- **New model needed:** `QCStatus`/`Verdict` = `pass|warn|fail|unverified` (`models.py:55`)
  does **not** map onto the C8 4-value vocabulary. `QCResult` (`models.py:67`) has no way to
  distinguish "exact" from "within tolerance." Cleanest path = a small new `ClaimResult` model
  + `ClaimStatus` enum + a `reduce`-style function mirroring `overall_verdict` (`models.py:85`,
  whose fail>warn>pass reduction + `informational` exclusion is a good template). No `claim`
  model exists today — C8 introduces the first.

**Self-heal (env-resurrection — slice 2, mapped now so the skeleton doesn't box it out):**
- `self_heal_run` loop `self_heal.py:925`. Add `missing_python_module` to `FailureClass`
  (`models.py:262`; `_VALID_FAILURE_CLASSES` `detect.py:424` auto-syncs). Add a detector branch
  in `diagnose_failure` (`detect.py:39`) *before* the `tool_crash` fallback (`detect.py:341`),
  matching `no module named`/`modulenotfounderror`/`importerror`. Add a `propose_patches` block
  (`repair.py:14`). Add a `DepInstaller = Callable[[argv, cwd], int]` seam parallel to
  `IndexBuilder` (`runner.py:571`), threaded through `self_heal_run` + `_apply_patch_and_maybe_
  build` (`self_heal.py:822`) via `operation["install_dependency"]`, bounded once-per-package by
  `built_paths` (`self_heal.py:966`). Test via scripted installer, mirroring `heal.py`'s
  `_scripted_index_builder` (`heal.py:63`) + `heal_scenarios.jsonl`. No network in CI.

## Contradiction to flag (dig vs roadmap) — IMPORTANT

`CAPABILITY_ROADMAP.md` C8 (~line 1077) promises to reuse "the existing **float-tolerance /
plot-hash / seed-aware** diffing." The dig verified against the code:
- **float-tolerance: real & reusable** (`benchmark._relative_delta`). ✅
- **plot-hash: does not exist anywhere.** There is no image/plot hashing in the repo, and the
  runtime dep set is deliberately minimal — `pydantic`, `typer`, `cryptography` only
  (`pyproject.toml:30`), stdlib-first everywhere. Adding perceptual-image-hash (Pillow/imagehash)
  would **break the no-new-dependency contract**. ❌
- **seed-aware diffing: does not exist** as a named mechanism (closest is the tolerance band
  absorbing run-to-run noise). ⚠️

**Consequence for scope:** the first slice must be **scalar numeric claims only**. Figure/plot
and table-cell claims are **out of scope** until a deliberate dependency decision is made — this
is a hard technical constraint, not a preference. Record it in the PRD as a non-goal.

## Guardrail check

- **Layer 2 only:** ✅ verify-and-reproduce; run/self-heal/compare, never NL→workflow authoring,
  never a judgement on the paper's conclusions. Env-resurrection is self-heal (Layer 2), not
  pipeline authoring. Paper-parsing (a potential Layer-1-adjacent parse) is **deferred** — we take
  an explicit claims file.
- **No raw-data egress:** ✅ runs on user/CI compute; only hashes + claim diffs in the bundle.
- **Founder's edge / stdlib-only:** ✅ pure-Python scalar math, no new deps — *provided we hold
  the scalar-only line above.*
- **Test-first:** ✅ synthetic repo fixtures, scripted executor/installer, no network, no real
  nf-core.

## Open questions for the interview

1. **First-slice boundary:** walking skeleton (surface + scalar claim verdict, env-resurrection
   deferred to UNVERIFIED) vs env-resurrection-first vs both-thin. *(Recommend: walking skeleton.)*
2. **Claims file format:** propose a JSON list of `{id, value, tolerance?}` (+ optional
   `kind:"scalar"`). Confirm.
3. **How the script is specified & where the regenerated value comes from:** `--run "<cmd>"`
   explicit command vs a repo convention; regenerated value from script-emitted JSON keyed by
   claim id, or an output file.
4. **REPRODUCED vs WITHIN-TOLERANCE threshold:** define "exact" for floats (byte-equal vs a tight
   epsilon like 1e-9) so the two states are well-defined.
5. **rerun-ability:** reuse `LaunchManifest` or a parallel `reproduce`-specific manifest?

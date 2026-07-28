# Task 4 report — Phase 4: CLI containment pre-check + help (C8 slice 1.5)

**Commit:** `16213e6` — `feat(cli): refuse a repo-escaping locator 'from' pre-run; clarify --results [C8 slice 1.5]`

## What changed

`src/contig/cli.py`, `reproduce` command:

- `src/contig/cli.py:717-723` — `--results` help text now reads: "Repo-relative JSON the script
  writes: {claim_id: value}; the fallback for claims without a 'from'/'path' locator".
- `src/contig/cli.py:788-802` — new containment pre-check, inserted after the `--tolerance`
  re-default block and before `claims_sha256`/`run_reproduction`. For each claim with a non-`None`
  `locator`, resolves `(repo_path / claim.locator.source).resolve()` and calls
  `.relative_to(repo_path.resolve())` inside `try/except ValueError`; on escape, echoes
  `"locator 'from' path escapes the repo: {claim.locator.source}"` to stderr and raises
  `typer.Exit(code=1)` — mirrors the existing `--results` guard at `cli.py:748-756` exactly, runs
  strictly before `run_reproduction`/`write_reproduce_bundle`, so no bundle/record is ever written
  for a refused claim. The pre-existing `--results` guard is untouched.

`tests/test_cli_reproduce.py` — 3 new tests added (mirroring the existing escape-test pattern at
`:285`/`:312`), inserted before `test_reproduce_writes_signed_bundle_when_signing_key_set`:

- `test_reproduce_escaping_locator_from_errors_and_writes_no_record` — claim with
  `"from": "../secret.json"` → `exit_code != 0`, no `reproduce_record.json` under `runs_dir`.
- `test_reproduce_absolute_locator_from_errors_and_writes_no_record` — claim with
  `"from": "/etc/passwd"` → `exit_code != 0`, no record.
- `test_reproduce_located_claim_end_to_end_reports_verdict` — fake `default_command_executor`
  writes `out/summary.json` (`{"model": {"auc": 0.9}}`) into the run cwd; claims file has
  `{"from": "out/summary.json", "path": "$.model.auc", "value": 0.9}` → `exit_code == 0`,
  `"REPRODUCED"` in output, a `reproduce_record.json` is written.

## TDD evidence

RED (pre-GREEN run of the new tests only, before touching `cli.py`):
```
uv run pytest tests/test_cli_reproduce.py -q
```
2 failures: `test_reproduce_escaping_locator_from_errors_and_writes_no_record` and
`test_reproduce_absolute_locator_from_errors_and_writes_no_record` both asserted
`result.exit_code != 0` and got `0` — the engine's own defense-in-depth marks the claim
`unverified` but the CLI command still completes and exits 0. The third new test (happy-path
end-to-end) passed immediately since Phase 3's engine already supports located claims — expected,
it's a regression-style acceptance check on already-shipped behavior, not a RED case.

GREEN (after the `cli.py` pre-check):
```
uv run pytest tests/test_cli_reproduce.py -q
```
```
................
16 passed in 0.45s
```

Full suite:
```
uv run pytest -q
```
Tail (via non-`-q` rerun to get the summary line, since `-q` piped through this environment's
tooling truncated the final summary line — dot progress was identical either way):
```
1727 passed, 1 skipped in 13.27s
```

## Concerns

- None functional. One environment quirk noted for the record: `uv run pytest -q | tail` in this
  sandbox drops pytest's final summary line (dots/percentages print fine); running without `-q`
  reproduces the summary reliably. Not a code issue — just a note for whoever reruns this.
- Two unrelated pre-existing modified files (`docs/planning/_card/issue.md`,
  `docs/planning/_card/understanding.md`) were present in the worktree before this task started and
  were deliberately left uncommitted/untouched, out of scope for Phase 4.

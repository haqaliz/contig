# Task 2 report — Phase 2: `Locator` model + `Claim`/`load_claims` extension

**Commit:** `70a9b29` — `feat(reproduce): optional per-claim output-locator on Claim + load_claims validation [C8 slice 1.5]`

## What was added

`src/contig/verification/reproduce.py`:

- `Locator` frozen dataclass (`:103-113`): fields `source: str` (the claims-file `"from"` key —
  named `source` internally since `from` is a Python keyword) and `path: str` (the dotted+`[n]`
  pointer, walked later by the already-committed `resolve_pointer`).
- `Claim.locator: Locator | None = None` (`:117-129`), appended as the last field so existing
  positional/keyword construction (`Claim(id=..., value=..., tolerance=...)`) is unaffected.
- `load_claims` (`:165-190`), after the existing `tolerance` validation and before
  `claims.append(...)`: validates `"from"`/`"path"` are both present or both absent
  (`ClaimsError` if only one is set), and when present, both must be non-empty (post-`.strip()`)
  strings (`ClaimsError` otherwise). Builds `Locator(source=raw_from, path=raw_path)` and passes
  `locator=locator` into `Claim(...)`. No filesystem/containment check — pure parsing/validation,
  repo-agnostic, per the Phase-2 constraint (that's Phase 4's CLI job).

## New tests

Added to `tests/test_reproduce.py`, in a new `load_claims() -- output locator ("from" + "path")`
group right before the `run_reproduction()` section (`:194-274` in the final file):

- `test_load_claims_with_from_and_path_attaches_locator` — both fields set →
  `claim.locator == Locator("out/x.json", "$.a")`.
- `test_load_claims_slice1_claim_has_no_locator` — neither field → `claim.locator is None`
  (back-compat, AC9).
- `test_load_claims_rejects_from_without_path` / `_rejects_path_without_from` — all-or-nothing
  violation → `ClaimsError`.
- `test_load_claims_rejects_non_string_from` / `_rejects_non_string_path` — non-string value →
  `ClaimsError`.
- `test_load_claims_rejects_empty_from` / `_rejects_empty_path` — whitespace-only / empty string
  → `ClaimsError`.

Also added `Locator` to the `contig.verification.reproduce` import block at the top of the file.

## TDD sequence

1. RED: wrote the 8 tests above + the `Locator` import; confirmed failure via
   `uv run pytest tests/test_reproduce.py -q` → `ImportError: cannot import name 'Locator'`
   (collection error, as expected — `Locator` did not exist yet).
2. GREEN: added `Locator`, `Claim.locator`, and the `load_claims` validation block; reran.
3. REFACTOR: none needed beyond the initial implementation — kept the reference shape from the
   plan, only tightened docstrings.

## Validation (final output)

```
$ uv run pytest tests/test_reproduce.py -q
....................................                                     [100%]
```
(36 passed — 28 pre-existing + 8 new.)

```
$ uv run pytest tests/test_reproduce_locator.py tests/test_cli_reproduce.py \
               tests/test_reproduce_models.py tests/test_reproduce_bundle.py -q
........................................................................ [ 84%]
.............                                                            [100%]
```
(87 passed, all green.)

Also ran the full repo suite as a sanity check: `uv run pytest -q` → all green (1 pre-existing
skip, no failures).

## Concerns

- None functional. `Locator` is exported and importable from `contig.verification.reproduce` as
  required.
- Two unrelated, pre-existing working-tree modifications were present before this task started
  (`docs/planning/_card/issue.md`, `docs/planning/_card/understanding.md`) — left untouched and
  unstaged; not part of this commit, since they're outside Phase 2's scope (task-1 planning
  artifacts, not reproduce.py/tests).
- Did not touch `run_reproduction`, `classify`, `models.py`, or the CLI, per the task boundary.

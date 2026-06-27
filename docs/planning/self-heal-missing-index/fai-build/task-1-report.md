# Task 1 Report — IndexBuilder seam + pure parse helpers

**Date:** 2026-06-27
**Branch:** feat/self-heal-missing-index/aliz (worktree)
**Phase:** Phase 1 of `fai-build` aspect

## What was done

### Files changed

**`src/contig/runner.py`**
- Added `IndexBuilder = Callable[[list[str], Path], int]` type alias beside `Executor` (~line 77), with a comment mirroring the `Executor` comment style.
- Added `default_index_builder(cmd: list[str], cwd: Path) -> int` function after `default_executor` (~line 110). Calls `subprocess.run(cmd, cwd=cwd, check=False)` and returns the returncode. Mirrors `default_executor`'s minimal structure.

**`src/contig/self_heal.py`**
- Added `Diagnosis` to the `from contig.models import ...` line.
- Added module-level compiled regex `_FAI_TOKEN_RE = re.compile(r"\S+\.fai")` after the constants block.
- Added `_parse_missing_fai(diagnosis: Diagnosis) -> str | None` — scans `diagnosis.evidence` lines for the first whitespace-free token ending in `.fai`; returns it verbatim or `None`. Pure, no I/O.
- Added `_fai_build_command(fai_path: str) -> list[str]` — strips the trailing `.fai` suffix via `str.removesuffix` and returns `["samtools", "faidx", <fasta>]`. Pure, no I/O.

**`tests/test_runner.py`**
- Added `test_default_index_builder_returns_zero_for_success` — uses `[sys.executable, "-c", ""]` for portability; asserts return 0.
- Added `test_default_index_builder_returns_nonzero_for_failure` — uses `[sys.executable, "-c", "import sys; sys.exit(3)"]`; asserts return 3.

**`tests/test_self_heal.py`**
- Added `test_parse_missing_fai_returns_relative_token` — canonical `fai_load` evidence line → `"reference.fasta.fai"`.
- Added `test_parse_missing_fai_returns_absolute_token` — `/data/ref.fa.fai` token → returned verbatim.
- Added `test_parse_missing_fai_returns_none_when_no_fai_token` — evidence with no `.fai` token → `None`.
- Added `test_fai_build_command_strips_fai_suffix` — `"reference.fasta.fai"` → `["samtools", "faidx", "reference.fasta"]`.
- Added `test_fai_build_command_strips_fai_suffix_absolute` — `"/data/ref.fa.fai"` → `["samtools", "faidx", "/data/ref.fa"]`.

### TDD sequence

RED → GREEN → REFACTOR followed strictly:
1. Tests written first and confirmed failing (ImportError) before any production code.
2. Production code added to make tests pass.
3. No separate refactor step needed — helpers were written small and pure from the start.

## Test commands and output

```
uv run pytest tests/test_self_heal.py -q -k "parse or build_command"
# 5 passed in 0.XXs

uv run pytest tests/test_runner.py -q -k index_builder
# 2 passed in 0.XXs

uv run pytest -q
# 783 passed, 1 skipped in 9.97s
```

Full suite was 776 passed, 1 skipped before this task; now 783 passed, 1 skipped (+7 new tests, no regressions).

## Concerns

None. The implementation is straightforward:
- `str.removesuffix` (Python 3.9+) is used for the `.fai` strip — clean and explicit.
- The regex `\S+\.fai` handles both relative and absolute paths correctly.
- `Diagnosis` is now explicitly imported in `self_heal.py` (it was previously used only via `diagnose_failure`'s return value downstream); the import is clean with `from __future__ import annotations` already in place.
- Phase 2 (loop wiring) can proceed directly — the seam and parse helpers are fully in place.

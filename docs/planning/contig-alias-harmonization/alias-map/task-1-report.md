# Task 1 report: contig alias equivalence table (Phase 1)

## What was built

Phase 1 of `contig-alias-harmonization`: a standalone, data-driven alias
equivalence lookup. No existing module was modified or consumed yet — this
phase is purely the data table + loader, per the task brief.

Files created:

1. **`src/contig/data/contig_aliases.tsv`** — bundled TSV seed data.
   - Top `#` comment documents the source (UCSC hg38.chromAlias.txt) and
     notes mito is code-only, plus the extension format
     (`ensembl_name<TAB>ucsc_name` per line).
   - 3 seeded GRCh38 scaffold pairs:
     - `GL000191.1` <-> `chrUn_GL000191v1`
     - `GL000192.1` <-> `chrUn_GL000192v1`
     - `KI270711.1` <-> `chr1_KI270711v1`

2. **`src/contig/contig_aliases.py`** — the loader + lookup.
   - `_MITO: frozenset[str] = frozenset({"M", "MT"})` — code constant, bare
     names only (no `chr` prefix — prefix handling stays out of scope for
     this phase per the brief).
   - `_DATA_PATH = Path(__file__).parent / "data" / "contig_aliases.tsv"` —
     mirrors `corpus.py`'s `default_corpus_path()` pattern
     (`Path(__file__).parent / "data" / "detector_corpus.jsonl"`), which
     works for both a source checkout and an installed package since the
     wheel target `packages = ["src/contig"]` (see `pyproject.toml`) carries
     the whole `contig` package tree, including `data/`, with it.
   - `_parse_tsv()` — line-based parsing (blank lines and `#`-comment lines
     skipped), matching the simplicity of `reference_check.gtf_contigs`'s
     line-skipping style.
   - `_build_alias_map()` — builds a `dict[str, frozenset[str]]` mapping
     every member (mito members + every TSV row's ensembl/ucsc name) to its
     full equivalence group. Built once at module import time (module-level
     `_ALIAS_MAP`).
   - `alias_group(name: str) -> frozenset[str]` — public API. Looks up
     `name` in `_ALIAS_MAP`; if absent, returns `frozenset({name})`; if
     present, returns the stored group unioned with `{name}` (always
     includes the queried name, defensively, even though by construction
     every map value already contains its own key).

3. **`tests/test_contig_aliases.py`** — 7 tests, written first (RED) before
   any implementation existed.

## Exact test names

- `test_mito_mt_group_includes_both_spellings`
- `test_mito_m_group_includes_both_spellings`
- `test_seeded_scaffold_ensembl_to_ucsc`
- `test_seeded_scaffold_ucsc_to_ensembl`
- `test_unknown_name_maps_to_itself_only`
- `test_alias_group_always_includes_queried_name`
- `test_loader_tolerates_blank_and_comment_lines_and_has_known_pair`

## TDD evidence

**RED** — test file written first, `contig_aliases.py` did not exist yet:

```
$ uv run pytest tests/test_contig_aliases.py -v
ImportError while importing test module '.../tests/test_contig_aliases.py'.
E   ModuleNotFoundError: No module named 'contig.contig_aliases'
=========================== short test summary info ============================
ERROR tests/test_contig_aliases.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
=============================== 1 error in 0.04s ===============================
```

**GREEN** — after creating the TSV and implementing `contig_aliases.py`:

```
$ uv run pytest tests/test_contig_aliases.py -v
collected 7 items
tests/test_contig_aliases.py .......                                     [100%]
============================== 7 passed in 0.01s ===============================
```

No refactor pass was needed beyond the initial clean implementation (the
module is small and single-purpose; nothing came up worth restructuring
after GREEN).

## Full suite

Baseline (measured before any changes in this task): `1093 passed, 1 skipped`.

Final full-suite run:

```
$ uv run pytest
1100 passed, 1 skipped in 11.05s
```

1100 = 1093 baseline + 7 new tests. No existing test was touched, no
regression.

Note: `ruff` and `mypy` are not installed in this environment's venv
(`Failed to spawn: ruff` / `mypy` — os error 2), so no lint/type-check pass
was run; this matches what the shell had available.

## Commit

`git commit` on branch `feat/contig-alias-harmonization/aliz` with message
`feat(reference): add contig alias equivalence table (mito + GRCh38 scaffolds)`.
Commit hash recorded in the handoff message back to the orchestrating agent.

## Concerns

- None blocking. The scaffold seed set is intentionally minimal (3 pairs)
  per the brief ("completeness is explicitly NOT required") — later phases
  extending the TSV should just append rows in the same `ensembl<TAB>ucsc`
  format.
- This phase does not wire `alias_group` into `reference_check.py` or
  `reference_harmonize.py` — that is explicitly out of scope here and left
  for the next phase.

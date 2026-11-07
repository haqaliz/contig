# Local Cohort Frequency Layer — M1 Implementation Plan

**Status:** implemented 2026-11-08 — Tasks 1–5; 16 cohort tests pass. Local-only;
the federated layer remains deferred.

**Goal:** Add `contig cohort-build` and `contig cohort-query`: a local-only
aggregate of M1 variant tables with per-variant/per-gene counts and frequencies.
No network, no federated sharing.

**Architecture:** A new `contig.cohort` package. It loads M1 variants JSON via
the existing report input validator, aggregates in memory, and writes a cohort
JSON. Query filters the cohort and renders TSV/JSON. CLI is a thin Typer
wrapper. No new dependencies.

## Global Constraints

- **Local only.** No network, no central service, no cross-lab sharing.
- **No sample IDs.** Run labels are file stems, or hashes with `--anonymize`.
- **Deterministic** sorted output; timestamps only in metadata.
- **No new dependencies.**
- **Test-first.**

---

### Task 1: Models

**Files:**
- Create: `src/contig/cohort/__init__.py`
- Create: `src/contig/cohort/models.py`
- Create: `tests/test_cohort_models.py`

**Interfaces:**
- `CohortVariant`: key, seen_runs, frequency, genes, consequences,
  clinvar_significance.
- `GeneSummary`: gene, variant_count, runs_with_gene.
- `CohortRun`: label, path, sha256.
- `CohortMeta`/`Cohort`.

**Tests:** JSON round-trip, defaults.

---

### Task 2: Build

**Files:**
- Create: `src/contig/cohort/build.py`
- Create: `tests/test_cohort_build.py`
- Create: `tests/fixtures/cohort/run1.json`, `run2.json`, `run3.json`

**Interfaces:**
- `build_cohort(name, paths, anonymize=False) -> Cohort`
- `write_cohort(cohort, path)`.

**Tests:** overlapping variant counts/frequencies; gene summaries; anonymize;
deterministic output; missing/invalid input.

---

### Task 3: Query

**Files:**
- Create: `src/contig/cohort/query.py`
- Create: `tests/test_cohort_query.py`

**Interfaces:**
- `load_cohort(path) -> Cohort`
- `query_cohort(cohort, gene=None, variant=None, min_runs=None) -> list[CohortVariant]`
- `render_tsv`, `render_json`, `write_query`.

**Tests:** gene query, variant query, min-runs, no match, invalid variant string.

---

### Task 4: CLI

**Files:**
- Modify: `src/contig/cli.py`
- Create: `tests/test_cli_cohort.py`

**Interfaces:**
- `contig cohort-build --name NAME --variants a.json,b.json [--anonymize] [--out]`
- `contig cohort-query --cohort cohort.json [--gene] [--variant] [--min-runs] [--json] [--out]`

**Tests:** help, build, query, anonymize, missing input.

---

### Task 5: Docs and manual verification

**Files:**
- Modify: `docs/USAGE.md`
- Modify: `CHANGELOG.md`

**Manual checks:**
- Build a cohort from the M1 fixture tables; query BRCA1.
- Confirm `--anonymize` removes paths and hashes labels.
- Confirm no network is used.

---

## Verification

```bash
uv run pytest tests/test_cohort_*.py tests/test_cli_cohort.py -q
uv run contig cohort-build --help
```

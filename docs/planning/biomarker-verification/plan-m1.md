# Oncology Biomarker Verification — M1 Implementation Plan

**Status:** implemented 2026-11-07 — Tasks 1–5; 16 biomarker tests pass. TMB
verified on the SEQC2 truth set (15.87 mut/Mb / 2,485 Mb callable); MSI/LOH/CNV
remain `not_verified`.

**Goal:** Add `contig biomarkers`: verify TMB from a somatic VCF + callable BED,
compare a reported TMB within tolerance, and record MSI/LOH/CNV honestly as
`not_verified` in v1. No drug recommendations.

**Architecture:** A new `contig.biomarkers` package. Reuse M1 VCF/annotation
parsing; BED interval checks use stdlib `bisect`; a report model and TSV/JSON
renderer include provenance. CLI is a thin Typer wrapper. No new dependencies.

## Global Constraints

- **Research-use only.** No NCCN/drug/treatment recommendation, no clinical
  tumor-board claim.
- **TMB definition is explicit** in the output; the BED is required.
- **MSI/LOH/CNV are `not_verified` in v1**, with the reason; never a false pass.
- **No new dependencies.** Stdlib only.
- **Test-first.**

---

### Task 1: Models

**Files:**
- Create: `src/contig/biomarkers/__init__.py`
- Create: `src/contig/biomarkers/models.py`
- Create: `tests/test_biomarkers_models.py`

**Interfaces:**
- `BiomarkerEntry`: name, value, unit, status, detail.
- `BiomarkerMeta`: sources, definition, tolerance, generated_at, contig_version,
  notes.
- `BiomarkerReport`: entries, meta.

**Tests:** JSON round-trip, defaults.

---

### Task 2: Callable BED and TMB

**Files:**
- Create: `src/contig/biomarkers/tmb.py`
- Create: `tests/test_biomarkers_tmb.py`
- Create: `tests/fixtures/biomarkers/variants.vcf`
- Create: `tests/fixtures/biomarkers/callable.bed`

**Interfaces:**
- `load_callable_bed(path) -> tuple[dict[str, list[tuple[int,int]]], float]`
- `in_callable(intervals, chrom, pos) -> bool`
- `compute_tmb(vcf_path, bed_path, coding_only=False) -> dict` with variant_count,
  callable_mb, tmb, outside_count, unannotated_count, definition.

**Tests:** 5 PASS variants in 1 Mb -> 5.0; filtered/outside excluded; coding-only
filters; missing files.

---

### Task 3: TMB comparison and report

**Files:**
- Create: `src/contig/biomarkers/report.py`
- Create: `tests/test_biomarkers_report.py`

**Interfaces:**
- `build_report(vcf, bed, reported_tmb=None, tolerance=0.20, reported_msi=None,
  reported_loh=None, reported_cnv=None, coding_only=False) -> BiomarkerReport`
- `tmb_status(computed, reported, tolerance)`.
- `render_tsv`, `render_json`, `write_report`.

**Tests:** computed/match/divergent/unverified statuses; MSI/LOH/CNV
`not_verified`; no drug text; meta hashes.

---

### Task 4: CLI

**Files:**
- Modify: `src/contig/cli.py`
- Create: `tests/test_cli_biomarkers.py`

**Interfaces:**
- `contig biomarkers --vcf VCF --callable-bed BED [--reported-tmb FLOAT]
  [--tmb-tolerance 0.20] [--reported-msi TEXT] [--reported-loh TEXT]
  [--reported-cnv TEXT] [--coding-only] [--out PATH] [--json]`

**Tests:** help, run, JSON, match/divergent, missing input.

---

### Task 5: Docs and manual verification

**Files:**
- Modify: `docs/USAGE.md`
- Modify: `CHANGELOG.md`

**Manual checks:**
- Run against the SEQC2 high-confidence SNV VCF + high-confidence BED; record
  the computed TMB.
- Confirm MSI/LOH/CNV are `not_verified`.
- Confirm no drug/treatment text.

---

## Verification

```bash
uv run pytest tests/test_biomarkers_*.py tests/test_cli_biomarkers.py -q
uv run contig biomarkers --help
```

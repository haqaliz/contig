# Family/Trio Analysis — M1 Implementation Plan

**Status:** implemented 2026-11-07 — Tasks 1–7; 25 family tests pass.

**Goal:** Add `contig family`: a research-use trio/family analysis over a
multi-sample VCF + PED, with per-variant inheritance, Mendelian consistency,
de novo candidates, and pairwise sample concordance.

**Architecture:** A new `contig.family` package. Stdlib parsers read the PED and
multi-sample VCF (reusing M1 annotation helpers); a deterministic analyzer
produces rows and a summary; TSV/JSON renderers include provenance. The CLI is a
thin Typer wrapper. No new dependencies.

## Global Constraints

- **Research-use only.** No diagnosis, counselling, PGT-M, or clinical
  classification.
- **Autosomal only in v1.** X/Y/MT are `not_evaluated`, never guessed.
- **De novo is a candidate, not a validated event.**
- **Mendelian error rate excludes de novo candidates** (they are the expected
  biological exception).
- **No new dependencies.** Stdlib + existing pydantic/typer.
- **Test-first.**

---

### Task 1: Models and PED parser

**Files:**
- Create: `src/contig/family/__init__.py`
- Create: `src/contig/family/models.py`
- Create: `src/contig/family/ped.py`
- Create: `tests/test_family_models.py`
- Create: `tests/test_family_ped.py`
- Create: `tests/fixtures/family/trio.ped`

**Interfaces:**
- `FamilyMember`: sample_id, father_id, mother_id, sex, phenotype.
- `Family`: family_id, members, child/parent lookup; validate one family.
- `load_ped(path) -> Family`.
- `FamilyVariant`: key, gene, consequence, per-sample genotypes.
- `FamilyRow`: family_id, variant, child/father/mother GTs, inheritance,
  consistent, de_novo.
- `FamilyMeta`/`FamilyTable`.

**Tests:** PED parse, missing parent IDs, multiple families refused, missing
sample validation.

---

### Task 2: Multi-sample VCF reader

**Files:**
- Create: `src/contig/family/vcf.py`
- Create: `tests/test_family_vcf.py`
- Create: `tests/fixtures/family/trio.vcf`

**Interfaces:**
- `read_family_variants(path, samples: list[str]) -> tuple[list[FamilyVariant], VcfStats]`
- Reuse M1 `_parse_info`, `_parse_csq`, `_parse_ann`, `_annotation`,
  `_zygosity`; one row per ALT.

**Tests:** per-sample GT, multi-allelic split, missing sample, unannotated kept,
malformed line counted.

---

### Task 3: Inheritance and Mendelian consistency

**Files:**
- Create: `src/contig/family/analyze.py`
- Create: `tests/test_family_analyze.py`

**Interfaces:**
- `alleles(gt) -> list[int] | None`
- `inheritance(child_gt, father_gt, mother_gt, chrom) -> str`
- `mendelian_consistent(...) -> bool | None`
- `analyze_variant(family, variant) -> list[FamilyRow]`
- `summarize(rows) -> dict` with counts, error rate, de novo count, inheritance
  counts.

**Tests:** paternal, maternal, biparental, not carried, de novo, inconsistent,
missing genotype, X/Y `not_evaluated`, error-rate math.

---

### Task 4: Pairwise concordance

**Files:**
- Modify: `src/contig/family/analyze.py`
- Create: `tests/test_family_concordance.py`

**Interfaces:**
- `pairwise_concordance(variants, samples) -> list[dict]` with called sites,
  same-genotype count, opposite-homozygote count, rates, possible-swap flag for
  parent–child pairs (IBS0 > 0.01).

**Tests:** identical samples, opposite homozygotes, missing genotypes, parent–
child flag.

---

### Task 5: Table builder and renderers

**Files:**
- Create: `src/contig/family/table.py`
- Create: `tests/test_family_table.py`

**Interfaces:**
- `build_family_table(vcf_path, ped_path) -> FamilyTable`
- `render_tsv`, `render_json`, `write_table`.
- Metadata: VCF/PED paths + SHA-256, sample list, family id, counts, version,
  timestamp, notes.

**Tests:** one row per child/ALT, documented header, JSON meta, deterministic TSV,
missing files.

---

### Task 6: CLI

**Files:**
- Modify: `src/contig/cli.py`
- Create: `tests/test_cli_family.py`

**Interfaces:**
- `contig family --vcf family.vcf --ped family.ped [--out family.tsv] [--json]`

**Tests:** help, run, JSON output, missing input, multiple families error.

---

### Task 7: Docs and manual verification

**Files:**
- Modify: `docs/USAGE.md`
- Modify: `CHANGELOG.md`

**Manual checks:**
- Run the synthetic trio; confirm paternal/maternal/biparental/de novo/
  inconsistent rows and the summary.
- Confirm the same command produces identical output.
- Confirm no clinical claim in the output.

---

## Verification

```bash
uv run pytest tests/test_family_*.py tests/test_cli_family.py -q
uv run contig family --help
```

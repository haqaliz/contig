# Variant Workbench — M1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** implemented 2026-11-07 — Tasks 1–8; 52 workbench tests pass and the
full suite is green.

**Goal:** Add a research-use `contig variants` command that turns a VCF plus open
evidence sources into a deterministic, reproducible, filterable table — with no
ACMG adjudication, diagnosis, or treatment claim.

**Architecture:** A new `contig.variants` package. Pure stdlib parsers read the
VCF and TSV sources; a deterministic filter engine and sorter produce rows; a
renderer emits TSV/JSON plus provenance. The CLI command is a thin Typer wrapper
in `src/contig/cli.py`. No new dependencies, no network, no real data in CI.

**Tech Stack:** Python 3.12, stdlib `gzip`/`csv`/`dataclasses`, Pydantic v2 for
the filter spec/meta, Typer for the command, pytest. Existing `sha256_file` from
`contig.models`.

## Global Constraints

- **Research-use only.** No Contig-authored pathogenicity, diagnosis, prognosis,
  screening, or treatment claim. ClinVar is always "ClinVar reports …".
- **No new dependencies.** Stdlib + existing pydantic/typer. No `pysam`,
  `cyvcf2`, `pybedtools`, or `tabix` in v1.
- **No network in CI.** All tests use synthetic fixtures. The downloaded `data/`
  is for manual/dev runs only.
- **No real VEP/SnpEff run.** Parse `CSQ`/`ANN` from the VCF header and INFO.
- **Deterministic.** Same VCF + same sources + same spec => same rows. Sort order
  is documented and stable.
- **Honest gaps.** Missing annotation is `unannotated`, missing ClinVar is
  "not in ClinVar"; neither is treated as benign. A build-mismatched source is
  skipped with a recorded note.
- **Test-first.** Every task writes the failing test first.

---

### Task 1: Models and filter spec

**Files:**
- Create: `src/contig/variants/__init__.py`
- Create: `src/contig/variants/models.py`
- Create: `tests/test_variants_models.py`

**Interfaces:**
- `VariantKey` frozen dataclass: `chrom: str, pos: int, ref: str, alt: str`.
- `VariantRecord` dataclass: key, rsid, qual, filter, genotype, zygosity, depth,
  vaf, consequence, impact, gene, transcript, hgvsc, hgvsp, clinvar_*,
  gnomad_af/an, iranome_af/ac/an.
- `FilterSpec` Pydantic model: genes, consequences, max_af, clinvar_significance,
  pass_only, min_depth, min_vaf, zygosity, region. `to_dict()`/`from_dict()`.
- `SourceProvenance` Pydantic model: kind, path, sha256, build, version, note.
- `TableMeta` Pydantic model: sources, filters, build, generated_at,
  contig_version, notes.
- `VariantTable` dataclass: rows, meta.

**Tests:** construct a record, round-trip a spec, assert defaults and validation
(e.g., `max_af=1.5` rejected).

---

### Task 2: VCF reader and annotation parser

**Files:**
- Create: `src/contig/variants/vcf.py`
- Create: `tests/test_variants_vcf.py`
- Create: `tests/fixtures/variants/sample.vcf`

**Interfaces:**
- `read_variants(path: str | Path) -> Iterator[VariantRecord]`
- Internal: `_parse_info`, `_parse_csq`, `_parse_ann`, `_zygosity`, `_vaf`.

**Tests:**
- Plain and gzipped VCF produce identical rows.
- Multi-allelic ALT splits into one row per ALT.
- VEP `CSQ` header `Format:` is parsed; the Allele field matches the ALT.
- SnpEff `ANN` fixed layout is parsed.
- Missing `CSQ`/`ANN` => `consequence is None`, not dropped.
- GT `0/1` => het, `1/1` => hom, `./.` => unknown.
- VAF from `AF`, else from `AD`; missing => `None`.
- Malformed lines are skipped and counted in a module-level note (returned via
  `read_variants` stats or a separate `VcfStats`).

**Implementation notes:** Collect the header `##INFO=<ID=CSQ` `Format:` string;
split on `|`; map field names to indices. For ANN, use the fixed SnpEff layout.
Choose the most severe consequence per ALT. Keep a fixed severity tuple.

---

### Task 3: ClinVar source

**Files:**
- Create: `src/contig/variants/sources.py`
- Create: `tests/test_variants_sources.py`
- Create: `tests/fixtures/variants/clinvar.vcf`

**Interfaces:**
- `load_clinvar(path, sites: set[VariantKey], build: str | None) -> tuple[dict[VariantKey, ClinVarEvidence], SourceProvenance]`
- `ClinVarEvidence` dataclass: significance, review_status, condition, variant_type,
  hgvs.
- `infer_build_from_vcf(path) -> str | None` (read `##reference=`/`##assembly=`).

**Tests:**
- Matching site joins; non-matching site is absent.
- Multi-allelic ClinVar records are keyed per ALT.
- `CLNSIG`, `CLNREVSTAT`, `CLNDN`, `CLNVC`, `CLNHGVS` are surfaced.
- A missing/empty ClinVar file returns empty evidence and a note, never an error
  that hides the calls.
- Build mismatch is recorded in the provenance note, not guessed.

**Implementation notes:** Stream the ClinVar VCF, parse INFO, keep only keys in
the input site set. Do not load 4.6M records into memory.

---

### Task 4: Iranome and frequency sources

**Files:**
- Modify: `src/contig/variants/sources.py`
- Create: `tests/test_variants_frequency_sources.py`
- Create: `tests/fixtures/variants/iranome.tsv`
- Create: `tests/fixtures/variants/frequencies.tsv`

**Interfaces:**
- `load_iranome(path, sites, build) -> tuple[dict[VariantKey, IranomeEvidence], SourceProvenance]`
- `IranomeEvidence` dataclass: af, ac, an.
- `load_frequencies(path, sites) -> tuple[dict[VariantKey, FrequencyEvidence], SourceProvenance]`
- `FrequencyEvidence` dataclass: af, an, source label.

**Tests:**
- Iranome joins only when `build == "GRCh37"`; a GRCh38 build skips with a note.
- Frequency TSV joins on `(CHROM, POS, REF, ALT)`.
- Missing values are `None`, not zero.
- A source with zero matching sites is recorded honestly.

---

### Task 5: Filter engine and sorter

**Files:**
- Create: `src/contig/variants/filters.py`
- Create: `tests/test_variants_filters.py`

**Interfaces:**
- `apply_filters(rows: list[VariantRecord], spec: FilterSpec) -> list[VariantRecord]`
- `sort_rows(rows) -> list[VariantRecord]`
- `clinvar_rank(significance: str | None) -> int`

**Tests:**
- Gene list (case-insensitive), consequence, max AF (gnomAD first, Iranome
  fallback, unknown kept), ClinVar substring, PASS-only (PASS and `.`), min depth,
  min VAF, zygosity, region.
- Filters combine with AND.
- `max_af` with only Iranome evidence works; with no evidence the row is kept.
- Sort order: pathogenic, likely pathogenic, conflicting, VUS, likely benign,
  benign, missing; then AF ascending; then consequence severity; then position.
- A saved spec replays the same result.

---

### Task 6: Table renderer and provenance

**Files:**
- Create: `src/contig/variants/table.py`
- Create: `tests/test_variants_table.py`
- Create: `tests/fixtures/variants/expected.tsv`

**Interfaces:**
- `render_tsv(table: VariantTable) -> str`
- `render_json(table: VariantTable) -> str`
- `write_table(table, path, as_json: bool) -> None`
- `build_table(...) -> VariantTable` (orchestrates readers, sources, filters).

**Tests:**
- TSV header matches the documented columns; one row per ALT.
- JSON contains `meta.sources`, `meta.filters`, `meta.build`, `meta.generated_at`,
  `meta.contig_version`, `meta.notes`.
- Source SHA-256 is recorded.
- `unannotated` and "not in ClinVar" are explicit.
- No output field named `pathogenic` or `diagnosis` owned by Contig.

---

### Task 7: CLI command

**Files:**
- Modify: `src/contig/cli.py`
- Create: `tests/test_cli_variants.py`

**Interfaces:**
- `contig variants VCF [--clinvar PATH] [--iranome PATH] [--frequencies PATH]
  [--build GRCh37|GRCh38] [--gene LIST] [--consequence LIST] [--max-af FLOAT]
  [--clinvar-significance LIST] [--pass-only] [--min-depth INT] [--min-vaf FLOAT]
  [--zygosity het|hom|hemi] [--region CHROM:START-END] [--spec PATH]
  [--save-spec PATH] [--out PATH] [--json]`

**Tests:**
- `--help` lists the options.
- A synthetic run writes a TSV and prints the research-use notice to stderr.
- `--json` emits parseable JSON.
- `--save-spec` then `--spec` reproduces the same rows.
- Missing input exits non-zero with a clear message.
- `--build GRCh38` + `--iranome` records the skip note.

**Implementation notes:** Keep the command a thin wrapper around
`contig.variants.command.run_variants`. Print the research-use notice to stderr so
TSV stdout stays clean. Use `typer.Exit(code=1)` for input errors.

---

### Task 8: Docs and manual verification

**Files:**
- Modify: `docs/USAGE.md` (add a `contig variants` section)
- Modify: `README.md` (one line in the feature table or quickstart, optional)
- Modify: `CHANGELOG.md` (Unreleased entry, optional but repo convention)

**Manual checks (not CI):**
- Run against the downloaded Kaggle VCF + ClinVar VCF + Iranome TSV.
- Run against the Ensembl VEP chr22 VCF (catalogue; verifies CSQ parsing at
  scale).
- Confirm a GRCh38 input + Iranome produces the skip note.
- Confirm the output is byte-identical on a second run with the same spec.

---

## Verification

```bash
uv run pytest tests/test_variants_*.py tests/test_cli_variants.py -q
uv run contig variants --help
```

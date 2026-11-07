# Panel Builder & Registry — M1 Implementation Plan

**Status:** implemented 2026-11-07 — Tasks 1–6; 22 panel tests pass.

**Goal:** Add `contig panel-build`, `contig panel-list`, and `contig panel-show`:
resolve gene symbols, build a canonical exon BED from a GTF, validate an
uploaded BED, checksum it, and store it with metadata.

**Architecture:** A new `contig.panels` package. Stdlib parsers read HGNC/GTF/BED;
a builder writes `<id>.bed` + `<id>.json`; the CLI is a thin Typer wrapper. The
resulting BED is already accepted by M1/M2. No new dependencies.

## Global Constraints

- **No new dependencies.** Stdlib only.
- **Deterministic BED.** Sorted, deduped, normalized `chr` prefixes; the panel id
  is a slug + short SHA-256 of the BED.
- **HGNC optional.** Validate/normalize when supplied; otherwise keep uppercase
  symbols with a note.
- **No clinical claims.** A panel is a research-use interval definition.
- **Test-first.**

---

### Task 1: Models

**Files:**
- Create: `src/contig/panels/__init__.py`
- Create: `src/contig/panels/models.py`
- Create: `tests/test_panels_models.py`

**Interfaces:**
- `PanelMeta` Pydantic: id, name, build, source, genes, transcripts, method,
  checksum, created_at, contig_version, notes.
- `Panel` dataclass: meta, bed_text.

**Tests:** JSON round-trip, required fields, defaults.

---

### Task 2: HGNC resolution

**Files:**
- Create: `src/contig/panels/hgnc.py`
- Create: `tests/test_panels_hgnc.py`
- Create: `tests/fixtures/panels/hgnc.tsv`

**Interfaces:**
- `load_hgnc(path) -> HgncIndex` (approved, aliases, previous, version).
- `resolve_symbols(symbols, index) -> tuple[list[str], list[str]]` (approved,
  unknown).

**Tests:** approved symbol, alias, previous symbol, unknown list, duplicate
collapse, case-insensitivity.

---

### Task 3: Gene-list BED builder

**Files:**
- Create: `src/contig/panels/build.py`
- Create: `tests/test_panels_build.py`
- Create: `tests/fixtures/panels/genes.gtf`

**Interfaces:**
- `build_from_genes(genes, gtf, hgnc_path, name, build, transcripts) -> Panel`
- `build_from_bed(path, name, build) -> Panel`
- `canonical_bed(rows) -> str` (sort, dedupe, format)
- `panel_id(name, bed_text) -> str`

**Tests:**
- MANE Select exons win; `all` keeps all protein-coding transcripts.
- 1-based GTF -> 0-based BED conversion.
- BED input sorts/dedupes/normalizes `chr`.
- Invalid BED coordinates are skipped/refused.
- Same inputs -> same id/checksum.

---

### Task 4: Registry

**Files:**
- Modify: `src/contig/panels/build.py`
- Create: `tests/test_panels_registry.py`

**Interfaces:**
- `write_panel(panel, out_dir) -> tuple[Path, Path]`
- `list_panels(dir) -> list[PanelMeta]`
- `load_panel(dir, panel_id) -> Panel`

**Tests:** write/read round-trip, list ordering, missing id, checksum matches the
stored BED.

---

### Task 5: CLI

**Files:**
- Modify: `src/contig/cli.py`
- Create: `tests/test_cli_panels.py`

**Interfaces:**
- `contig panel-build --name NAME (--genes LIST --gtf PATH | --bed PATH)
  [--hgnc PATH] [--build GRCh38] [--transcripts mane|all] [--out-dir panels]`
- `contig panel-list [--dir panels]`
- `contig panel-show PANEL_ID [--dir panels]`

**Tests:** help, build from genes/BED, list/show, unknown gene exits non-zero,
`--genes`/`--bed` mutually exclusive.

---

### Task 6: Docs and manual verification

**Files:**
- Modify: `docs/USAGE.md` (panel section)
- Modify: `CHANGELOG.md` (Unreleased entry)

**Manual checks:**
- Build a BRCA1/BRCA2 panel from `data/ensembl/Homo_sapiens.GRCh38.113.gtf.gz`
  and `data/mane/hgnc_complete_set.txt`.
- Confirm the BED is accepted by `contig readiness --bed`.
- Build the same panel twice; confirm the id/checksum are identical.

---

## Verification

```bash
uv run pytest tests/test_panels_*.py tests/test_cli_panels.py -q
uv run contig panel-build --help
```

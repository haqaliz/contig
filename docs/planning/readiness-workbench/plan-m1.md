# Coverage & Readiness Workbench — M1 Implementation Plan

**Status:** implemented 2026-11-07 — Tasks 1–8; 35 readiness tests pass.

**Goal:** Add a research-use `contig readiness` command that turns a
`samtools depth` TSV plus a target BED/GTF into a per-target coverage and
readiness table, with explicit homology/pseudogene caveats and no clinical
claim.

**Architecture:** A new `contig.readiness` package. Stdlib parsers read the
depth TSV, BED/GTF targets, and caveat BED; a deterministic evaluator produces
metrics and `ready`/`caution`/`not-interpretable`; renderers emit TSV/JSON plus
provenance. The CLI is a thin Typer wrapper in `src/contig/cli.py`.

**Tech Stack:** Python 3.12, stdlib `gzip`/`csv`/`dataclasses`, Pydantic for the
thresholds/meta, Typer, pytest. No new dependencies.

## Global Constraints

- **Research-use only.** Readiness is a data-sufficiency check, never a clinical
  guarantee or diagnosis.
- **No BAM/CRAM or `samtools` in v1.** The input is a depth TSV; `--bam` is a
  follow-up.
- **No network in CI.** Synthetic fixtures only.
- **BED is 0-based half-open; depth positions are 1-based.** Convert explicitly.
- **Missing depth = zero coverage.** Never "unknown"; an empty target is
  `not-interpretable`, never a pass.
- **Deterministic.** Same depth + targets + caveats + thresholds => same rows.
- **Test-first.**

---

### Task 1: Models and thresholds

**Files:**
- Create: `src/contig/readiness/__init__.py`
- Create: `src/contig/readiness/models.py`
- Create: `tests/test_readiness_models.py`

**Interfaces:**
- `Target` dataclass: chrom, start, end, name, gene, transcript, exon.
- `CaveatRegion` dataclass: chrom, start, end, name, reason.
- `ReadinessThresholds` Pydantic model: `depth_threshold` (default 20),
  `ready_fraction` (0.90), `caution_fraction` (0.50). Validate 0..1 fractions.
- `TargetMetrics` dataclass: target + bases, covered_bases, mean_depth,
  pct_20x, pct_50x, pct_100x, zero_bases, caveats, readiness, reason.
- `ReadinessMeta`/`ReadinessTable` with sources, thresholds, generated_at,
  contig_version, notes.

**Tests:** validation, defaults, JSON round-trip.

---

### Task 2: Depth TSV reader

**Files:**
- Create: `src/contig/readiness/depth.py`
- Create: `tests/test_readiness_depth.py`
- Create: `tests/fixtures/readiness/depth.tsv`

**Interfaces:**
- `load_depth(path) -> tuple[dict[tuple[str, int], int], DepthStats]`
- `DepthStats`: lines, positions, skipped, duplicates.

**Tests:**
- Parses `chrom pos depth`; normalizes `chr` prefixes.
- Skips `#` comments and an optional `chrom` header.
- Malformed lines are skipped and counted.
- Missing positions are absent from the dict (the evaluator treats them as 0).
- Duplicate positions keep the last value and count the duplicate.

---

### Task 3: Target readers

**Files:**
- Create: `src/contig/readiness/targets.py`
- Create: `tests/test_readiness_targets.py`
- Create: `tests/fixtures/readiness/panel.bed`
- Create: `tests/fixtures/readiness/genes.gtf`

**Interfaces:**
- `load_bed_targets(path) -> list[Target]`
- `load_gtf_targets(path, genes) -> list[Target]`
- `normalize_chrom` reused from `contig.variants.vcf`.

**Tests:**
- BED3 gets a `chrom:start-end` name; BED4 uses the name.
- BED coordinates stay 0-based half-open.
- GTF exons are grouped per gene/transcript/exon; MANE Select wins when tagged.
- A gene list filters the GTF; an empty gene list is refused.

---

### Task 4: Caveat reader and overlap

**Files:**
- Create: `src/contig/readiness/caveats.py`
- Create: `tests/test_readiness_caveats.py`
- Create: `tests/fixtures/readiness/homology.bed`

**Interfaces:**
- `load_caveats(path) -> list[CaveatRegion]`
- `overlapping_caveats(target, caveats) -> list[CaveatRegion]`

**Tests:**
- BED4 and the 8-column homology BED both parse.
- Half-open overlap is correct at the boundaries.
- A target with no overlap returns an empty list.
- Chrom prefixes are normalized.

---

### Task 5: Evaluator and readiness states

**Files:**
- Create: `src/contig/readiness/evaluate.py`
- Create: `tests/test_readiness_evaluate.py`

**Interfaces:**
- `evaluate_target(target, depths, thresholds, caveats) -> TargetMetrics`
- `evaluate_targets(targets, depths, thresholds, caveats) -> list[TargetMetrics]`

**Tests:**
- All positions ≥20x, mean ≥20x, no caveat => `ready`.
- 80% ≥20x => `caution` with the fraction in the reason.
- 10% ≥20x => `not-interpretable` with the fraction in the reason.
- Zero depth => `not-interpretable`, `zero_bases == bases`.
- Homology overlap at high depth => `caution`, caveat named.
- Missing depth positions count as zero in the denominator.
- `pct_50x`/`pct_100x` are computed independently of the threshold.

---

### Task 6: Table builder and renderers

**Files:**
- Create: `src/contig/readiness/table.py`
- Create: `tests/test_readiness_table.py`

**Interfaces:**
- `build_readiness(depth, bed=None, gtf=None, genes=(), caveats=None,
  thresholds=None) -> ReadinessTable`
- `render_tsv(table)`, `render_json(table)`, `write_table(table, path, as_json)`.

**Tests:**
- One row per target; the documented header.
- `not-interpretable` and caveat text are explicit.
- JSON meta contains source paths/SHA-256, thresholds, version, timestamp.
- Building twice with the same inputs produces identical rows.
- A missing depth/target file raises `FileNotFoundError`.

---

### Task 7: CLI command

**Files:**
- Modify: `src/contig/cli.py`
- Create: `tests/test_cli_readiness.py`

**Interfaces:**
- `contig readiness --depth PATH (--bed PATH | --gtf PATH --genes LIST)
  [--caveats PATH] [--depth-threshold INT] [--ready-fraction FLOAT]
  [--caution-fraction FLOAT] [--out PATH] [--json]`

**Tests:**
- `--help` lists the options.
- A synthetic run writes a TSV and prints the research-use notice to stderr.
- `--json` emits parseable JSON.
- Missing input exits non-zero with a clear message.
- `--bed` and `--gtf` are mutually exclusive; one is required.

---

### Task 8: Docs and manual verification

**Files:**
- Modify: `docs/USAGE.md` (add a `contig readiness` section)
- Modify: `CHANGELOG.md` (Unreleased entry)

**Manual checks:**
- Generate `samtools depth -a -b data/nfcore/target_chr20.bed
  data/nfcore/NA12878_*.cram > /tmp/depth.tsv`; run `contig readiness` on it
  with the nf-core BED and the curated homology BED.
- Confirm the zero-coverage targets are `not-interpretable`, and that the state
  summary is printed.
- Confirm the same command produces identical output on a second run.

---

## Verification

```bash
uv run pytest tests/test_readiness_*.py tests/test_cli_readiness.py -q
uv run contig readiness --help
```

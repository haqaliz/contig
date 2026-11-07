# PRD — Research-use variant workbench (M1)

Feature slug: `variant-workbench` · Type: feat · Owner: aliz
Branch: `feat/variant-workbench/aliz` · Capability: **M1 (variant workbench)**
Status: drafted 2026-11-07 (planning → PRD)

## Problem Statement

Contig can run and verify a germline or somatic variant-calling pipeline, and it
can verify that the annotation step ran. But it stops before the question the
researcher actually asks: **"which of these variants should I look at first?"**

Today the user gets a verified VCF and a verdict, then goes back to spreadsheets,
`bcftools` one-liners, or a clinical platform to filter by gene, consequence,
population frequency, and ClinVar significance. That work is manual, hard to
reproduce, and usually loses the link back to the verified run.

M1 adds a **research-use variant workbench**: a deterministic, reproducible table
that joins the run's calls to open evidence sources and lets the user filter and
export them. It is deliberately **not** an interpretation or diagnosis engine.
Contig surfaces what ClinVar, gnomAD, Iranome, VEP/SnpEff, and CIViC reported,
attributed to the source and version; it never adjudicates pathogenicity.

**Who has the problem:** the disease-research ICP — a lone computational
biologist or a wet-lab scientist who can't code — who has a verified call set and
needs a defensible shortlist for review, without a clinical-credential product.

**Why now:** the data is acquired (`DATA_SOURCES.md`), the annotation verifier
exists (C7), and this is the missing last mile between a verified run and a
usable result. It needs no model and no clinical claims.

## Goals & Success Metrics

- **G1 — One reproducible table.** Given a VCF and open evidence sources, produce
  a TSV/JSON table that can be regenerated from a saved filter spec and source
  checksums.
- **G2 — Deterministic filtering.** Gene, consequence, population frequency,
  ClinVar significance, PASS, depth, VAF, zygosity, and region filters are
  explicit, testable, and documented. No hidden ranking model.
- **G3 — Attribution, never adjudication.** Every evidence cell names its source.
  ClinVar is shown as "ClinVar reports …" with review status; Contig never emits
  its own pathogenic/benign call, diagnosis, or treatment recommendation.
- **G4 — Honest gaps.** A variant with no annotation is marked `unannotated` or
  left empty with a source note; it is never silently treated as benign. A
  build-mismatched source is skipped with a recorded note, not guessed.
- **Success metric:** a user can go from a VCF to a filtered, reproducible TSV in
  one command, and a second run with the same spec produces the same rows.

## User Personas & Scenarios

- **Lone computational biologist:** has a verified sarek run, wants a quick
  shortlist of rare, coding, ClinVar-flagged variants for a PI meeting, and wants
  to hand over a table with provenance.
- **Wet-lab scientist who can't code:** has a VCF from a collaborator, wants to
  filter to a gene panel and rare variants without writing `bcftools`.
- **Core facility:** wants a consistent, auditable filtering step across many
  samples, with the same spec and source versions.

## Requirements

### Must-have (v1)

- **Input:** a VCF (plain or `.gz`) with at least `CHROM`, `POS`, `ID`, `REF`,
  `ALT`, `QUAL`, `FILTER`, `INFO`, `FORMAT`, and one sample column.
- **Annotation parsing:** read VEP `CSQ` and SnpEff `ANN` from INFO when present;
  extract consequence, impact, gene symbol, transcript, HGVSc, HGVSp. Choose the
  most severe consequence per ALT. If neither is present, mark the variant
  `unannotated` (never drop it silently).
- **ClinVar source:** accept a ClinVar VCF (GRCh38 or GRCh37). Join on
  `(CHROM, POS, REF, ALT)`. Surface `CLNSIG`, `CLNREVSTAT`, `CLNDN`, `CLNVC`,
  `CLNHGVS` as "ClinVar reports …". Do not restate significance as Contig's own.
- **Iranome source:** accept the scraped `iranome_panel.tsv` (GRCh37). Join on
  `(CHROM, POS, REF, ALT)` only when the input build is GRCh37; otherwise skip
  with a recorded note. Surface `allele_freq`, `allele_count`, `allele_num`.
- **Frequency source:** accept a TSV with `CHROM, POS, REF, ALT, AF, AN`
  (gnomAD or any population source). Surface `AF`/`AN` with the source label.
- **Filters:** gene/panel list, consequence class, max population AF, ClinVar
  significance, PASS-only, minimum depth, minimum VAF, zygosity, and region.
  All filters are deterministic and combine with AND.
- **Sort order:** ClinVar significance severity (most actionable first), then
  population AF ascending, then consequence severity, then genomic position.
  The rule is documented and stable.
- **Output:** TSV by default; `--json` for a structured table plus metadata.
  `--out` writes to a file. The metadata includes source paths, SHA-256, build,
  filter spec, and a UTC timestamp.
- **Saved spec:** `--save-spec` writes the filter/source configuration;
  `--spec` replays it. Explicit flags override the spec.
- **CLI:** `contig variants <vcf> ...` with `--help`.
- **Tests:** synthetic fixtures only in CI; no network, no real VEP/SnpEff, no
  dependency on `data/`.

### Should-have (later slices)

- A dashboard table over the same JSON (read-only, no new engine logic).
- A `tabix`-backed ClinVar lookup for large inputs (v1 streams and keeps only
  input sites).
- gnomAD GraphQL API client with a local cache (v1 accepts a TSV).
- Liftover for Iranome GRCh37 → GRCh38.
- CIViC cancer evidence join (v1 leaves a column stub).
- Saved filter presets (e.g., "rare coding", "panel review").
- A "why is this row here?" one-line explanation per filter.

### Nice-to-have / explicit non-goals

- ACMG/AMP classification computed by Contig.
- Pathogenicity, diagnosis, prognosis, screening, or treatment recommendations.
- A general variant database or a clinical report.
- A trained ranking model or LLM-generated interpretation.
- A patient-facing portal.

## Technical Considerations

- **No new dependencies.** The engine is stdlib + pydantic + typer. VCF/TSV
  parsing is stdlib `gzip`/`csv`. `tabix` is optional and external; v1 avoids it.
- **Streaming join.** For a large ClinVar VCF, collect the input sites first,
  stream the ClinVar records, and keep only matching sites. This avoids loading
  4.6M records into memory.
- **Build guard.** The source build is explicit (`--build` or inferred from the
  VCF header). Iranome is GRCh37; a GRCh38 input skips it with a note. No liftover
  in v1.
- **Attribution model.** Each source contributes a named field and a provenance
  entry. ClinVar's significance is never copied into a Contig-authored
  `pathogenicity` field.
- **Reproducibility.** The output metadata records the exact source files and
  checksums, the filter spec, and the Contig version. The table is a function of
  those inputs.
- **Reuse.** The VCF open/read patterns and `sha256_file` already exist in the
  repo; do not add a new generic VCF library.

## Risks & Open Questions

- **R1 — interpretation creep.** The UI/table must not imply a clinical call.
  Mitigation: column names say `clinvar_significance`, `clinvar_review_status`,
  and the CLI prints a research-use notice. No `pathogenic` boolean owned by
  Contig.
- **R2 — multi-allelic and missing fields.** Real VCFs are messy. Mitigation:
  split multiallelic ALTs; keep per-ALT evidence; mark missing values as empty,
  never zero; count and report malformed lines.
- **R3 — build mismatch.** Iranome is GRCh37, most calls are GRCh38. Mitigation:
  skip with a note in v1; liftover is a separate slice.
- **R4 — large ClinVar memory.** Mitigation: site-set streaming join; a `tabix`
  path is a follow-up.
- **Open:** should the default table include all variants or only PASS? (v1:
  include all, with `--pass-only` available.)
- **Open:** which consequence ordering to use? (v1: the existing VEP/SnpEff
  severity vocabulary, documented in the code.)
- **Open:** which ClinVar significance strings count as "actionable"? (v1:
  substring filter, no hard-coded clinical logic.)

## Out of Scope

- Clinical diagnosis, ACMG classification as Contig's own call, treatment
  recommendations, patient portals.
- gnomAD API, liftover, CIViC join, dashboard in v1.
- Any model training.

## Data

Use the sources documented in
`docs/planning/research-workbenches/DATA_SOURCES.md`:

- ClinVar GRCh38 VCF (`data/clinvar/clinvar.vcf.gz`).
- Iranome panel (`data/iranome/iranome_panel.tsv`, GRCh37).
- A gnomAD TSV or subset (v1 accepts a TSV; the API is later).
- The Kaggle ClinVar table and the Ensembl VEP chr22 VCF are development
  fixtures, not required at run time.

## Acceptance

- `contig variants sample.vcf --clinvar clinvar.vcf --iranome iranome.tsv
  --build GRCh37 --gene BRCA1,BRCA2 --max-af 0.01 --pass-only --out table.tsv`
  produces a table with one row per ALT, attributed evidence, and a metadata
  sidecar (or JSON meta).
- Running the same command with the saved spec produces identical rows.
- A variant absent from ClinVar is shown as "not in ClinVar", not as benign.
- A GRCh38 input with `--iranome` skips Iranome and records the reason.
- No output field or message claims a diagnosis or a Contig-authored
  pathogenicity call.

# Aspect spec: surface-and-provenance (C7 M5)

Single aspect covering all of shippable M5. Parent PRD:
`docs/planning/annotation-m5-surface/prd.md`. One atomic PR.

## Problem slice & user outcome

Make M4's already-computed annotation concordance **legible** (a "corroborated by" line on
every verdict surface) and pin the annotation **cache/build identifier** into provenance so
the analysis reproduces against the same annotation data. Research-use only.

## In scope

- A shared Python helper that reads the M4 `kind="concordance"` results +
  `annotation_identity` and returns a corroboration line (or `None`).
- Render that line on: text report, HTML report, `contig methods`, Next.js dashboard
  concordance card.
- `AnnotationProvenance.db_version` (labeled "cache/build") captured from VEP `cache="…"`
  and SnpEff `##SnpEffCmd`/`##SnpEffGenomeVersion`; rendered in methods + HTML panel +
  dashboard; round-trips through the bundle; pre-M5 bundles still load.
- SnpEff DB-token fixture (none exists today).

## Out of scope

- C6 eval-corpus fold-in (blocked). FAIL severity. Cache wiring. Per-DB (ClinVar/gnomAD)
  version. Any new `QCResult`/primitive/model beyond the one optional field.

## Acceptance criteria (testable)

1. `corroborated_by_line(record)` returns a line naming both annotators + the consequence
   fraction `matches/total (0.XX)` and marks gene-symbol as informational, **only** when
   `consequence_concordance.value is not None`; else `None`. (PRD D2, D3)
2. Text report, HTML report, and methods each include that line for a dual-annotated
   fixture; none show a fabricated fraction for a single-annotator/absent fixture.
3. Dashboard concordance card renders the line; `annotation_identity` is on the TS
   `RunRecord`; a component test asserts the line for a dual-annotated record and its
   absence for a single-annotator record.
4. `db_version` parsed: VEP `cache="…/110_GRCh38"` → `110_GRCh38`; SnpEff `##SnpEffCmd`
   genome token → e.g. `GRCh38.105`; absent → `None`. Rendered labeled "cache/build".
5. A pre-M5 bundle (no `db_version` key) loads and reproduces; a round-trip preserves
   `db_version`. Existing annotation suites stay green; verify exit code unchanged.

## Dependencies & sequencing

Python model+parse (foundation) → Python surfaces → dashboard (last, independent). Fixtures
land with the phase that needs them (TDD RED).

## Open questions / risks

- Exact SnpEff header spelling (R1) — commit to a synthetic spelling; real-run mismatch
  degrades to `None`, never wrong.
- Dashboard JSON-shape match for `annotation_identity` (R3) — test over a real
  `run_record.json`-shaped fixture. Heed `dashboard/AGENTS.md` (non-standard Next.js).

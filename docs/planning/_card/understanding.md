# Understanding: annotation-m5-surface (C7 M5, Phase-2 dig)

Dig date: 2026-07-10. Two read-only agents mapped (1) the M4 concordance-surfacing path
and (2) the AnnotationProvenance capture/render/reproduce path in the worktree. Findings
below are grounded in `file:line` anchors verified against the worktree source.

## What the work is really asking

Close out the variant-annotation assay (C7) with milestone **M5**, scoped to the two
**unblocked** halves and deferring the third (blocked) half:

- **Part 1 — "Corroborated by" surface line.** M4 already *computes* two
  `kind="concordance"` `QCResult`s (`consequence_concordance`, `gene_symbol_concordance`).
  M5 makes them **human-legible**: a one-line "corroborated by VEP and SnpEff (…% agree)"
  summary on the verdict surfaces. Read the computed results; never recompute.
- **Part 2 — Annotation DB/cache-version provenance.** Capture the annotation
  **database/cache version** from the VCF header (currently discarded) into
  `AnnotationProvenance`, render it in `contig methods` + the HTML provenance panel, and
  let it round-trip through the reproduce bundle.
- **Part 3 — DEFERRED (blocked).** Folding annotation outcomes into the C6 eval corpus:
  blocked on C6's no-ground-truth-labels problem (deferred across v0.17.0/v0.22.0). Note,
  don't build.

## Affected areas (grounded)

### Part 1 — surfacing (read, don't recompute)
- `models.py:64` `QCKind = Literal["metric","structural","concordance"]`; `QCResult`
  at `models.py:67-75` — **no dedicated annotator field**; tool names live only in the
  `message` string. Annotator names for rendering must come from
  `RunRecord.annotation_identity` (`models.py:301`, `list[AnnotationProvenance]`).
- `verification/annotation_concordance.py` emits the two metrics
  (`consequence_concordance` ~150-193 WARN-capable; `gene_symbol_concordance` ~320-375
  informational, always `pass`). Wired at `runner.py:174`.
- **Insertion points (3 Python surfaces, all have annotator names in hand):**
  1. Text report — `report.py:render_run_report`, inside `if concordance:` after
     `report.py:107`.
  2. HTML report — `report.py:render_run_report_html`, between `report.py:280` and `:281`
     (a `<p>` note); this file already renders an "Annotation identity" section at
     `report.py:344-357`.
  3. `contig methods` — extend `methods.py:_annotation_clause` (`methods.py:81-103`), which
     already names both annotators.
- **Recommendation:** one shared helper `corroborated_by_line(record)` that reads the
  concordance `QCResult`s + `annotation_identity`, dropped into all three surfaces.
- `render_explain` (`report.py:69-82`) only prints checks whose status == overall verdict;
  since concordance is at-most-WARN/always-PASS it rarely appears there — **not** the home
  for this line. Confirmed: `render_run_report` is the terminal surface (`cli.py:610`,
  `cli.py:699`).

### Part 2 — provenance
- Model: `AnnotationProvenance` (`models.py:206-216`) has exactly `tool`, `version`,
  `raw_header`. Add `db_version: str | None = None`. **No validator change needed** — the
  `_normalize_annotation_identity` `mode="before"` validator (`models.py:310-324`) accepts
  a dict, and Pydantic defaults the new optional field, so pre-M5 bundles load unchanged.
- Capture point: `bundle.py:_parse_annotation_header` (`bundle.py:113-126`), orchestrated
  by `compute_annotation_identity` (`bundle.py:129-153`), called once at
  `self_heal.py:1282` (variant-assay-gated).
  - **VEP**: header `##VEP="v110" time="..." cache="/vep/homo_sapiens/110_GRCh38"` — the
    `cache="..."` token (→ basename `110_GRCh38`) is **currently discarded**; parse it into
    `db_version`.
  - **SnpEff**: only `##SnpEffVersion=` is read today. The genome DB (e.g. `GRCh38.105`)
    lives in `##SnpEffCmd` / `##SnpEffGenomeVersion`, which is **not scanned** — add a scan.
- Render: `methods.py:_annotation_clause` (~97-98) and `report.py:354-356` (`ann_rows`
  dict → add a DB-version cell).
- Reproduce: automatic. `write_bundle`→`model_dump_json`, `load_bundle`→
  `model_validate_json` (`bundle.py:23-59`); optional-field default is the back-compat
  guarantee; signature sidecar is field-neutral for newly written bundles.

## Ambiguities / open questions for the PRD

1. **Dashboard (Next.js) scope.** `dashboard/lib/types.ts` `RunRecord` (~83-101) omits
   `annotation_identity` entirely — no `AnnotationProvenance` type in `dashboard/`. So the
   dashboard concordance card (`dashboard/components/run/qc-panel.tsx:188-203`) cannot show
   annotator names or a corroboration line without adding the field to `types.ts` (+ any
   loader). **Open:** include the dashboard in M5, or scope M5 to the Python surfaces
   (text/HTML report + methods) and defer the Next.js card? Leaning **Python-only** for
   this slice (the HTML report already covers a browser-viewable surface); flag the
   dashboard as a clean follow-on.
2. **SnpEff DB-version fixture gap (must-fix if part 2 ships).** VEP fixtures already carry
   `cache="…110_GRCh38"`, but **no SnpEff fixture has any DB token** (`SnpEffCmd` appears
   nowhere in `src/` or `tests/`). To exercise the SnpEff DB-version path we must add a
   `##SnpEffCmd="SnpEff GRCh38.105 …"`-style line to the SnpEff fixtures in
   `tests/test_annotation_provenance.py` (+ lifecycle/integration). Confirm the exact real
   SnpEff header spelling before writing the fixture.
3. **DB-version normalization.** Decide the exact token we store: VEP → cache basename
   (`110_GRCh38`) vs the raw cache path; SnpEff → the genome-DB string (`GRCh38.105`).
   Keep it minimal and honest; store `None` when absent (never fabricate — C5 rule).
4. **Corroboration-line wording + empty states.** When only one annotator ran / annotation
   absent / below shared-record floor, the concordance results are UNVERIFIED — the line
   must render nothing or an honest "not corroborated (single annotator)" rather than a
   fabricated agreement. Nail the copy in the PRD.

## Guardrail check (CLAUDE.md)

On-thesis Layer-2: this is verify/reproduce **surfacing + provenance**, not Layer-1
authoring, no new verification primitive, no models, no proprietary data. Research-use
only — a corroboration line and a DB-version string, never a pathogenicity/clinical
verdict; UNVERIFIED never rendered as PASS. No drift detected.

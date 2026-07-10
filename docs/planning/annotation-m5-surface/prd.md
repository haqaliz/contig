# PRD: annotation-m5-surface (C7 M5 — annotation surface + DB-version provenance)

Status: draft for review. Owner: aliz. Branch: `feat/annotation-m5-surface/aliz`.
Slug: `annotation-m5-surface`.
Sources: `docs/planning/_card/issue.md` (contig-next handoff), `_card/understanding.md`
(Phase-2 dig, two read-only agents), the initiative PRD
`docs/planning/variant-annotation-assay/prd.md` (M5 row), the M4 PRD
`docs/planning/annotation-concordance/prd.md` (Out-of-Scope names M5), and
`docs/technical/CAPABILITY_ROADMAP.md` C7 (M5 row, lines ~674-677).

### Decisions locked at review gate (2026-07-10, approved)

- **D1 — Field name/label is "annotation cache/build", not "database version".** The new
  provenance field is `db_version` internally but is **rendered/labeled as the annotation
  cache/build identifier** (e.g. VEP `cache 110_GRCh38`, SnpEff `GRCh38.105`), never as a
  ClinVar/gnomAD "database version" — that would over-claim (R2). Every render label uses
  "cache/build".
- **D2 — Empty-state rule: render the corroboration line ONLY when
  `consequence_concordance.value is not None`; otherwise OMIT on every surface.** Single
  annotator, annotation absent, and below-floor UNVERIFIED all collapse to omission. N-1's
  explicit "not corroborated" note is dropped unless trivial. This makes G2 one testable
  assertion.
- **D3 — Fraction render contract:** `matches/total (0.XX)` reusing M4's 4dp `value`
  rounding for the parenthetical; **S-1 is promoted to must-have** — the line must visibly
  mark `gene_symbol_concordance` as "informational" so a low symbol fraction never reads as
  a failure.

Capability: **C7 milestone M5** — the final annotation-assay slice. M1 (germline
structural verify + provenance, v0.25.0), M2 (somatic gate, v0.26.0), M3 (annotation
plausibility, v0.26.0), M4 (VEP-vs-SnpEff concordance, v0.27.0) are shipped. M5 adds the
**human-legible surface** for M4's concordance and the **DB/cache-version provenance**;
the third M5 sub-part (folding annotation outcomes into the C6 eval corpus) is **deferred**
(blocked, see Out of Scope).

## Problem Statement

Two gaps remain after M4:

1. **M4's corroboration signal is computed but not legible.** A germline/somatic run now
   emits two `kind="concordance"` `QCResult`s (`consequence_concordance`,
   `gene_symbol_concordance`), but they only appear as raw check rows
   (`report.py:108-109`: `"{check}: {STATUS} (value {value})"`). A researcher reading the
   verdict gets no plain-language "VEP and SnpEff agree on 47/50 consequences (0.94)" line
   — the diagnostic value of M4 is buried. The M4 PRD explicitly deferred this "corroborated
   by" line to M5 (`annotation-concordance/prd.md:230`).

2. **The annotation DB/cache version is discarded, weakening the reproduce guarantee.**
   `AnnotationProvenance` captures the annotation *tool* + *tool version* (VEP `v110`,
   SnpEff `5.1d`) but **not the database/cache version** the annotation ran against
   (`bundle.py:_parse_annotation_header` reads `##VEP="v110"` and throws away the
   `cache="…/110_GRCh38"` token; it never scans SnpEff's `##SnpEffCmd` for the genome DB).
   Two runs with identical tool versions but different ClinVar/gnomAD/cache releases produce
   different annotations that Contig's provenance cannot distinguish — a reproducibility
   hole in the exact "pins the *data*, not just the tools" spirit C5 established
   (`CAPABILITY_ROADMAP.md:674-677`).

**For whom.** The variant-analysis personas (lone computational biologist, core facility,
biotech) running germline/somatic calling with annotation, who need (a) a defensible,
non-expert-legible "two tools agree" line in the verdict and (b) the annotation DB version
pinned in the Methods/reproduce bundle for a citable, reproducible analysis.

**Evidence it's real.** M5 is the named final milestone (`variant-annotation-assay/prd.md`
M5 row; `CAPABILITY_ROADMAP.md:674-677`), explicitly scoped in the M4 PRD Out-of-Scope
(`annotation-concordance/prd.md:229-231`), on an actively-shipping 4-slice track (v0.25.0
→ v0.27.0, all 2026-07-10).

## Goals & Success Metrics

- **G1 — A "corroborated by" line renders on all verdict surfaces when concordance was
  computed.** For a run with computed annotation-concordance results, the text report, HTML
  report, `contig methods`, and the Next.js dashboard concordance card each show a
  plain-language line naming both annotators and the consequence-agreement fraction (and the
  informational gene-symbol fraction).
  *Metric:* a test per surface asserts the line is present with both tool names and the
  fraction, sourced from the existing `QCResult`s (never recomputed).
- **G2 — The line degrades honestly.** When only one annotator ran, annotation was absent,
  or shared records fell below the floor (concordance UNVERIFIED / no computable value), the
  line either does not render or renders an explicit "not corroborated (single annotator)"
  — never a fabricated agreement number.
  *Metric:* a single-annotator fixture and an annotation-absent fixture each yield no
  fabricated fraction on any surface.
- **G3 — Annotation DB/cache version is captured into provenance.** `AnnotationProvenance`
  gains a `db_version` field; VEP's `cache="…"` token and SnpEff's `##SnpEffCmd`/
  `##SnpEffGenomeVersion` genome DB are parsed into it.
  *Metric:* a VEP fixture with `cache="…/110_GRCh38"` yields `db_version="110_GRCh38"`; a
  SnpEff fixture with a `##SnpEffCmd` genome token yields its DB string; a header lacking the
  token yields `db_version=None` (never fabricated).
- **G4 — DB version renders and reproduces.** The DB version appears in `contig methods`,
  the HTML provenance panel, and the dashboard; it round-trips through the reproduce bundle
  and survives rerun/resume; pre-M5 bundles (no `db_version` key) still load.
  *Metric:* a bundle round-trip test shows `db_version` preserved; a pre-M5 bundle fixture
  loads without error and defaults `db_version=None`.
- **G5 — No regression of M1–M4.** The computed structural/plausibility/concordance checks,
  their parsers, and the verify exit code are behaviorally unchanged; M5 only reads results
  and adds an optional field.
  *Metric:* existing annotation test suites stay green; no exit-code change.

Non-goals for metrics: no FAIL severity, no exit-code change, no new verification primitive,
no calibration on real data.

## User Personas & Scenarios

- **Lone computational biologist (A)** runs sarek somatic with annotation; the verdict card
  now reads "Corroborated by: VEP and SnpEff agree on 47/50 consequences (0.94); gene
  symbols 45/50 (0.90, informational)" — a line she can cite, or a WARN that flags a
  disagreement to inspect.
- **Core facility (C)** wants an auditable, non-expert-legible corroboration signal and the
  annotation DB version on record; both now appear in the HTML report / provenance panel and
  the dashboard.
- **Biotech (D)** wants the annotation cache/DB release pinned in the reproduce bundle for a
  defensible Methods section; `db_version` now round-trips.

All research-use: the line is "two tools agree on the consequence," never "this variant is
pathogenic."

## Requirements

### Must-have

- **M-1 Shared corroboration helper.** A single pure helper (e.g.
  `corroborated_by_line(record) -> str | None`) that reads the existing
  `kind="concordance"` annotation `QCResult`s (`consequence_concordance`,
  `gene_symbol_concordance`) and `record.annotation_identity`, and returns a plain-language
  line naming both annotators + the consequence fraction (+ the informational gene-symbol
  fraction). Returns `None` when there is no computable concordance value (single annotator /
  absent / below floor). **Never recomputes concordance** (G1, G2). Lives in a Python module
  reused by all Python surfaces.
- **M-2 Text report surface.** `report.py:render_run_report` renders the helper's line
  inside the existing `if concordance:` block (after `report.py:107`), only when non-None.
- **M-3 HTML report surface.** `report.py:render_run_report_html` renders the line as a
  `<p class="note">` in the concordance section (between `report.py:280` and `:281`).
- **M-4 `contig methods` surface.** `methods.py:_annotation_clause` (`methods.py:81-103`)
  appends one corroboration sentence sourced from the concordance results (it already names
  both annotators).
- **M-5 Dashboard surface.** The Next.js dashboard concordance card
  (`dashboard/components/run/qc-panel.tsx`, concordance `<Card>` ~188-203) renders the
  corroborated-by line. This requires adding `annotation_identity`
  (`AnnotationProvenance[]`) to `dashboard/lib/types.ts` `RunRecord` (~83-101) and any
  loader that shapes it (`dashboard/lib/runs.ts` / `derive.ts`), plus a small derive helper
  mirroring the Python `corroborated_by_line` (read the concordance rows already present in
  the record's `qc_results`). Minimal: one field, one loader touch, one card line, one
  component test.
- **M-6 `AnnotationProvenance.db_version` field.** Add `db_version: str | None = None` to
  `AnnotationProvenance` (`models.py:206-216`). **No validator change** — the existing
  `_normalize_annotation_identity` `mode="before"` validator (`models.py:310-324`) and the
  Pydantic default cover pre-M5 bundle load (G4).
- **M-7 DB-version header parsing.** Extend `bundle.py:_parse_annotation_header`
  (`bundle.py:113-126`):
  - **VEP**: parse the `cache="…"` token and store its basename (e.g.
    `/vep/homo_sapiens/110_GRCh38` → `110_GRCh38`) as `db_version`. Absent → `None`.
  - **SnpEff**: scan for the genome DB in `##SnpEffCmd` (and/or `##SnpEffGenomeVersion`) and
    store it (e.g. `GRCh38.105`). Absent → `None`.
  - Null-safe throughout; **never fabricate** a version (C5 rule). Tool + tool-version
    parsing is unchanged (G5).
- **M-8 DB-version rendering.** Render `db_version` (when present) in
  `methods.py:_annotation_clause` (~97-98), the HTML "Annotation identity" panel `ann_rows`
  (`report.py:354-356`), and the dashboard provenance surface.
- **M-9 SnpEff DB-version fixture.** Add a `##SnpEffCmd`-style header line carrying a genome
  DB token to the SnpEff fixtures in `tests/test_annotation_provenance.py` (and any
  lifecycle/integration fixture the SnpEff DB path must traverse) — **none exists today**, so
  the SnpEff `db_version` path is untested without it (fixture gap from the dig).
- **M-10 Reproduce round-trip.** `db_version` serializes into `run_record.json` and reloads
  on `rerun`/`resume` (automatic via `model_dump_json`/`model_validate_json`); a pre-M5
  bundle regression test confirms back-compat (G4).
- **M-11 Honest contract.** No exit-code change, no new `FailureClass`, no verification
  primitive. Research-use only: a corroboration line + a DB-version string, never a
  pathogenicity/clinical claim; UNVERIFIED is never rendered as a corroboration.

### Should-have

- **S-1** The corroboration line's WARN/agreement phrasing distinguishes the WARN-capable
  `consequence_concordance` from the informational-only `gene_symbol_concordance` (so a
  low gene-symbol fraction never reads as a failure).
- **S-2** DB-version shown alongside tool version in the same provenance row/cell (one
  legible "VEP v110 · cache 110_GRCh38" style string), not a separate disconnected field.

### Nice-to-have

- **N-1** A short "not corroborated (single annotator)" explicit note when exactly one
  annotator ran (vs. rendering nothing). Default: render nothing; add only if trivial.

## Technical Considerations

- **Read, don't recompute (hard constraint).** The surface line is a pure function of the
  already-computed concordance `QCResult`s + `annotation_identity`. No call into
  `annotation_concordance.py` at render time; M4's compute path is untouched (G5).
- **Provenance is additive.** One optional field; serialization, signature sidecar, and the
  back-compat validator all absorb it with no migration (`bundle.py:23-59`,
  `models.py:310-324`).
- **Cross-language duplication (accepted).** The corroboration line exists twice — a Python
  helper and a small TypeScript derive — because the Python surfaces and the dashboard read
  the record independently. Keep both minimal and tested; the dashboard reads the concordance
  rows already present in `qc_results`, so it needs only `annotation_identity` added to
  `types.ts` for the tool names.
- **Reproducibility impact (positive).** Capturing `db_version` deepens the reproduce
  guarantee — the annotation DB release is now pinned in the bundle, closing a C5-style
  silent-divergence gap.
- **Live-cache caveat (carried from M1–M4).** A live run may not produce a second
  annotation or a cache token at all (SnpEff cache not wired by Contig); in that case there
  is no concordance value and/or no `db_version` — the line omits and `db_version` stays
  `None`. Shippable on synthetic fixtures regardless (no real VEP/SnpEff/sarek in CI).
- **Known resume quirk (pre-existing, flag not fix).** `resume` doesn't pass `assay=` (noted
  in the M4 PRD); M5 changes no assay wiring, so the quirk's blast radius is unchanged.

## Data Model

- `AnnotationProvenance` (`models.py:206-216`): add `db_version: str | None = None`.
  `tool`, `version`, `raw_header` unchanged. `RunRecord.annotation_identity`
  (`list[AnnotationProvenance]`) unchanged in shape.
- Dashboard `dashboard/lib/types.ts`: add `annotation_identity?: AnnotationProvenance[]` to
  `RunRecord` and an `AnnotationProvenance` type (`tool`, `version`, `db_version`).

## Artifact / Run Contracts

- No new `QCResult`s (M5 surfaces the M4 ones). No new check names, no exit-code semantics.
- `run_record.json` gains an optional `annotation_identity[].db_version` string field;
  absent in pre-M5 bundles → `None`.

## Risks & Open Questions

- **R1 — SnpEff DB header spelling unverified against a real run.** The exact
  `##SnpEffCmd` / `##SnpEffGenomeVersion` format is taken from tool docs, not a real sarek
  run (none in CI). Mitigation: parse defensively (accept the genome token where it appears,
  `None` otherwise), and drive with a synthetic fixture whose spelling we commit to; a real
  run that differs degrades to `db_version=None`, never a wrong value.
- **R2 — VEP cache-token → DB-version mapping is heuristic.** `cache="…/110_GRCh38"` basename
  is the pragmatic DB identifier; it is the cache release, not a per-database (ClinVar/gnomAD)
  version. Mitigation: store it honestly as the cache identifier and label it as such in the
  render; do not over-claim it is a ClinVar/gnomAD version.
- **R3 — Dashboard type/loader drift.** Adding `annotation_identity` to `types.ts` must match
  the serialized JSON shape (list of objects). Mitigation: a component/loader test over a
  real `run_record.json`-shaped fixture.
- **R4 — Empty-state wording.** Resolved default: render nothing when no computable
  concordance value; N-1 optional explicit note only if trivial.
- **Open:** whether S-2's combined "tool · cache" render string is preferred over two cells
  — default to the combined legible string, confirm in the plan.

## Out of Scope

- **Folding annotation outcomes into the C6 eval corpus (the third M5 sub-part) — DEFERRED,
  blocked.** The C1/C3/annotation corroboration signals carry no ground-truth labels, so they
  need a labeling design before joining `eval-guard`/`heal-guard` (deferred across v0.17.0 /
  v0.22.0). Do not build in this slice.
- FAIL severity on any annotation concordance band (still uncalibrated).
- Wiring a SnpEff/VEP cache or `--step annotate` (the live-cache fix); M5 stays honest via
  omission / `None` when annotation didn't run.
- Per-database (ClinVar/gnomAD) version extraction beyond the cache/genome identifier.
- Any new verification primitive, model, or `QCResult`.
- Research prioritization (ACMG, PGx, PRS) — deferred per the initiative's verify-only line.

## Guardrail check (CLAUDE.md)

On-thesis Layer-2 verify/reproduce **surfacing + provenance**, not Layer-1 authoring. No
wet-lab/clinical credentials, no proprietary data, no new model. Research-use only — a
corroboration line and a DB-version string, never a pathogenicity/clinical verdict;
UNVERIFIED never rendered as PASS. Compounds the reproduce guarantee (moat).

# PRD — Research report builder (M4)

Feature slug: `report-builder` · Type: feat · Owner: aliz
Branch: `feat/report-builder/aliz` · Capability: **M4 (Beyond Genomist)**
Status: drafted 2026-11-07

## Problem Statement

Contig can verify a run, build a variant table (M1), and check coverage/readiness
(M2), but the user still has to assemble the story: methods, verdict, QC,
evidence, limitations, and who reviewed it. That assembly is manual, easy to get
wrong, and usually loses the link back to the run bundle.

M4 adds a **research report builder**: one command that turns a run bundle plus
optional M1/M2 tables and a small narrative spec into a self-contained HTML
report and a machine-readable sidecar. Every section names its source and
SHA-256; the report can be checked for staleness when an input changes.

It is a **research report**, not a clinical report. No diagnosis, ACMG
classification, treatment recommendation, or medical sign-off.

**Who has the problem:** the disease-research ICP who needs to hand a PI,
collaborator, or reviewer a defensible summary without rebuilding it in Word.

**Why now:** M1 and M2 now produce the evidence; M4 is the last mile that makes
the result shareable.

## Goals & Success Metrics

- **G1 — One command.** `contig report <run-id>` builds a self-contained HTML
  report plus a JSON sidecar from the run bundle and optional tables.
- **G2 — Traceability.** Every section names its input source and SHA-256; the
  sidecar records the exact inputs, spec, Contig version, and report hash.
- **G3 — Editable narrative.** A JSON spec supplies title, summary, notes,
  limitations, author/institution, reviewer, template, and row caps.
- **G4 — Staleness check.** `contig report-check <sidecar>` recomputes input
  hashes and says current/stale.
- **G5 — Research-use boundary.** The report carries a clear research-use banner
  and never claims a diagnosis or a Contig-authored pathogenicity call.

## Requirements

### Must-have (v1)

- **Run bundle input:** `--run-id` + `--runs-dir` (default `runs`); renders
  pipeline/revision, verdict, QC checks, methods paragraph, provenance, and
  signature status.
- **Optional M1 input:** `--variants <json>` from `contig variants --json`;
  renders a summary (counts, ClinVar buckets) and a capped variant table.
- **Optional M2 input:** `--readiness <json>` from `contig readiness --json`;
  renders readiness counts and a capped target table.
- **Narrative spec:** `--spec <json>` with `title`, `subtitle`, `author`,
  `institution`, `summary`, `notes`, `limitations`, `template`, `reviewer`,
  `max_rows`. Missing fields fall back to safe defaults.
- **Templates:** `publication`, `internal`, `audit`; each selects a section set.
- **Output:** self-contained HTML (`--out`, default `runs/<id>/report.html`) and
  a JSON sidecar (`--meta`, default `runs/<id>/report.json`).
- **Provenance:** sidecar lists each input path + SHA-256, the spec, thresholds
  used by M2 if present, Contig version, generated timestamp, and HTML SHA-256.
- **Check:** `contig report-check <sidecar>` reports current/stale per input.
- **Tests:** synthetic run bundle + M1/M2 JSON fixtures; no network.

### Should-have (later slices)

- PDF export (browser print is the v1 path).
- Report diff between two sidecars.
- Reviewer comments per section.
- Figure embedding (QC plots/coverage plots).
- A dashboard "Build report" button.
- DOCX export.

### Nice-to-have / explicit non-goals

- Clinical report language, diagnosis, ACMG adjudication, treatment advice.
- A full document editor.
- A signature workflow that claims medical sign-off.
- Model-generated narrative (the M5 assistant may draft text later, but the
  report must render without a model).

## Technical Considerations

- **No new dependencies.** HTML is built with stdlib string templates and
  `html.escape`; no Jinja, no PDF library.
- **Self-contained.** Inline CSS, no external assets, no raw reads. Only metadata,
  tables, and hashes.
- **Attribution.** The report labels M1/M2 sections with the source file and
  hash; ClinVar values remain "ClinVar reports …".
- **Reproducibility.** The sidecar is the audit artifact; the HTML hash lets a
  reviewer confirm the rendered file. `report-check` recomputes inputs.
- **Caps.** Variant/readiness tables are capped (`max_rows`, default 100) with a
  note; the full data stays in the attached JSON.

## Risks & Open Questions

- **R1 — report implies clinical authority.** Mitigation: research-use banner,
  "not a clinical report" wording, reviewer block labeled "research review".
- **R2 — stale inputs.** Mitigation: sidecar hashes + `report-check`.
- **R3 — huge tables.** Mitigation: cap rows; link to the full JSON.
- **R4 — HTML injection.** Mitigation: escape every user-provided string.
- **Open:** is HTML enough, or is PDF required for the first user? (v1: HTML +
  browser print; PDF is a follow-up.)

## Out of Scope

- Clinical diagnosis, ACMG classification, treatment recommendations.
- PDF/DOCX export, dashboard, report diffing (v1).
- Model-generated narrative.

## Acceptance

- `contig report r1 --variants variants.json --readiness readiness.json --spec
  spec.json --out report.html --meta report.json` produces a self-contained HTML
  report and a sidecar.
- The HTML contains the run verdict, QC checks, methods, attached variant and
  readiness summaries/tables, provenance hashes, reviewer block, and the
  research-use banner.
- `contig report-check report.json` says current; after changing an input, it
  says stale and names the file.
- A missing run or input exits non-zero with a clear message.
- No output claims a diagnosis or a Contig-authored pathogenicity call.

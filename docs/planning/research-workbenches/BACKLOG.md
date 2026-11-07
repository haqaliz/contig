# Research workbenches wrap-up backlog

**Status 2026-11-08:** all eight milestones have a v1. There are no open code
rows: every remaining row is **deferred** (post-v1, no user asking yet) or
**blocked** on evidence/data a design partner or reviewer must supply. See
`WRAP_UP.md` for the narrative and `BLOCKED_RUNBOOK.md` for the exact evidence.

Status legend: `done` · `deferred` (post-v1, not blocked) · `blocked` (needs
real data/reviewer/legal) · `decision` (deliberately not building).

| ID | Milestone | Item | Status |
|---|---|---|---|
| M1-0 | M1 | `contig variants` workbench (ClinVar/Iranome/frequency, filters, TSV/JSON, spec replay) | done |
| M1-1 | M1 | gnomAD GraphQL client + local cache | deferred |
| M1-2 | M1 | Real annotated VCF from a design partner (VEP/SnpEff) | blocked |
| M1-3 | M1 | Iranome GRCh37 → GRCh38 liftover | deferred |
| M1-4 | M1 | Dashboard variant table | deferred |
| M1-5 | M1 | Filter/sort semantics review with a researcher | blocked |
| M2-0 | M2 | `contig readiness` per-target coverage/readiness | done |
| M2-1 | M2 | Direct BAM/CRAM ingestion (`samtools depth` seam) | deferred |
| M2-2 | M2 | Sex check / sample-swap readiness caveats | deferred |
| M2-3 | M2 | Threshold calibration (20x, 90%, 50%) on real panels | blocked |
| M2-4 | M2 | Homology/pseudogene list expansion | deferred |
| M3-0 | M3 | `contig panel-build`/`panel-list`/`panel-show` | done |
| M3-1 | M3 | Panel versioning/archival + diff | deferred |
| M3-2 | M3 | Real lab panel validation | blocked |
| M4-0 | M4 | `contig report` + `report-check` (HTML, sidecar, templates) | done |
| M4-1 | M4 | Native PDF export | deferred |
| M4-2 | M4 | Report diff between sidecars | deferred |
| M4-3 | M4 | Reviewer workflow feedback / report examples | blocked |
| M5-0 | M5 | `contig ask` + `ask-eval` (deterministic, citations, optional LLM) | done |
| M5-1 | M5 | Live LLM eval + provider/privacy decision | blocked |
| M5-2 | M5 | Action execution behind the approval gate | deferred |
| M5-3 | M5 | Dashboard chat panel | deferred |
| M6-0 | M6 | `contig family` inheritance/Mendelian/de novo/concordance | done |
| M6-1 | M6 | X-linked/sex-aware Mendelian rules | deferred |
| M6-2 | M6 | Multiple families/quads per PED | deferred |
| M6-3 | M6 | Carrier/couple views + recessive panels | deferred |
| M6-4 | M6 | Real trio validation + swap-threshold calibration | blocked |
| M7-0 | M7 | `contig biomarkers` TMB verification | done |
| M7-1 | M7 | Independent MSI caller + MSI-H/MSS reference data | blocked |
| M7-2 | M7 | LOH/CNV verification (FACETS/CNVkit + truth set) | blocked |
| M7-3 | M7 | TMB tolerance/band calibration | blocked |
| M8-0 | M8 | `contig cohort-build`/`cohort-query` local-only | done |
| M8-1 | M8 | Federated/cross-lab frequency layer | blocked |
| M8-2 | M8 | Dashboard cohort view | deferred |
| X-1 | Cross | Dashboard integration for M1–M8 surfaces | deferred |
| X-2 | Cross | Streaming/scale mode for large VCF/depth files | deferred |
| X-3 | Cross | Design-partner validation of all defaults | blocked |
| X-4 | Cross | Release 1.1.0 (version bump + release notes) | deferred |
| X-5 | Cross | Clinical diagnosis / ACMG adjudication / drug recs | decision |

**Totals:** 8 built · 18 deferred · 12 blocked · 1 decision (39 rows). No row is
an unfinished code task; every blocked row names its evidence in
`BLOCKED_RUNBOOK.md`.

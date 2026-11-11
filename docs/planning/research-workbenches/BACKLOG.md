# Research workbenches wrap-up backlog

**Status 2026-11-11:** all eight milestones have a v1, the read-only research
dashboard ships, and report sidecars can be signed. Rows with public-data or
agent evidence are **provisional**: usable, but not partner/reviewer-calibrated.
One row remains blocked on the human validation gate, and three are deliberate
decisions. See `WRAP_UP.md` for the narrative, `BLOCKED_RUNBOOK.md` for the
exact evidence, and `docs/validation/DATA_AND_PARTNER_ACQUISITION.md` for the
open-data and permission/contact plan.

Status legend: `done` · `provisional` (public-data/agent evidence; partner or
reviewer still pending, so not calibrated) · `blocked` (needs real
data/reviewer/legal) · `decision` (deliberately not building).

| ID | Milestone | Item | Status |
|---|---|---|---|
| M1-0 | M1 | `contig variants` workbench (ClinVar/Iranome/frequency, filters, TSV/JSON, spec replay) | done |
| M1-1 | M1 | gnomAD GraphQL client + local cache (`--gnomad-api`, 1000-site cap) | done |
| M1-2 | M1 | Real annotated VCF from a design partner (VEP/SnpEff); public GIAB/SnpEff validation done | provisional (public GIAB/SnpEff; partner VCF pending) |
| M1-3 | M1 | Iranome GRCh37 → GRCh38 liftover | done |
| M1-4 | M1 | Dashboard variant table | done |
| M1-5 | M1 | Filter/sort semantics review with a researcher | provisional (deterministic defaults + agent validation; human review pending) |
| M2-0 | M2 | `contig readiness` per-target coverage/readiness | done |
| M2-1 | M2 | Direct BAM/CRAM ingestion (`contig readiness --bam`) | done |
| M2-2 | M2 | Sex check / sample-swap readiness caveats | done |
| M2-3 | M2 | Threshold calibration (20x, 90%, 50%) on real panels (nf-core CRAM + BED available) | provisional (nf-core CRAM run; lab expectations pending) |
| M2-4 | M2 | Homology/pseudogene list expansion | done |
| M3-0 | M3 | `contig panel-build`/`panel-list`/`panel-show` | done |
| M3-1a | M3 | Panel version label (`--version`, listed in the registry) | done |
| M3-1b | M3 | Panel archival + diff | done |
| M3-2 | M3 | Real lab panel validation | provisional (PanelApp panel; lab BED/transcript policy pending) |
| M4-0 | M4 | `contig report` + `report-check` (HTML, sidecar, templates) | done |
| M4-1 | M4 | Native PDF export | decision (browser print-to-PDF only) |
| M4-2 | M4 | Report diff between sidecars (`contig report-diff`) | done |
| M4-3 | M4 | Reviewer workflow feedback / report examples | provisional (agent-generated reports; redacted lab reports/reviewer pending) |
| M5-0 | M5 | `contig ask` + `ask-eval` (deterministic, citations, optional LLM) | done |
| M5-1 | M5 | Live LLM eval + provider/privacy decision (local `qwen2.5:1.5b` 9/9 with the fidelity guard; local-only default decided) | done (local-only default; hosted provider not used) |
| M5-2 | M5 | Action execution behind the approval gate | done |
| M5-3 | M5 | Dashboard chat panel | done |
| M6-0 | M6 | `contig family` inheritance/Mendelian/de novo/concordance | done |
| M6-1 | M6 | X/Y/MT sex-aware Mendelian rules (basic; unknown sex not_evaluated) | done |
| M6-2 | M6 | Multiple families/quads per PED | done |
| M6-3 | M6 | Carrier/couple views + recessive panels | done |
| M6-4 | M6 | Real trio validation + swap-threshold calibration (full GIAB trio: 2.26M evaluated, 19 residual inconsistencies in no-inconsistent regions, IBS0=0) | done |
| M7-0 | M7 | `contig biomarkers` TMB verification | done |
| M7-1a | M7 | MSI caller seam: parse MSIsensor output or run tumor/normal BAMs; threshold + reported-status comparison | done |
| M7-1b | M7 | Real MSI-H/MSS pair validation + threshold calibration (MSIsensor example data + TCGA baseline available) | provisional (MSIsensor example output + TCGA baseline; real pair pending) |
| M7-2a | M7 | CNV segment concordance (`--cnv-segments/--cnv-truth`) | done |
| M7-2b | M7 | LOH verification (`--loh-segments/--loh-truth` comparator shipped; real caller validation needs a run's allele-specific segments) | provisional (open TCGA-COAD ASCAT self-comparison; real caller pending) |
| M7-3 | M7 | TMB tolerance/band calibration (SEQC2 TMB computed; reviewer needed) | provisional (SEQC2 TMB 15.87; reviewer band pending) |
| M8-0 | M8 | `contig cohort-build`/`cohort-query` local-only | done |
| M8-1 | M8 | Federated/cross-lab frequency layer | decision (PRD-only; no code until 2 labs + consent/legal) |
| M8-2 | M8 | Dashboard cohort view | done |
| X-1 | Cross | Dashboard integration for M1–M8 surfaces (read-only) | done |
| X-1b | Cross | Auto-discovery from the run bundle + report/variant/readiness actions | done (read-only manifest auto-discovery; actions deferred) |
| X-2 | Cross | Streaming/scale mode for large VCF/depth files | done (M1 cap + streaming depth filtering) |
| X-3 | Cross | Design-partner validation of all defaults | blocked (human gate: 3/5 partners, trust ≥4) |
| X-4 | Cross | Release 1.1.0 (version bump + release notes) | done |
| X-5 | Cross | Clinical diagnosis / ACMG adjudication / drug recs | decision |

**Totals:** 31 done · 8 provisional · 1 blocked · 3 decisions (43 rows).
Provisional rows are not calibrated; the partner/reviewer ask stays open in
outreach. The one blocked row is the human validation gate.

## Agent-validation follow-ups (2026-11-08)

These came from the four synthetic persona runs
(`docs/validation/AGENT_VALIDATION_FINDINGS.md`). They are not counted in the
milestone totals above.

- Signed report manifest (HTML + sidecar + reviewer) using the Ed25519 keypair —
  **shipped (Unreleased);** `report-check` verifies it and `--require-signature`
  rejects unsigned reports.
- `report-check --outputs --sources --base-dir`; recurse into M1/M2 sources —
  **shipped (Unreleased);** unrecorded sets are `unverified`, never a false pass.
- Report compatibility preflight for assay/build/gene mismatch —
  **shipped (Unreleased);** HTML, sidecar, and stderr warnings, never blocking.
- Portable report bundle (HTML + sidecar + attached tables) —
  **shipped (Unreleased):** `contig report-bundle` writes relative paths and
  keeps every table row.
- Panel archival/diff and GTF/HGNC source hashes in panel metadata —
  **shipped (Unreleased):** `panel-diff`, `panel-archive`, and `meta.sources`.
- Cohort append/list/merge and opt-in contributing-run labels —
  **shipped (Unreleased):** `--trace`, `cohort-list`, `cohort-append`,
  `cohort-merge`, and the query `run_labels` column.
- Batch report/check and a project/workspace manifest —
  **shipped (Unreleased):** `report-batch`, `report-check-batch`, and
  manifest-relative path resolution.
- Readiness build matching, caveat coverage, and BED3 gene-annotation guidance —
  **shipped (Unreleased):** `--build`, explicit caveat meta, and preflight notes.
- WGS region/gene guard and explicit record cap —
  **shipped (Unreleased):** streaming `--region`/`--gene` bound plus a
  1,000,000-record default cap that names the flags.

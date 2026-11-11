# Research workbenches wrap-up: where M1–M8 stand

**Status 2026-11-11:** all eight milestones have a shippable v1. The engine,
CLI, docs, and synthetic tests are in place. The ledger is **31 done · 8
provisional · 1 blocked · 3 decisions**: provisional means public-data or agent
evidence only, not partner/reviewer calibration. What remains is human
validation and integration — not unfinished code.

No open code row: `BACKLOG.md` is the row-level ledger; `BLOCKED_RUNBOOK.md`
names the evidence each provisional or blocked row still needs.

## What shipped

| Milestone | Command | What it does | Tests | Honest limit |
|---|---|---|---|---|
| M1 | `contig variants` / `contig iranome-lift` | ClinVar/Iranome/frequency/gnomAD-API join, deterministic filters, TSV/JSON + provenance, spec replay, Iranome GRCh37→GRCh38 liftover | 56 | In-memory table; gnomAD API capped at 1000 sites; Iranome liftover is chain-dependent; public GIAB/SnpEff shape only, partner VCF pending |
| M2 | `contig readiness` | Per-target depth from a TSV or BAM/CRAM, %≥20x/50x/100x, expanded 33-gene homology/pseudogene caveats, VCF sex check / possible swap, ready/caution/not-interpretable | 61 | Public nf-core CRAM only; lab thresholds pending; sex check is VCF-only; caveat BED uses one representative transcript per gene |
| M3 | `contig panel-build`/`panel-list`/`panel-show`/`panel-diff`/`panel-archive` | HGNC-resolved, MANE-preferred, checksummed panel BED registry with version labels, source hashes, diff and archive | 24 | PanelApp public panel only; no lab-specific BED/transcript policy |
| M4 | `contig report`/`report-check`/`report-diff` | Self-contained HTML report, sidecar hashes, templates, reviewer block, staleness check, sidecar diff | 37 | HTML only; agent-generated reports, no redacted lab reports/reviewer |
| M5 | `contig ask`/`ask-eval` | Grounded Q&A over the bundle + M1/M2, citations, suggested actions, approval-gated action execution, optional LLM paraphrase | 52 | Local-only default; `qwen2.5:1.5b` eval 9/9 after the fidelity guard; no hosted provider |
| M6 | `contig family` / `contig carriers` | Inheritance, autosomal + basic X/Y/MT Mendelian consistency, de novo candidates, pairwise concordance, multiple families/quads, carrier/couple views | 25 | Full GIAB trio validated (2.26M evaluated, 19 residual inconsistencies in no-inconsistent regions, IBS0=0); carrier/couple views are autosomal only |
| M7 | `contig biomarkers` | TMB from PASS variants in a callable BED; MSI from MSIsensor output/BAMs; CNV segment concordance; LOH from allele-specific segments | 32 | MSIsensor example + TCGA baseline; real MSI pair pending; LOH self-comparison only; TMB 15.87, reviewer band pending |
| M8 | `contig cohort-build`/`cohort-query` | Local-only per-variant/gene cohort counts and frequencies | 16 | Decision: PRD-only; no federated/cross-lab code |

All merged to `origin/master`; the full test suite is green. Docs are in
`docs/USAGE.md`, each milestone's `docs/planning/<slug>/prd.md` + `plan-m1.md`,
and the `CHANGELOG.md` Unreleased section.

### Manual real-data smoke

`OUT=/tmp/contig-research-smoke bash scripts/smoke_research_workbenches.sh` runs
all eight surfaces over the downloaded data (not CI). It exercises:

- M1: 32,736-row table from the Kaggle sample VCF + ClinVar.
- M2: 200 nf-core chr20 targets from the CRAM via samtools (3 ready, 4 caution,
  193 not-interpretable).
- M3: 322-exon BRCA1/BRCA2 panel from real HGNC + GENCODE.
- M4/M5: report + `report-check` current + `report-diff` no differences;
  grounded `ask` answer for GENE3.
- M6: real GIAB Ashkenazim trio subset, 399 rows, 217 evaluated, 0 Mendelian
  inconsistencies, 0 de novo candidates.
- M7: TMB 15.87 mut/Mb on the SEQC2 truth set; MSI 100.00% (match) from the
  MSIsensor example; CNV verification available; LOH `not_verified`.
- M8: local cohort across three M1 tables, 3 variants / 3 genes / 3 runs.

This is the closest thing to validation we can do without a design partner; it
proves the plumbing, not that the defaults are scientifically right.

### Agent-persona validation

Four synthetic personas ran the CLI on real fixtures/data
(`docs/validation/AGENT_PARTNERS.md`, reports in
`docs/validation/agent-runs/`). They found and we fixed: panel-version overwrite,
cohort duplicate double-counting, report HTML-hash verification, cwd-relative
sidecars, the misleading “signed” label, missing report evidence columns,
non-runnable `ask` actions, the generic-frequency mislabel, the panel-list
header, and the missing gene-level readiness summary. Remaining findings are in
`docs/validation/AGENT_VALIDATION_FINDINGS.md`; they are backlog, not dashboard
blockers.

## What is deliberately not built

- **Clinical diagnosis, ACMG adjudication, drug/treatment recommendations, a
  patient portal.** The research-use boundary is the moat, not a gap.
- **Federated/cross-lab frequency.** Needs multi-lab demand, consent/IRB, a
  privacy method, tenancy/audit, and legal review.
- **Model training.** Nothing needs one; M5's LLM is optional and only
  paraphrases a grounded answer.
- **A full document editor, PDF/DOCX export, dashboard for every surface.** These
  are post-v1 product work, not correctness work.

## What is still provisional or blocked

| Item | Status | Evidence still needed |
|---|---|---|
| M1-2 real annotated VCF | provisional | A design partner's annotated VCF (public GIAB/SnpEff shape done) |
| M1-5 filter/sort review | provisional | A researcher's review of the deterministic defaults |
| M2-3 threshold calibration | provisional | Real panel/WES runs with expected coverage + reviewer |
| M3-2 real panel | provisional | One real lab panel BED + transcript policy |
| M4-3 report feedback | provisional | 2–3 redacted report examples + reviewer workflow |
| M5-1 hosted LLM | done (local-only) | No hosted provider by decision; local `qwen2.5:1.5b` eval 9/9 |
| M7-1b real MSI pair | provisional | A real MSI-H/MSS tumor/normal pair + threshold |
| M7-2b real LOH caller | provisional | A real run's allele-specific segments |
| M7-3 TMB band | provisional | A domain reviewer and expected band |
| M8-1 federation | decision | No code until 2+ labs, consent/IRB, privacy, legal |
| X-3 human validation | blocked | 3–5 partners complete core tasks with trust ≥4 |

## What I recommend next

1. **Design-partner validation (P0).** Use
   `docs/validation/DESIGN_PARTNER_KIT.md`. Pick 3–5 researchers/labs, have them
   run their own data through the commands, and measure time-to-result, trust,
   which filters/thresholds they challenge, and willingness to pay. This is the
   roadmap's own gate. Source and contact routes are in
   `docs/validation/DATA_AND_PARTNER_ACQUISITION.md`; keep
   `docs/validation/acquisition_tracker.csv` current.
2. **Upgrade provisional rows (P1).** Supply the evidence in the table above:
   partner VCF, lab panel/BED, redacted reports, real MSI/LOH/TMB review. There
   is no queued feature work; each upgrade is evidence-driven.
3. **M5 local-only default (done).** No hosted provider. Revisit only with a new
   explicit provider/privacy decision.
4. **M8 federation (decision).** No code until 2+ labs and legal/privacy
   approve.

## How to resume

- There are no deferred code rows. Start from a `provisional` row only when its
  evidence in `BLOCKED_RUNBOOK.md` exists.
- X-3 is the human gate: do not call the defaults calibrated until 3–5 partners
  complete the core tasks with trust ≥4.
- The discipline stays: test-first, one commit per item, full suite green, no
  clinical over-claiming.

## What “done” means here

M1–M8 v1 means **the product surface exists and is deterministic, attributed, and
tested**. It does not mean the defaults are calibrated or that a real researcher
has trusted the output. Those are the next milestones, and they need people and
data, not more code.

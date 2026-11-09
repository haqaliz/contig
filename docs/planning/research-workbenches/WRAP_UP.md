# Research workbenches wrap-up: where M1–M8 stand

**Status 2026-11-08:** all eight milestones have a shippable v1. The engine,
CLI, docs, and synthetic tests are in place; what remains is **validation,
integration, and the deliberately deferred parts** — not unfinished code.

No open code row: `BACKLOG.md` is the row-level ledger; `BLOCKED_RUNBOOK.md`
names the evidence each blocked row needs.

## What shipped

| Milestone | Command | What it does | Tests | Honest limit |
|---|---|---|---|---|
| M1 | `contig variants` | ClinVar/Iranome/frequency/gnomAD-API join, deterministic filters, TSV/JSON + provenance, spec replay | 56 | In-memory table; gnomAD API capped at 1000 sites; Iranome GRCh37 only |
| M2 | `contig readiness` | Per-target depth from a TSV or BAM/CRAM, %≥20x/50x/100x, homology caveats, ready/caution/not-interpretable | 39 | Thresholds uncalibrated |
| M3 | `contig panel-build`/`panel-list`/`panel-show` | HGNC-resolved, MANE-preferred, checksummed panel BED registry with version labels | 24 | No archival/diff; no real lab panel |
| M4 | `contig report`/`report-check`/`report-diff` | Self-contained HTML report, sidecar hashes, templates, reviewer block, staleness check, sidecar diff | 37 | HTML only; no PDF/dashboard |
| M5 | `contig ask`/`ask-eval` | Grounded Q&A over the bundle + M1/M2, citations, suggested actions, optional LLM paraphrase | 31 | No live LLM eval; deterministic router only |
| M6 | `contig family` | Inheritance, autosomal + basic X/Y/MT Mendelian consistency, de novo candidates, pairwise concordance | 25 | Full GIAB trio validated (2.26M evaluated, 19 residual inconsistencies in no-inconsistent regions, IBS0=0); multiple families/quads still deferred |
| M7 | `contig biomarkers` | TMB from PASS variants in a callable BED; MSI from MSIsensor output/BAMs; CNV segment concordance | 32 | LOH is `not_verified`; MSI/CNV thresholds need real validation |
| M8 | `contig cohort-build`/`cohort-query` | Local-only per-variant/gene cohort counts and frequencies | 16 | No federated/cross-lab layer |

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

## What is blocked, and on what

| Blocked item | Evidence needed |
|---|---|
| M1 filter/sort review; M1 real annotated VCF | A design partner's annotated VCF + feedback on filters |
| M2 threshold calibration | Real panel/WES runs with expected coverage and a reviewer |
| M3 real panel | One real lab panel BED + expected behavior |
| M4 report feedback | 2–3 redacted report examples + reviewer workflow |
| M5 live LLM eval | Provider/privacy decision + a real eval run |
| M6 real trio/swap threshold | A real multi-sample trio VCF + expected inheritance |
| M7 MSI/CNV calibration + LOH | A real MSI-H/MSS pair + threshold; a real CNV segment file + expected calls; LOH needs allele-specific data |
| M7 TMB band | A domain reviewer and real tumor-normal TMB values |
| M8 federated layer | 2+ labs, consent/IRB, privacy design, legal review |
| Cross-cutting validation | A design partner running their own data through M1–M8 |

## What I recommend next

1. **Design-partner validation (P0).** Use
   `docs/validation/DESIGN_PARTNER_KIT.md`. Pick 3–5 researchers/labs, have them
   run their own data through the commands, and measure time-to-result, trust,
   which filters/thresholds they challenge, and willingness to pay. This is the
   roadmap's own gate. Source and contact routes are in
   `docs/validation/DATA_AND_PARTNER_ACQUISITION.md`; keep
   `docs/validation/acquisition_tracker.csv` current.
2. **Dashboard/auto-discovery integration (P1).** Make the new surfaces usable
   without manually passing `--variants`/`--readiness`/`--vcf`: auto-discover
   from the run bundle, add report/variant/readiness actions.
3. **M7 follow-up (P1).** Acquire HCT116/SW480 data, wire an MSI caller, then
   LOH/CNV segments. Keep the no-drug rule.
4. **Scale/performance (P2).** Add streaming or explicit record caps for large
   VCF/depth inputs before a WGS design partner arrives.
5. **M8 federation design (P3).** Only after two labs ask. Design doc first; no
   code.

## How to resume

- Pick a `deferred` row from `BACKLOG.md` if you want a code task.
- Pick a `blocked` row only after its `BLOCKED_RUNBOOK.md` evidence exists.
- The discipline stays: test-first, one commit per item, full suite green, no
  clinical over-claiming.

## What “done” means here

M1–M8 v1 means **the product surface exists and is deterministic, attributed, and
tested**. It does not mean the defaults are calibrated or that a real researcher
has trusted the output. Those are the next milestones, and they need people and
data, not more code.

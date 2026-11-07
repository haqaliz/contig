# Beyond Genomist: milestone plan and required context

Status: planning only. Nothing here is committed or scheduled.
Purpose: turn the Genomist gap analysis into a sequenced set of milestones, and
record for each one **what we must know, obtain, or decide before a build session
can start** — data, models, licenses, code to reuse, and open questions.

Read first, every session:

- `docs/planning/beyond-genomist/DATA_SOURCES.md` — the verified data inventory,
  licenses, Persian/Iranian sources, and what is already downloaded in `data/`.
- `CLAUDE.md` — the wedge and the four strategic constraints.
- `docs/technical/USE_CASE_UNIVERSE.md` — the research-use bright line.
- `docs/technical/CAPABILITY_ROADMAP.md`, section C7 — what variant annotation
  already ships, and the explicit "prioritization deferred" note.
- `docs/technical/ADD_AN_ASSAY.md` — the data-driven assay recipe.
- `src/contig/models.py`, `src/contig/report.py`, `src/contig/cli.py`,
  `src/contig/verification/` — the surfaces each milestone extends.

---

## The one rule that shapes all of this

Contig stays **Layer 2**: run, verify, reproduce, and surface evidence. It does
not diagnose, adjudicate pathogenicity, recommend treatment, or sign a clinical
report. Every milestone below is framed as **research-use verification and
evidence presentation**, even where the inspiration (Genomist) is clinical.

If a milestone cannot be built without crossing that line, it is either
re-scoped or dropped. That is a feature, not a limitation: it is the moat.

---

## Milestone summary

| # | Milestone | Needs new data? | Needs a trained model? | Effort | Depends on |
|---|---|---|---|---|---|
| M1 | Variant workbench (prioritization + evidence table) | Yes — annotated VCFs + public DBs | No (deterministic; optional published scores) | M–L | C7 annotation ship |
| M2 | Coverage & interpretation-readiness workbench | Yes — coverage/BED/GTF + truth intervals | No | M | M1 data model |
| M3 | Panel builder + panel registry | Yes — panel BEDs, gene lists, GTF | No | S–M | M2 (coverage checks) |
| M4 | Research report builder ("self-proving report") | No new science data; needs report templates + design input | No | M | M1–M3 |
| M5 | Ask-your-run assistant | Yes — a grounded eval set of run bundles | Yes — an LLM (API or local), no training required initially | M | M4 bundle fields |
| M6 | Family analysis (trio / carrier / couple) | Yes — trio VCFs, PED, HPO terms | No | M–L | M1 |
| M7 | Oncology biomarker verification (MSI/TMB/LOH/CNV) | Yes — reference cell lines / truth sets | No | M–L | Existing somatic assay |
| M8 | Cohort / federated frequency layer | Yes — multi-lab aggregates + consent model | No (statistics/privacy, not ML) | L | Team/workspace backend |

Sequencing rationale: M1–M4 complete the "last mile" from a verified run to a
usable, shareable result. M5–M7 add depth on top of that surface. M8 is a
network-effect play and should wait for real multi-lab demand.

---

## Shared context (applies to every milestone)

### Data and files that will be needed repeatedly

- **Reference genomes**: GRCh38 (primary), GRCh37 (legacy), plus a small
  non-model genome for honesty tests. Prefer iGenomes/Ensembl sources already
  used by nf-core. Record build + source + checksum in provenance.
- **Annotation caches**: VEP cache (~25 GB full; a smaller subset for tests) and
  SnpEff database. The engine already downloads these per pipeline revision;
  keep the same pattern.
- **Gene/transcript models**: GTF/GFF3 for gene, exon, transcript, and
  MANE Select mapping. Needed for per-gene coverage, panel validation, and
  consequence display.
- **Public variant databases**: ClinVar (free), gnomAD (free, large — use
  tabix/remote or a subset), HPO (free), ClinGen (free), CIViC (free, cancer),
  GeneReviews/NCBI Bookshelf (free). These are display-and-attribute sources,
  never Contig's own judgment.
- **Test data**: GIAB HG002/HG003/HG004 trio (public), NA12878 (public data),
  nf-core test profiles, sarek test data, and small synthetic VCFs. Every
  verifier stays synthetic-fixture-first in CI, as the repo already does.
- **Licensing landmines**: OMIM, NCCN, COSMIC, HGMD, CADD (commercial),
  SpliceAI (commercial terms), OncoKB (commercial), InterVar (check). Do not
  embed their content without a license. Prefer open equivalents and link out.

### Existing code to reuse (do not rebuild)

- VCF reading patterns: `verification/variant_metrics.py`,
  `verification/annotation_structural.py`,
  `verification/annotation_plausibility.py`,
  `verification/annotation_concordance.py`,
  `verification/somatic_plausibility.py`, `verification/sex_plausibility.py`.
- Verdict model: `models.QCResult`, `models.overall_verdict`,
  `report.explain_verdict`.
- Provenance: `AnnotationProvenance`, `ReferenceIdentity`, `RunRecord`,
  `bundle.py`, `signing.py`.
- Report surfaces: `report.render_run_report`, `render_run_report_html`,
  `render_explain`, `render_reproduction`.
- Dashboard: read-only run/eval/reproduce pages under `dashboard/app/`.
- Assay onboarding: `docs/technical/ADD_AN_ASSAY.md` + `registry.py`.

### Cross-cutting decisions still open

1. **Where does curated content live?** In-repo JSON/TSV (simple, versioned) vs.
   a local SQLite cache vs. a service. Recommendation: in-repo definitions +
   generated cache, no server for M1–M7.
2. **Dependency policy.** The engine is deliberately stdlib-only. M2/M3/M7 may
   want `pysam`, `pybedtools`, or a PDF library. Decide per milestone whether to
   add a dependency or write a small stdlib parser; do not add one casually.
3. **UI surface.** CLI first, dashboard second, matching the existing pattern.
   M1/M2 need a real interactive surface; decide whether it is a new dashboard
   page or a static report first.
4. **Workspaces/auth.** M8 needs multi-user; today the dashboard is
   localhost-only. Do not build auth before a design partner needs it.
5. **Persian/RTL.** Genomist's local advantage is Persian. Contig does not need
   it to win the engineering layer, but if the Iranian market matters, RTL and
   Persian report templates are a small, separate frontend slice. Decide later.
6. **Review/sign-off semantics.** Research-use "reviewed by" is a workflow and
   audit feature, not a medical act. Keep the wording explicit.

---

## M1 — Variant workbench (research-use prioritization)

**Status:** v1 implemented 2026-11-07 — `contig variants`, with PRD and task plan
in `docs/planning/variant-workbench/`.

**Goal.** After a verified variant/annotation run, let a researcher see the
annotated call set, filter and prioritize it, and inspect the evidence behind
each row — without Contig claiming what is pathogenic.

**In scope**

- Read the run's annotated VCF (VEP `CSQ` / SnpEff `ANN`), plus the call VCF.
- Evidence table: gene, transcript, HGVSc/HGVSp, consequence, zygosity, depth,
  VAF, population frequency (gnomAD), ClinVar assertion (attributed), in-silico
  scores if available, filter status, Contig QC flags.
- Deterministic filters: gene/panel, consequence class, frequency ceiling,
  quality/depth floor, zygosity, inheritance pattern (if pedigree present),
  ClinVar significance as *reported*, and saved filter sets.
- Sort/rank by transparent, documented rules (not a black box). Optional:
  consume published pre-trained scores (CADD, REVEL, SpliceAI, AlphaMissense)
  as attributed columns — do not train our own.
- Export the filtered table (TSV) with column provenance.

**Out of scope**

- ACMG classification computed by Contig. Display what InterVar/ClinVar/tools
  report, with source and version, or omit.
- Pathogenicity assertions, diagnosis, treatment advice.

**Context needed**

- 3–5 real annotated VCFs from different pipelines/layouts (VEP-only,
  SnpEff-only, both; GRCh38 and one GRCh37; germline and somatic).
- Decision: which evidence columns are must-have vs. nice-to-have.
- Decision: do we ship a curated small gene panel for the first demo, or start
  with "all genes" and filters?
- Licensing decision for any in-silico score column.
- A design partner or researcher to sanity-check the filter semantics.

**Data needed**

- Public: ClinVar VCF, gnomAD frequencies (subset/tabix), transcript models.
- Test: small synthetic annotated VCFs covering CSQ/ANN layouts, multi-allelic
  records, missing values, and a deliberately stale annotation cache.

**Model/training needed**

- No trained model. Start deterministic. A learned ranking can be a later
  opt-in experiment once we have user filter/click data; do not build it now.

**Acceptance**

- Given a run bundle, the workbench renders the same variant count the VCF
  contains, every displayed evidence cell names its source and version, filters
  are reproducible from a saved spec, and an absent/partial annotation yields an
  honest "not annotated" state, never a blank pass.

**Open questions for the session**

- Is the primary output a CLI command, a dashboard table, or both?
- Which filters are actually used by the target persona (lone computational
  biologist vs. wet-lab scientist)?
- Do we need a "why is this variant here?" one-line explanation per row?

**Session kickoff**

> "Design M1: the research-use variant workbench. Start from the existing
> annotation verifiers and `RunRecord`. Propose the data model, the filter spec,
> and the first UI surface. Do not add ACMG adjudication."

---

## M2 — Coverage & interpretation-readiness workbench

**Status:** v1 implemented 2026-11-07 — `contig readiness`, with PRD and task plan
in `docs/planning/readiness-workbench/`.

**Goal.** Show whether the data can support interpretation at all: per-gene and
per-exon coverage, target uniformity, homology/pseudogene caveats, sample
identity, and sex/relatedness checks. Gate "ready to interpret" and record the
gate in the bundle.

**In scope**

- Per-gene/per-exon coverage from BAM/CRAM + BED (or from an existing coverage
  TSV/MultiQC artifact where available).
- Metrics: mean depth, % ≥20x/50x/100x, uniformity, zero-coverage exons.
- Caveat flags: segmental duplication/homology (e.g., SMN1/SMN2), pseudogene
  regions (e.g., PMS2CL), low mappability, extreme GC.
- Interpretation-readiness state per gene/region: `ready`, `caution`,
  `not-interpretable`, with the reason and evidence.
- Sex check and sample-swap check surfaced as readiness caveats.
- Export a coverage/readiness table.

**Out of scope**

- Clinical coverage guarantees or diagnostic-grade claims.
- Replacing the existing QC verdict; this is an additional, gene-level surface.

**Context needed**

- Decision: do we compute coverage ourselves (BAM + BED) or consume the
  pipeline's coverage output? Computing it needs a BAM reader; consuming it
  depends on what sarek/rnaseq emit per assay. Check real outputs first.
- BED/GTF source and naming convention (chr-prefix handling already exists).
- Which caveat regions ship in v1 (start with SMN1/SMN2, PMS2/PMS2CL, and a
  documented "add more" format).
- Threshold defaults and whether they are configurable per panel/assay.

**Data needed**

- Reference FASTA + `.fai`, BED/GTF, a truth coverage set (GIAB or a real run).
- A small BAM/CRAM fixture with known depths for tests; no real aligner in CI.
- A list of homology/pseudogene regions with source and version.

**Model/training needed**

- No. Thresholds + deterministic checks. Outlier detection can reuse the
  existing cross-sample MAD pattern.

**Acceptance**

- For a run with a BED, the workbench shows every target gene/exon, the same
  numbers recomputable from the BAM, caveats with sources, and a readiness state
  that is `not-interpretable` when coverage is absent/low or a known homology
  caveat is unresolved — never silently "ready".

**Open questions for the session**

- Is readiness a hard gate on M1 filters/reports, or advisory with a recorded
  acknowledgement?
- Do we support panels with no BED yet (gene-list only), and how?
- What is the minimum viable caveat set that is honest without being noisy?

**Session kickoff**

> "Design M2: coverage and interpretation readiness. Read the existing QC packs,
> decide compute-vs-consume coverage, and define the readiness model. Keep it
> research-use and honest."

---

## M3 — Panel builder + panel registry

**Status:** v1 implemented 2026-11-07 — `contig panel-build`, `panel-list`,
`panel-show`, with PRD and task plan in `docs/planning/panel-registry/`.

**Goal.** Let a lab define a gene panel (gene name, gene list, or BED), validate
it against the reference, version it, and reuse it across runs and reports.

**In scope**

- Input modes: HGNC gene symbol(s), pasted list, BED upload.
- Validation: symbols resolve to HGNC; transcripts resolve to the reference;
  BED contigs match the FASTA; regions overlap exons as claimed; no silent
  off-target or empty panel; checksum the result.
- Generated canonical BED + metadata (genes, transcripts, source, version,
  checksum, creation time).
- Panel registry: list, inspect, duplicate, version, archive. Attach expected
  QC/coverage thresholds to a panel.
- Use the panel as a launch parameter and as a filter in M1/M2.

**Out of scope**

- Clinical panel certification.
- A hosted community marketplace (later, if demand).

**Context needed**

- HGNC complete set + alias table (free download; version it).
- Reference GTF/GFF3 and MANE Select mapping.
- Decision: where the registry lives (in-repo JSON vs. local SQLite vs.
  workspace DB).
- Decision: BED vs. BED.gz vs. interval-list canonical form; 0-based vs. 1-based
  handling must be explicit.
- A real lab panel (or 2–3 public panels) as a fixture.

**Data needed**

- HGNC dataset, GTF, reference `.fai`, 2–3 public panel BEDs, and synthetic
  invalid panels (wrong contig, empty overlap, duplicate genes).

**Model/training needed**

- No. Deterministic validation and normalization.

**Acceptance**

- A valid panel resolves to a checksummed canonical BED; an invalid panel is
  rejected with the exact reason; the same panel renders identical results on
  rerun/reproduce; the registry survives a restart and records provenance.

**Open questions for the session**

- Is a panel a first-class entity in `RunRecord`, or just a BED path + checksum?
- Do we need transcript-level panels in v1, or gene-level only?
- How do panels interact with the existing `--input` sample sheet?

**Session kickoff**

> "Design M3: the panel builder and registry. Start from the BED/GTF/reference
> reality in this repo, define the canonical panel artifact, and keep validation
> deterministic."

---

## M4 — Research report builder ("the self-proving report")

**Status:** v1 implemented 2026-11-07 — `contig report` + `contig report-check`,
with PRD and task plan in `docs/planning/report-builder/`.

**Goal.** Turn a verified run into an editable, shareable research report whose
every number is traceable to the signed bundle and which can be regenerated.

**In scope**

- Report sections: title/metadata, methods (pipeline, versions, params),
  verdict + deciding checks, QC summary, coverage/readiness, variant/evidence
  table (filtered), figures (QC plots/coverage), provenance, limitations,
  reviewer sign-off block.
- Editable narrative fields (intro, notes, limitations) with a diff/history.
- Include/exclude variants or sections; choose a template
  (publication / internal / core-facility delivery / audit).
- Every data cell links to its source file + checksum; the report carries the
  bundle hash and signature status.
- Export HTML (self-contained) and PDF; regenerate from the bundle with one
  command.
- Reviewer workflow: comment, approve, record who/when; research-use wording.
- Report diff between two runs or two bundle versions.

**Out of scope**

- Clinical report language, diagnosis, treatment recommendations, medical
  sign-off.
- A full document editor (keep it structured fields + narrative blocks).

**Context needed**

- Existing `report.py` HTML renderer and `contig show --html` output.
- Decision: PDF path — print-to-PDF (existing) vs. a library; check dependency
  policy and CI.
- 2–3 sample reports from target users (publication, core facility, internal).
- Decision: what "reviewed by" means and what is recorded (name, role, timestamp,
  key signature or just an audit entry).
- Templates and wording reviewed against the bright line.

**Data needed**

- No new biological data. Need real run bundles, a couple of design-partner
  report examples, and a style guide for figures/tables.

**Model/training needed**

- No. Templating and provenance binding. Optionally use the M5 assistant to
  draft narrative text, but the report must render without any model.

**Acceptance**

- The report regenerates byte-identical (or within documented tolerance) from
  the same bundle; every number is bound to a source; a changed bundle changes
  the report; an unsigned bundle is labelled unsigned; no raw reads are embedded.

**Open questions for the session**

- Is the report the primary product surface, or a companion to the dashboard?
- Do we need Word/DOCX export or is PDF/HTML enough?
- How much narrative editing is needed before it becomes a document editor?

**Session kickoff**

> "Design M4: the self-proving research report. Use the existing HTML report,
> define the section schema and provenance binding, and pick the PDF path."

---

## M5 — Ask-your-run assistant (grounded, action-taking)

**Status:** v1 implemented 2026-11-07 — `contig ask` + `ask-eval`, with PRD and
task plan in `docs/planning/ask-your-run/`. The deterministic router is the
product; the LLM is an optional paraphrase layer.

**Goal.** Let a user ask questions about a run and get answers that cite the
bundle, plus proposed actions (re-run, filter change, patch approval) behind
the existing approval gate.

**In scope**

- Retrieval over the run bundle: `run_record.json`, QC results, logs, repair
  history, provenance, report text, coverage/variant tables.
- Answers cite exact sources (check name, log line, file/hash) and say "not in
  this bundle" when unknown.
- Suggested actions map to existing CLI operations: explain verdict, reproduce,
  rerun with a parameter, inspect a repair, export a report.
- Guardrails: no clinical claims, no unsourced biology, no raw-read egress,
  prompt-injection defenses for log/report text, deterministic fallback when no
  model is configured.
- Privacy: send only bundle metadata/text, never FASTQ/BAM; support a local
  model option for air-gapped labs.

**Out of scope**

- A general bioinformatics chatbot or a Layer-1 workflow generator.
- Autonomous actions without approval.
- Training a foundation model.

**Context needed**

- Decision: hosted API vs. local model vs. both; which provider and data terms.
- A labeled eval set: 30–50 questions with expected cited sources and
  acceptable answers, built from real/synthetic bundles.
- Decision: how actions are confirmed (reuse the dashboard approval gate).
- Threat model for untrusted log/report content.
- Cost/latency budget per question.

**Data needed**

- 10–20 diverse run bundles (clean, healed, failed, unverified, different
  assays) and a question/answer/citation eval set.
- A small adversarial set: logs containing injected instructions, misleading
  report text, missing data.

**Model/training needed**

- Yes — an LLM, but **no training required initially**. Use a hosted chat model
  or a local instruction model with retrieval + tool calling. The real work is
  grounding, citation enforcement, and eval. Optional later: fine-tune a small
  model on the eval set if cost/latency demands it.

**Acceptance**

- Every answer either cites a bundle source or says it cannot answer; no
  unsourced claim passes the eval; proposed actions are never executed without
  approval; a model outage degrades to a deterministic "explain this run" path.

**Open questions for the session**

- Which model/provider meets the privacy constraint for the target users?
- Is the assistant a dashboard-only feature or also a CLI (`contig ask`)?
- What is the minimum eval bar before shipping (citation accuracy, refusal
  accuracy, action safety)?

**Session kickoff**

> "Design M5: the grounded ask-your-run assistant. Start from the bundle schema,
> define retrieval and citation rules, and build the eval set before the UI."

---

## M6 — Family analysis (trio / carrier / couple)

**Status:** v1 implemented 2026-11-07 — `contig family` (inheritance, Mendelian
consistency, de novo candidates, concordance), with PRD and task plan in
`docs/planning/family-trio/`. Carrier/couple views and X-linked rules remain
follow-ups.

**Goal.** Support research-use family analysis: inheritance-aware filtering,
Mendelian consistency, de novo candidates, carrier status, and couple
compatibility — all as evidence, not diagnosis.

**In scope**

- Pedigree input (PED-like) + sample mapping; validate against the sample sheet.
- Trio/quad analysis: Mendelian error rate, de novo candidate list, inheritance
  pattern per variant, parent-of-origin where computable.
- Carrier screening: per-person carrier list for recessive/X-linked variants,
  couple shared-carrier view, risk explanation as a research calculation.
- Family-level QC: sample identity/relatedness, sex check, swap detection.
- Readiness caveats per gene (reuse M2).

**Out of scope**

- Clinical genetic counseling, prenatal diagnosis, PGT-M recommendations.
- ACMG classification as Contig's own call.

**Context needed**

- Pedigree format decision (PED vs. a simple JSON) and how it maps to the
  existing sample sheet.
- Inheritance models to support in v1 (AR, AD, X-linked, de novo, compound het).
- Decision: relatedness computation (KING-style vs. a simpler genotype
  concordance; check dependency policy).
- HPO terms: optional in v1? If yes, use HPO's public ontology and keep
  phenotype matching deterministic/attributed.
- A genetics-savvy reviewer for the semantics (research-use, not clinical).

**Data needed**

- GIAB trio (HG002/HG003/HG004) VCFs and truth sets, plus a public carrier
  panel and a couple example.
- Synthetic pedigrees with known Mendelian errors and a deliberate sample swap.

**Model/training needed**

- No. Deterministic inheritance and relatedness checks.

**Acceptance**

- Mendelian error rate and de novo candidates are recomputed correctly on the
  GIAB trio fixture; a sample swap is detected; carrier/couple output is
  attributed and reproducible; every claim is labelled research-use.

**Open questions for the session**

- Is trio the first family shape, or couple carrier screening?
- Do we need phenotype (HPO) input in v1, or is genotype-only enough?
- How do we present "risk" without crossing into counseling?

**Session kickoff**

> "Design M6: research-use family analysis. Start with the GIAB trio and the
> existing sample sheet, define the pedigree model, and keep every output
> evidence-attributed."

---

## M7 — Oncology biomarker verification (MSI / TMB / LOH / CNV)

**Status:** v1 implemented 2026-11-07 — `contig biomarkers` verifies TMB against
a callable BED and records MSI/LOH/CNV as `not_verified`; PRD and task plan in
`docs/planning/biomarker-verification/`. MSI/LOH/CNV callers and reference data
remain follow-ups.

**Goal.** Verify that the somatic pipeline's oncology biomarkers were computed
correctly and reproducibly, and surface them with provenance — no drug
recommendations.

**In scope**

- Verify MSI status, TMB (mut/Mb), LOH, and CNV calls against the pipeline's
  own outputs and a second method where feasible.
- Sanity bands and cross-tool concordance; flag implausible values.
- Surface biomarker values with tool + version + reference build.
- Verify tumor/normal pairing, purity/ploidy caveats, and panel-of-normals use.
- Reproduce the biomarker computation where the pipeline exposes enough data.

**Out of scope**

- NCCN or any treatment/drug recommendation.
- Clinical tumor board reporting.
- Training a model to predict response.

**Context needed**

- Which somatic pipeline outputs are available (Mutect2/Strelka2/CNVkit/
  FACETS/Sequenza/MSIsensor/TMB from sarek or nf-core modules).
- Decision: verify by recomputation vs. cross-tool concordance vs. both.
- A domain reviewer to define honest sanity bands per biomarker.
- Licensing: avoid OncoKB/NCCN content; use CIViC (free) only as an attributed
  link-out if needed.

**Data needed**

- Reference cell lines / public truth sets: HCC1143/HCC1143BL, COLO829,
  HCT116 (MSI-H) and an MSS control; GIAB somatic/CNV truth sets where public.
- A real tumor-normal and a tumor-only run.
- Synthetic fixtures with deliberately wrong TMB/MSI/LOH values.

**Model/training needed**

- No. Deterministic computation and concordance.

**Acceptance**

- A known MSI-H line reports MSI-H with the evidence; a deliberately corrupted
  TMB is flagged; LOH/CNV calls match the truth set within documented tolerance;
  every value names its tool and version; drug recommendations are absent by
  design.

**Open questions for the session**

- Which biomarkers are verifiable from today's sarek outputs, and which need a
  new module?
- Do we support tumor-only in v1, or tumor-normal only?
- What is the honest tolerance for each biomarker before we have real data?

**Session kickoff**

> "Design M7: oncology biomarker verification. Inventory the current somatic
> outputs, pick the verifiable biomarkers, and define truth sets and tolerances.
> No drug recommendations."

---

## M8 — Cohort / federated frequency layer (later)

**Status:** local-only v1 implemented 2026-11-08 — `contig cohort-build` /
`cohort-query`, with PRD and task plan in `docs/planning/local-cohort/`. The
federated/cross-lab layer remains gated on multi-lab demand, consent, privacy,
and legal review.

**Goal.** Give labs cohort context — "this variant has been seen N times in your
lab / across participating labs" — without centralizing raw data, by default.

**In scope**

- Local cohort index: aggregate variant counts across a lab's own runs, with
  consent and access control.
- Optional federated aggregation: opt-in, k-anonymized counts, no raw reads or
  sample identifiers leaving the lab.
- Frequency display in M1/M2/report, attributed and versioned.
- Provenance: which cohorts contributed, when, and under what policy.

**Out of scope**

- A public population database (gnomAD already exists).
- Selling or sharing individual-level data.
- Any use of the data to train a model without explicit consent.

**Context needed**

- A real multi-lab design partner; without it, this is speculative.
- Consent/IRB posture and data residency requirements.
- Architecture decision: local-only vs. a small aggregation service; auth,
  tenancy, and audit.
- Privacy method: k-anonymity threshold, suppression rules, differential
  privacy if counts are sensitive.
- Legal review of the data-sharing model.

**Data needed**

- Multi-run bundles from at least two labs, or a synthetic multi-lab corpus.
- A privacy test set: queries that must be suppressed, small-count edge cases,
  re-identification attempts.

**Model/training needed**

- No ML. Statistics + privacy engineering. Do not build this before M1–M4 have
  real users; the network effect is worthless without adoption.

**Acceptance**

- No query returns a count below the k threshold; the aggregation is
  reproducible; a lab can delete its contribution; the audit log shows every
  access; no raw data leaves the lab.

**Open questions for the session**

- Is there real demand from more than one lab?
- Local-only cohort first, or federated from day one?
- Who owns the aggregation service, and where does it run?

**Session kickoff**

> "Design M8: the cohort/federated frequency layer. Do not start with code;
> start with the consent, privacy, and tenancy model, and confirm demand."

---

## What we need from the user before these sessions

1. **Priority and timeline.** Confirm the M1–M4 order, or reorder by real demand.
2. **Design partner access.** At least one researcher or lab willing to share a
   real annotated VCF/run and give feedback. Without this, M1/M2/M4 are guesses.
3. **Data permissions.** Which real datasets can be used in development, and
   which must stay synthetic/public.
4. **Licensing budget.** Whether to license OMIM/NCCN/COSMIC or stay open-only.
   Recommendation: stay open-only for the first pass.
5. **Deployment target.** Local-only, on-prem lab server, or cloud; this changes
   M4/M5/M8.
6. **UI preference.** CLI-first, dashboard-first, or both; and whether Persian/
   RTL matters for the first release.
7. **Clinical boundary confirmation.** Confirm we are not building diagnosis,
   ACMG adjudication, drug recommendations, or a patient portal.

---

## Definition of done for the whole plan

- Every milestone has a written PRD and a task-level plan in
  `docs/planning/<slug>/`, following the existing repo convention.
- Every scientific claim is attributed to a tool/database/version, and every
  output is reproducible from a signed bundle.
- No milestone requires a trained model except M5's LLM, which is consumed, not
  trained.
- The research-use bright line is intact in code, copy, and report templates.

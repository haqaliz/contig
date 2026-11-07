# Research workbenches blocked runbook

Each blocked row in `BACKLOG.md` needs evidence before code. This file records
exactly what to collect and what to change when it arrives.

## M1 — variant workbench

### M1-2: real annotated VCF
Collect from one design partner:
- 1–3 real VCFs with VEP `CSQ` or SnpEff `ANN` annotations.
- Reference build and transcript set.
- The filters they actually use, and the rows they expect to see.
- Any tumor/normal or trio shape.
Then: add the VCF as a manual gate (not CI), run `contig variants --json`, and
compare the evidence table to their expectation. Fix only evidenced gaps.

### M1-5: filter/sort review
Ask the partner:
- Which filters matter (gene, consequence, AF, ClinVar significance, depth/VAF,
  PASS, region).
- Whether “unknown AF is kept” is right for their work.
- Whether the ClinVar-first sort matches their review order.
Then: adjust defaults/docs; add tests for the accepted semantics.

## M2 — readiness

### M2-3: threshold calibration
Collect:
- 2–3 real panel/WES runs with the lab's expected coverage.
- Their minimum mean depth and %≥20x for “ready”.
- Genes/regions they consider uninterpretable.
Then: make the thresholds configurable (already are), record the lab's defaults,
and add a calibration note; do not change the global default without evidence.

## M3 — panel registry

### M3-2: real lab panel
Collect:
- One real panel BED or gene list + the expected exon set.
- Their transcript policy (MANE vs specific transcripts).
Then: validate the BED/GTF output against their expectation; add a panel
versioning/archive slice only if they ask for it.

## M4 — report builder

### M4-3: report feedback
Collect:
- 2–3 redacted reports they currently produce (publication/core-facility/audit).
- Who reviews/signs them, and what “reviewed” means.
Then: add/adjust templates; decide whether PDF/DOCX is actually needed.

## M5 — ask-your-run

### M5-1: live LLM eval
Decide:
- Hosted vs local model/provider, data terms, cost/latency budget.
- Whether bundle metadata/text is allowed to leave the machine.
Then: run the 30–50 question eval set against the chosen model; require citation
accuracy and refusal accuracy; only then enable `--llm` by default.

## M6 — family/trio

### M6-4: real trio + swap threshold
Collect:
- A real multi-sample trio/quad VCF + PED.
- Expected inheritance for a few known variants.
- Whether X-linked rules are needed.
Then: validate the autosomal calls; calibrate the IBS0 swap threshold; add
X-linked rules only if the partner needs them.

## M7 — biomarkers

### M7-1b: real MSI-H/MSS validation
Data acquired: MSIsensor example tumor/normal BAMs + BAI, microsatellite sites,
example BED/output, score/status list, and the GRCh38 TCGA baseline
(`data/msi/`). The caller seam is implemented: `contig biomarkers` parses an
existing MSIsensor output or runs `msisensor msi` on tumor/normal BAMs.
Remaining:
- A known real MSI-H/MSS pair (not just the 2-site demo) and the expected status.
- Calibrate the MSI-H threshold (default 10% unstable sites).
Then: report `match`/`divergent` with a research-use note.

### M7-2b: LOH
Data acquired: COLO829 copy-number segments
(`data/cnv/COLO829/copynumber/`). CNV segment concordance is implemented
(`--cnv-segments/--cnv-truth`).
Remaining:
- A real FACETS/CNVkit segment file with allele-specific data (BAF/LOH).
- Expected LOH calls for the run.
Then: verify LOH regions against the truth set; keep the no-drug-recommendation
rule. LOH remains `not_verified` until then.

### M7-3: TMB band
Data acquired: SEQC2 truth set + callable BED; TMB computed at 15.87 mut/Mb.
Remaining:
- Real tumor-normal TMB values from a reviewer.
- Whether their TMB definition is coding-only or all-pass.
Then: calibrate the tolerance/definition; keep the definition explicit in output.

## M8 — cohort

### M8-1: federated layer
Collect:
- At least two labs that explicitly ask for cross-lab frequency.
- Consent/IRB posture and data residency.
- A privacy method (k-anonymity threshold or differential privacy).
- Tenancy/audit/legal review.
Then: write a design doc first; build only after the legal/privacy model is
approved. The local-only v1 stays the default until then.

## Cross-cutting

### X-3: design-partner validation
Collect:
- 3–5 real users running their own data through M1–M8.
- Time-to-result, trust rating, filter/threshold complaints, WTP.
Then: reorder the backlog by what they actually hit, not by what is easy to code.

### X-4: release 1.1.0
After validation:
- Bump the version, write release notes, update the README front door.
- Keep the Unreleased changelog entries; do not cut a release on unvalidated
  defaults unless the notes say so.

# Outreach batch 1 — ready to send

**Goal:** 5 messages today, 20 this week. Replace `[your name]` and send from
the dedicated address (or GitHub/Slack identity). Do not attach data; the
redaction agreement comes after a reply.

Track each row in `docs/validation/outreach_targets.csv` and
`docs/validation/acquisition_tracker.csv` (status → `contacted`, date).

---

## 1. nf-core Slack (post once in `#help`, not every channel)

> Hi all — I maintain Contig, a local research-use layer on top of nf-core
> outputs: a filtered variant table, a coverage/readiness table, and an HTML
> report with hashed provenance. It never sends raw reads and makes no clinical
> claims. I’m looking for 3–5 people who would spend 60 minutes running it on
> their own VCF/panel/BED (or a sarek/rnaseq run) and telling me where the
> defaults are wrong. Happy to share the report and a short summary.
> Intake: https://github.com/haqaliz/contig/issues/new?template=design_partner.yml

**When:** after joining https://nf-co.re/join and setting the profile to
“Ali (Contig)”.

---

## 2. North Thames GLH — contact form

**Subject:** One panel BED + redacted report for a research-use readiness check?

> Hi — I maintain Contig, a local research-use workflow that checks coverage
> readiness and builds an HTML report with hashed provenance. I’m validating it
> on real panel/WES data and looking for one panel BED or gene list with the
> transcript policy you use, and (separately) 1–2 fully redacted reports you
> already produce. Nothing patient-identifying leaves your lab; I can sign a
> redaction/data-use agreement first. In return I’ll send a short summary of how
> the readiness states and report provenance compare to your expectations.
> Would that be possible? — [your name], Contig research validation

**Route:** https://www.gosh.nhs.uk/wards-and-departments/departments/laboratory-medicine/north-thames-genomic-laboratory-hub/

---

## 3. Central & South GLH — email

**To:** GMSAAdmin@uhb.nhs.uk  
**Subject:** One panel BED + redacted report for a research-use readiness check?

> Hi — I maintain Contig, a local research-use workflow that checks coverage
> readiness and builds an HTML report with hashed provenance. I’m validating it
> on real panel/WES data and looking for one panel BED or gene list with the
> transcript policy you use, and (separately) 1–2 fully redacted reports you
> already produce. Nothing patient-identifying leaves your lab; I can sign a
> redaction/data-use agreement first. In return I’ll send a short summary of how
> the readiness states and report provenance compare to your expectations.
> Would that be possible? — [your name], Contig research validation

**Route:** https://centralsouthgenomics.nhs.uk/ (verified public address)

---

## 4. Exeter Sequencing Service — contact form

**Subject:** One panel/WES run for a research-use coverage-readiness check?

> Hi — I maintain Contig, a local research-use workflow that checks coverage
> readiness and builds an HTML report with hashed provenance. I’m validating it
> on real panel/WES data and looking for one run with the coverage you would
> expect, plus your ready thresholds if you have them. Nothing patient-
> identifying leaves your lab; I can sign a redaction/data-use agreement first.
> In return I’ll send a short summary of how the readiness states compare to
> your expectations. Would that be possible? — [your name], Contig research
> validation

**Route:** https://www.exeter.ac.uk/research/facilities/sequencing/

---

## 5. AMP — MSI/TMB reviewer

**To:** amp@amp.org  
**Subject:** 15-min review of MSI/TMB verification bands?

> Hi — I’m building a research-use biomarker verification check (TMB from PASS
> variants in a callable BED; MSI from MSIsensor output or tumor/normal BAMs).
> I’m not making clinical claims; I need a sanity check on the band and
> definition (coding-only vs all-PASS, MSI-H threshold). Could you spare 15
> minutes, or point me to a published pair/values I should use? De-identified
> or public data only. — [your name], Contig research validation

**Route:** https://www.amp.org/ (verified public society address)

---

## 6. Biostars — post after the first replies

**Title:** Looking for feedback on a local, research-use variant/coverage/report workflow

> I maintain Contig (open source, local-first). It takes a VCF plus a panel/BED
> through a deterministic filtered variant table, a coverage/readiness table,
> and an HTML report with hashed provenance. It does not send raw reads and
> makes no clinical claims. I’m validating the defaults on real lab data and
> looking for 3–5 people willing to try it on a dataset they already have for 60
> minutes. The goal is to find where the filters/thresholds/report wording are
> wrong, not to sell anything. Details and the intake form:
> https://github.com/haqaliz/contig/issues/new?template=design_partner.yml

**Tags:** `variant-calling`, `coverage`, `report`, `validation`.

---

## Follow-up (day 4)

> Hi — just floating this up. Would a 30-minute version be easier? The intake
> form is here: https://github.com/haqaliz/contig/issues/new?template=design_partner.yml

## Follow-up (day 10)

Send the one-page example (M4 HTML report + the issue form), then close the
loop politely on day 21.

---

## What not to do

- Do not paste patient data, sample IDs, or raw paths into a public issue.
- Do not attach a VCF/BAM before the redaction agreement is signed.
- Do not mass-CC or scrape personal emails.
- Do not promise a clinical result, diagnosis, or treatment recommendation.

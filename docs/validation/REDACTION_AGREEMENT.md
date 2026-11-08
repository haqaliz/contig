# Research-use data sharing and redaction agreement (template)

**Template only — not legal advice.** Have the lab's own counsel or data owner
review it before use. Use one agreement per partner; keep the signed copy with
the partner's file, not in the public repo.

## Parties

- **Provider:** [lab / institution], represented by [name, role]
- **Recipient:** [Contig / Foresight Analytics], represented by [name, role]

## Purpose

Validate a local, research-use workflow that turns a VCF plus a panel/BED into a
filtered variant table, a coverage/readiness table, and an HTML report with
hashed provenance. The work is **not** a clinical service, diagnosis, ACMG
adjudication, or treatment recommendation.

## Data to be shared

Select what applies:

- [ ] One or more VCFs (annotated or unannotated), with reference build and
      transcript set.
- [ ] A panel BED or gene list + GTF, and the transcript policy.
- [ ] A depth/coverage TSV or a BAM/CRAM + target BED (or only summary metrics).
- [ ] 1–2 redacted reports the provider already produces.
- [ ] Other: [describe].

The provider will **not** share:

- Names, medical record numbers, dates of birth, addresses, or other direct
  identifiers.
- Sample IDs or file paths that identify a person.
- Raw reads or BAMs unless explicitly listed above and necessary.
- Any data the provider is not authorised to share.

## Redaction

The provider will replace identifiers with pseudonyms, remove free-text
identifiers, and check screenshots/logs for sample IDs before sharing. If a
report is shared, the provider confirms it is redacted to its own standard.

## Processing and storage

- The recipient processes the data **locally** on a machine controlled by the
  recipient. Raw reads are not uploaded to a cloud service.
- Only aggregate results (counts, coverage summaries, agreement metrics) and
  anonymized feedback are retained after the session.
- Access is limited to [name(s)].
- Retention: delete the files within [30] days of the session, or sooner on
  request. The provider may request deletion at any time.
- No attempt will be made to re-identify any individual.

## No clinical use

The recipient will not use the data or output for diagnosis, treatment,
screening, or clinical decision-making, and will not present the output as a
clinical report. The report carries a research-use banner.

## Publication and attribution

Findings may be described in aggregate (for example, “three labs completed the
core tasks; the most common friction was X”). The provider will not be named
without permission. No provider data or redacted report will be republished
without written permission.

## Security

The recipient will use a password-protected machine, keep the data out of public
repositories, and not send it to third parties. If a model provider is used for
optional paraphrase, only redacted bundle text may leave the machine, and the
provider will be told which model/provider is used before the session.

## Termination

Either party may terminate this agreement at any time. On termination, the
recipient deletes the provider's files and confirms deletion in writing.

## Signatures

Provider: ______________________  Date: __________

Recipient: _____________________  Date: __________

Contact for deletion/requests: [name, address]

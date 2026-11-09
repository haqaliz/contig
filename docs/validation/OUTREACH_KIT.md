# Outreach kit — research design partners and data/reviewer requests

**Status 2026-11-09.** This is the executable version of the people side of
`DATA_AND_PARTNER_ACQUISITION.md`. It assumes no new email infrastructure is
required to start: the first contact can happen through GitHub, nf-core Slack,
Biostars, Reddit, and the public lab/core contact pages. Email is only needed
for the follow-up and for the redaction agreement.

Research-use only. No PHI, no clinical claims, no patient data in public issues.

---

## 1. Identity: what to send from

### Technical channels (no new account needed)

- **GitHub:** `@haqaliz` (Ali Haqiqi, Foresight Analytics). Use the repo issue
  form as the inbound link:
  `https://github.com/haqaliz/contig/issues/new?template=design_partner.yml`
- **nf-core Slack / Nextflow Slack:** sign in with GitHub or email; set the
  display name to `Ali (Contig)` and the profile to “research-use validation”.
- **Biostars / Reddit:** a normal account is enough; disclose that you are the
  maintainer.

### Email (one dedicated address, not a personal inbox)

Pick one, in this order:

1. **Foresight Analytics domain alias** (best): `contig@<foresight-domain>` or
   `research@<foresight-domain>`. Create it as an alias/group so it can be
   shared later.
2. **Dedicated free address** (if no domain alias): create a new Gmail such as
   `contig.research@gmail.com`. Do not use a personal address; do not put the
   address in a public issue.
3. **No email yet:** use the GitHub issue form and Slack DMs for first contact;
   add the email only when a partner asks for the redaction agreement.

Signature:

```
Ali Haqiqi
Contig — research-use variant/coverage/report validation
https://github.com/haqaliz/contig
Book a 60-minute session: https://github.com/haqaliz/contig/issues/new?template=design_partner.yml
Research use only; no diagnosis, ACMG adjudication, or treatment recommendation.
```

### Inbound

The issue form asks for persona, data shape, goal, timezone, and consent. It
does **not** ask for PHI. Triage weekly; label `design-partner`; move qualified
contacts to the redaction agreement before receiving any files.

---

## 2. Channel playbook (do these in order)

### 2.1 nf-core Slack — highest yield

1. Open `https://nf-co.re/join`, join the Slack.
2. Set the profile; join `#help`, `#sarek`, `#rnaseq` (and `#scrnaseq` if
   relevant). Do not post in every channel.
3. Post the Slack template in `#help` once; answer replies in-thread.
4. Ask one maintainer/ambassador for a warm intro to a core/lab (template D).

### 2.2 Biostars

1. Create an account; complete the profile.
2. Post under **Bioinformatics** with tags `variant-calling`, `coverage`,
   `report`, `validation`.
3. Link the issue form, not a personal email. Follow the self-promotion norms:
   ask for feedback, do not advertise a product.

### 2.3 r/bioinformatics

Use the weekly “Ask a bioinformatician” / career thread if one is pinned;
otherwise a text post with the Slack template. Read the subreddit rules first.
No link-dropping without context.

### 2.4 ABRF CoreMarketplace — scalable lab route

1. Open `https://coremarketplace.org/?searchterms=*` and search `genomics`.
2. Filter to the UK/EU/US (pick one region per wave).
3. Open each facility's page; use its public contact form. Do not scrape
   personal emails.
4. Send template B. Target 10 per wave; log every contact.

### 2.5 NHS Genomic Laboratory Hubs — panel/report/reviewer route

Use the public pages:

- North Thames GLH: `https://www.gosh.nhs.uk/wards-and-departments/departments/laboratory-medicine/north-thames-genomic-laboratory-hub/`
- Central & South GLH: `https://centralsouthgenomics.nhs.uk/` (`GMSAAdmin@uhb.nhs.uk`)
- East Genomics: `https://www.eastgenomics.nhs.uk/` (`geneticslaboratories@nhs.net`)
- North East & Yorkshire GLH: `https://ney-genomics.org.uk/`

Ask for one panel BED + transcript policy, 1–2 redacted reports, or a
15-minute reviewer chat. Send the redaction agreement before any file.

### 2.6 AMP — MSI/TMB reviewer

Email `amp@amp.org` (public society address) or use the contact page at
`https://www.amp.org/`. Ask for a member interested in a 15–30 minute
research-use review; do not ask for patient data.

### 2.7 LinkedIn

Search: `genomics core facility director`, `computational biologist cancer
genomics`, `molecular pathologist MSI`. Send a short connection note, not a
mass message. Use template A shortened to 2–3 sentences.

### 2.8 Conferences

ABRF, ASHG, AGBT, Nextflow Summit/nf-core bytesize. Book 3 hallway sessions
per event; use the one-page brief.

### 2.9 Warm intros

Ask a mutual contact to forward a 3-line intro. The best targets are nf-core
maintainers, Nextflow ambassadors, local bioinformatics groups, and former
colleagues. A warm intro is worth 50 cold emails.

---

## 3. Templates

### A. Design partner (email / Slack DM / LinkedIn)

**Subject:** 60-min feedback on a research-use variant/report workflow?

> Hi [name] — I maintain Contig, a local research-use workflow that takes a VCF
> plus a panel/BED through a filtered variant table, a coverage/readiness table,
> and a shareable HTML report with hashed provenance. It runs on your machine,
> never sends raw reads, and makes no clinical claims.
>
> Would you be open to one 60-minute session on a dataset you already have?
> You would get the tables/report for your own use, and I would use anonymized
> feedback to fix the defaults. If yes, reply with the data shape
> (germline/somatic, panel/WES, trio?) and a slot — or use the issue form:
> https://github.com/haqaliz/contig/issues/new?template=design_partner.yml

### B. Core facility / lab panel + report

**Subject:** One panel/WES example for a research-use readiness/report check?

> Hi [name] — I maintain a research-use coverage-readiness and report workflow.
> I am looking for one panel or WES run with the coverage you would expect, and
> (separately) 1–2 fully redacted reports you already produce. Nothing
> patient-identifying leaves your lab; I can sign a redaction/data-use agreement
> first. In return I will send a short summary of how the readiness states and
> report provenance compare to your expectations. Would that be possible?

### C. MSI/TMB reviewer

**Subject:** 15-min review of MSI/TMB verification bands?

> Hi [name] — I am building a research-use biomarker verification check (TMB
> from PASS variants in a callable BED; MSI from MSIsensor output or
> tumor/normal BAMs). I am not making clinical claims; I need a sanity check on
> the band and definition (coding-only vs all-PASS, MSI-H threshold). Could you
> spare 15 minutes, or point me to a published pair/values I should use?
> De-identified or public data only.

### D. Warm intro (forwardable)

> [Mutual contact], would you be comfortable introducing me to [name]? I am
> looking for one 60-minute research-use validation session on a real
> VCF/panel/BED, not a sales call. Forwardable blurb below:
>
> “Ali maintains Contig, a local research-use variant/coverage/report workflow.
> He is looking for 3–5 labs to try it on their own data and tell him where the
> defaults are wrong. No raw reads leave the lab and there are no clinical
> claims. One 60-minute session.”

### E. nf-core Slack post

> Hi all — I maintain Contig, a local research-use layer on top of nf-core
> outputs: a filtered variant table, a coverage/readiness table, and an HTML
> report with hashed provenance. It never sends raw reads and makes no clinical
> claims. I am looking for 3–5 people who would spend 60 minutes running it on
> their own VCF/panel/BED (or a sarek/rnaseq run) and telling me where the
> defaults are wrong. Happy to share the report and a short summary.
> Issue form: https://github.com/haqaliz/contig/issues/new?template=design_partner.yml

### F. Biostars / Reddit post

> **Looking for feedback on a local, research-use variant/coverage/report workflow**
>
> I maintain Contig (open source, local-first). It takes a VCF plus a panel/BED
> through a deterministic filtered variant table, a coverage/readiness table,
> and an HTML report with hashed provenance. It does not send raw reads and
> makes no clinical claims. I am validating the defaults on real lab data and
> looking for 3–5 people willing to try it on a dataset they already have for 60
> minutes. The goal is to find where the filters/thresholds/report wording are
> wrong, not to sell anything. Details and the intake form:
> https://github.com/haqaliz/contig/issues/new?template=design_partner.yml

---

## 4. Follow-up sequence

| Day | Action |
|---|---|
| 0 | Initial message (A/B/C) or Slack/forum post. |
| 4 | One-line follow-up: “Would a 30-minute version be easier?” |
| 10 | Send a one-page example: the M4 HTML report + the issue form. |
| 21 | Close the loop: “I’ll stop here; happy to revisit after your next run.” |

Track every contact in `docs/validation/outreach_targets.csv`. Move a row only
when there is a reply, not when a message was sent.

---

## 5. Weekly targets

- 20 new contacts → 8 replies → 5 sessions → 3 completed core tasks.
- At least one germline/panel and one somatic/tumor user.
- At least one core facility and one lone computational biologist.
- One reviewer for MSI/TMB.
- One lab panel/report under the redaction agreement.

If after 20 contacts there is no reply, change the channel, not the message:
warm intros first, then Slack, then core facilities, then forums.

---

## 6. Sending from the terminal

`scripts/send_outreach.py` sends a JSON batch over SMTP and defaults to a dry
run. It reads the password from `CONTIG_SMTP_PASSWORD` or macOS Keychain
(`security find-generic-password -a contig-outreach -s smtp -w`). The batch is
`docs/validation/outreach_messages_batch1.json`.

### Recommended: a dedicated Gmail address

Best reliability and keeps outreach out of a personal inbox.

1. Create `contig.research@gmail.com` (or a domain alias).
2. Enable 2-Step Verification.
3. Google Account → Security → App passwords → create “Contig outreach” → copy
   the 16-character password.
4. Store it in Keychain (not shell history):

   ```bash
   read -rsp "App password: " SMTP_PASS; echo
   security add-generic-password -a contig-outreach -s smtp -w "$SMTP_PASS"
   unset SMTP_PASS
   ```

5. Configure and test:

   ```bash
   export CONTIG_SMTP_HOST=smtp.gmail.com
   export CONTIG_SMTP_PORT=465
   export CONTIG_SMTP_SECURITY=ssl
   export CONTIG_SMTP_USER=contig.research@gmail.com
   export CONTIG_SMTP_FROM=contig.research@gmail.com
   export CONTIG_SMTP_FROM_NAME="Ali Haqiqi"

   python scripts/send_outreach.py \
     --messages docs/validation/outreach_messages_batch1.json --check
   ```

6. Send after reviewing the previews:

   ```bash
   python scripts/send_outreach.py \
     --messages docs/validation/outreach_messages_batch1.json --send
   ```

### Other providers

| Provider | Host / port / security | Credential |
|---|---|---|
| AOL | `smtp.aol.com` / 465 / `ssl` | Full AOL address + app password from AOL Account Security (2FA may be required) |
| Proton Mail | `127.0.0.1` / 1025 / `starttls` | Requires a paid Proton plan + Proton Mail Bridge; use the Bridge-generated username/password |
| iCloud | `smtp.mail.me.com` / 587 / `starttls` | Apple app-specific password |
| Fastmail | `smtp.fastmail.com` / 465 / `ssl` | Fastmail app password |
| Outlook personal | `smtp-mail.outlook.com` / 587 / `starttls` | App password; Microsoft 365 may block basic SMTP auth |

Set `CONTIG_SMTP_HOST`, `CONTIG_SMTP_PORT`, `CONTIG_SMTP_SECURITY`,
`CONTIG_SMTP_USER`, and `CONTIG_SMTP_FROM` accordingly. Proton Bridge must be
running; AOL app passwords are the only AOL route this script supports.

### What the script does not send

The nf-core Slack post, the two web contact forms (North Thames GLH, Exeter),
and the Biostars/Reddit posts are not email. Open those pages and paste the
matching block from `outreach_batch_1.md`. Copy the Slack post to the clipboard
first if you want a one-paste flow.

### Safety

- Dry run is the default; `--send` is explicit.
- Never commit an app password; use Keychain.
- Never attach PHI or a VCF/BAM before the redaction agreement is signed.
- One message per target; no mass CC.

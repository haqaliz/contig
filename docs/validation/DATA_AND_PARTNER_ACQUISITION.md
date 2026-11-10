# Data and partner acquisition plan

**Status 2026-11-11.** This turns the blocked rows in
`docs/planning/research-workbenches/BACKLOG.md` into concrete sources, access
routes, and outreach. Open data first; permission-gated data second; people
last. Nothing here changes the research-use boundary: no diagnosis, no
Contig-authored ACMG, no drug/treatment recommendation, and no patient data
without a redaction agreement.

The companion tracker is `docs/validation/acquisition_tracker.csv`.

---

## 1. Short version

| Category | Items | What it means |
|---|---|---|
| **Ready now, no permission** | M6 trio (GIAB), M3 public panel (PanelApp), M7 TMB data (SEQC2), M1 annotation shape (GIAB + VEP/SnpEff), M2 plumbing (nf-core CRAM/BED) | We can run/calibrate these ourselves. The remaining gap is reviewer sign-off, not data access. |
| **Needs permission** | M7 MSI tumor/normal BAMs (TCGA/CPTAC), M4 redacted reports, M3 lab-specific BED, M2 lab coverage runs | An institution/lab must approve access or redaction. Start the paperwork now; it has the longest lead time. |
| **Needs people** | M1 filter review, M2 threshold reviewer, M3 lab expectation, M4 reviewer workflow, M5 provider/eval sign-off, M7 TMB reviewer, M8 labs/legal, X-3 design partners | A conversation, not a download. The outreach templates below are ready to send. |
| **Needs a user decision** | M5 model/provider; dashboard auto-discovery convention | Short decision, then unblocked. |

**Do this first:** run M6 on the full GIAB trio and calibrate the swap threshold;
build and diff a PanelApp public panel; verify LOH against TCGA ASCAT segments.
Those three produce real evidence without asking anyone for anything.

## 1a. How the seven asks are now executable

| Ask | Mechanism | Artifact |
|---|---|---|
| 1. Outreach identity | GitHub issue form + nf-core Slack/GitHub identity; a dedicated email alias (domain alias or new Gmail) only for follow-up; no personal address | `docs/validation/OUTREACH_KIT.md`, `.github/ISSUE_TEMPLATE/design_partner.yml` |
| 2. Target geography + intros | 20 verified public routes (NHS GLHs, UK/US cores, AMP, ABRF, nf-core, forums) + a forwardable warm-intro script | `docs/validation/outreach_targets.csv` |
| 3. Redaction/data-use approval | A one-page, plain-language agreement template to send before any file; the lab's counsel can edit it | `docs/validation/REDACTION_AGREEMENT.md` |
| 4. M5 access | Local Ollama (`qwen2.5:1.5b`) installed; the live eval script ran 9/9 after a fidelity guard; no API key needed for the local run | `docs/validation/M5_LLM_EVAL.md`, `scripts/llm_eval.py` |
| 5. Institutional data access | Open TCGA-COAD ASCAT allele-specific segments downloaded (LOH data); MSI paired BAMs are controlled (dbGaP/EGA) with a cell-line fallback documented | this document, §3.6–3.7; `scripts/fetch_validation_data.sh` |
| 6. Dashboard decision | Explicit manifest stays the default; optional read-only `runs/<run_id>/research/manifest.json` convention for X-1b; no write/launch actions | `docs/planning/research-workbenches/DECISIONS.md` |
| 7. Large downloads | `fetch_validation_data.sh` downloads only the small/open files and prints the exact large-data routes; `data/` stays gitignored | `scripts/fetch_validation_data.sh` |

---

## 2. Blocked-item matrix

| ID | Missing evidence | Type | Best source / route | Next action |
|---|---|---|---|---|
| M1-2 | Real annotated VCF (VEP `CSQ` / SnpEff `ANN`) | Open data or partner | GIAB truth VCF + local VEP/SnpEff; or a partner VCF | Generate a GIAB-annotated VCF now; ask a partner for one real VCF |
| M1-5 | Filter/sort semantics review | People | Design partner (computational biologist) | Send the partner brief; ask which filters/sort they use |
| M2-3 | Real panel/WES coverage + reviewer | Data + people | nf-core CRAM/BED (open) + a lab's expected coverage | Run the public data now; ask a core facility for one real run |
| M3-2 | Real lab panel BED + transcript policy | Data + people | PanelApp public panel now; a lab BED via a GLH/core | Build a PanelApp panel now; request one lab BED |
| M4-3 | 2–3 redacted reports + reviewer workflow | Data + people | Public nf-core MultiQC reports now; partner redacted reports | Collect public examples; ask 2 labs under a redaction agreement |
| M5-1 | Provider/privacy decision + live eval | User decision + data | Local Ollama + a hosted small OpenAI model | User picks provider/model; run the frozen eval |
| M6-4 | Real trio + swap threshold | Open data | GIAB Ashkenazim trio (already in `data/giab/`) | Run the full trio; calibrate IBS0 swap threshold |
| M7-1b | Real MSI-H/MSS tumor/normal pair | Permission data | TCGA-COAD/READ or CPTAC-COAD (labels open; BAMs controlled); public SRA study alternative | Start dbGaP/EGA collaborator route; search SRA in parallel |
| M7-2b | Allele-specific LOH segments | Open data | GDC ASCAT allele-specific copy-number segments (TCGA-COAD) | Download and inspect open processed segments |
| M7-3 | TMB band + reviewer | Data + people | SEQC2 truth set (ready) + published TMB + a reviewer | Compute TMB; ask AMP/a molecular pathologist for the band |
| M8-1 | 2 labs + consent/privacy/tenancy/legal | People + legal | Core facilities / GLHs / biotech partners | Do not build; collect demand and legal posture first |
| X-3 | 3–5 design partners | People | nf-core Slack, Biostars, ABRF CoreMarketplace, warm intros | Send 20 targeted invitations this week |
| X-4 | Release `1.1.0` | Done | Tag `v1.1.0` pushed 2026-11-08 | Watch the release workflow |

---

## 3. Open data we can use now

### 3.1 M6 — GIAB Ashkenazim trio (ready locally)

Already in `data/giab/`:

- `AshkenazimTrio_chr20_subset.vcf` + `AshkenazimTrio.ped`
- `HG002_GRCh38_1_22_v4.2.1_benchmark.vcf.gz` (son)
- `HG003_GRCh38_1_22_v4.2.1_benchmark.vcf.gz` (father)
- `HG004_GRCh38_1_22_v4.2.1_benchmark.vcf.gz` (mother)
- matching `*_noinconsistent.bed` high-confidence regions

The chr20 subset already runs cleanly:

```bash
uv run contig family \
  --vcf data/giab/AshkenazimTrio_chr20_subset.vcf \
  --ped data/giab/AshkenazimTrio.ped \
  --out /tmp/family_review.tsv
# 399 rows, 217 evaluated, 0 Mendelian inconsistent, 0 de novo
```

**Run 2026-11-09:** the chr20 subset gives parent-child same-genotype rates of
0.72 (HG002/HG003) and 0.82 (HG002/HG004), with IBS0 = 0 in all pairs. The
full trio (merged with `bcftools merge -m none`) gives **5,649,742 rows,
2,386,190 evaluated, 452 Mendelian inconsistencies (0.02%)**. Intersecting the
three GIAB `*_noinconsistent.bed` files (686,545 intervals) gives **5,027,114
rows, 2,259,196 evaluated, 19 residual inconsistencies (0.00084%)**; IBS0 = 0
across ~3.2M parent-child sites, same-genotype 0.71–0.72, and the swap flag
never fires. The current swap threshold (`IBS0 > 1%` or `same > 99%`) is
conservative and confirmed by the data; the 19 residual calls are truth-set
noise, not a Contig failure. The calibration is recorded in
`src/contig/family/analyze.py`. Source:
`https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/release/AshkenazimTrio/`.
GIAB is open; cite NIST/GIAB.

### 3.2 M3 — PanelApp public clinical panel (ready)

PanelApp is a public Genomics England knowledge base. The API is public:

```bash
# 433 public panels
curl -s 'https://panelapp.genomicsengland.co.uk/api/v1/panels/?page=1' > panels.json

# Example: Adult solid tumours cancer susceptibility (105 genes, GMS signed-off)
curl -s 'https://panelapp.genomicsengland.co.uk/api/v1/panels/245/' > panel-245.json
```

Take `entity_type == "gene"`, `confidence_level == "3"` (green), and
`gene_data.gene_symbol`; build with the local GTF + HGNC:

```bash
uv run contig panel-build \
  --name "PanelApp adult solid tumours" \
  --genes "$(python3 -c 'import json; d=json.load(open("panel-245.json")); print(",".join(g["gene_data"]["gene_symbol"] for g in d["genes"] if g["entity_type"]=="gene" and g["confidence_level"]=="3"))')" \
  --gtf data/ensembl/Homo_sapiens.GRCh38.113.gtf.gz \
  --hgnc data/mane/hgnc_complete_set.txt \
  --version 1 --out-dir /tmp/panelapp
```

**Run 2026-11-09:** 82 green genes; panel
`panelapp-adult-solid-tumours-v1-ed98559b` built successfully. This gives a
real public clinical panel definition without a partner. A lab-specific
BED/transcript policy still needs a lab. Attribute Genomics England; check the
PanelApp terms before redistribution.
Contact: `panelapp@genomicsengland.co.uk` / `info@genomicsengland.co.uk`.

### 3.3 M7 — SEQC2 TMB truth set (ready locally)

Already in `data/seqc2/`:

- `high-confidence_sSNV_in_HC_regions_v1.2.1.vcf.gz`
- `high-confidence_sINDEL_in_HC_regions_v1.2.1.vcf.gz`
- `High-Confidence_Regions_v1.2.bed`

TMB is already computed at 15.87 mut/Mb on the SEQC2 truth set. The data gap
is closed; the remaining gap is a reviewer/definition decision (coding-only
vs all-PASS). Published SEQC2/MAQC material can anchor the value; a molecular
pathologist or AMP reviewer sets the band. BAMs (if needed) are open at
`https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/seqc/Somatic_Mutation_WG/data/WGS/`.

### 3.4 M1 — annotated VCF shape from GIAB (ready to generate)

Use a GIAB truth VCF (or a public 1000G VCF) and annotate locally with VEP or
SnpEff:

```bash
# VEP (cache required); or SnpEff with a GRCh38 database
vep --input_file data/giab/HG002_GRCh38_1_22_v4.2.1_benchmark.vcf.gz \
  --output_file /tmp/HG002.vep.vcf --vcf --everything \
  --cache --assembly GRCh38 --offline

uv run contig variants /tmp/HG002.vep.vcf \
  --clinvar data/clinvar/clinvar.vcf.gz --build GRCh38 \
  --gene BRCA1,BRCA2 --max-af 0.01 --pass-only --out /tmp/variants.tsv
```

This exercises real `CSQ`/`ANN` shapes. It does not replace a partner's filter
semantics (M1-5). ClinVar: `https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/`.
The GDC VEP cache is open at
`https://api.gdc.cancer.gov/data/8b9278b3-1e0c-430a-aae5-a944428401c0`
(4.6 GB) if a cache is needed.

**Run 2026-11-09:** the local `data/ensembl/homo_sapiens_incl_consequences-chr22.vcf.gz`
is a real VEP-annotated VCF with >1M records. The new WGS guard correctly
demanded a region/gene; a 200 kb region with `--max-records 1000000` completed.
Its `CSQ` format is minimal (`Allele|Consequence|Feature_type|Feature|Amino_acids|SIFT`)
and has no `SYMBOL`/`Gene`, so gene-level filters cannot match. Use a GIAB VEP
run with `--symbol` (or a partner VCF with gene symbols) for the full M1-2/M1-5
shape.

**Run 2026-11-11 — SnpEff path works on real GIAB data.** Java is available
through Homebrew (`/opt/homebrew/opt/openjdk/bin/java`). SnpEff core 5.4 with
the `GRCh38.mane.1.5.ensembl` database annotated the GIAB chr20 trio subset:
399/399 records carry `ANN` with `Gene_Name`, and
`contig variants ... --gene RSPO4,PSMF1` matched 23 + 94 rows with parsed
consequence, impact, and HGVS. The first run exposed a fixture bug:
`scripts/build_trio_subset.py` split multi-allelic ALTs but kept the original
`1/2` genotypes, so SnpEff dropped 12 records. The script now remaps each GT to
the biallelic record; the regenerated subset has 399 valid rows. A partner VCF
is still the M1-2 gate for real-world annotation/transcript quirks, but the
public run closes the format/shape gap.

```bash
# SnpEff core + MANE database (manual; ~400 MB database)
java -jar snpEff.jar ann -v -noLog GRCh38.mane.1.5.ensembl \
  /tmp/AshkenazimTrio_chr20_subset.fixed.vcf > /tmp/AJtrio.snpeff.vcf
uv run contig variants /tmp/AJtrio.snpeff.vcf --build GRCh38 \
  --gene RSPO4,PSMF1 --out /tmp/aj_genes.tsv
```

### 3.5 M2 — coverage plumbing from nf-core (ready locally)

Already in `data/nfcore/`:

- `NA12878_sorted_chrM_chr20_rehead_60pdown.cram`
- `target_chr20.bed`

Run `contig readiness --bam ... --bed ... --build GRCh38`. This proves the
plumbing and gives a coverage distribution. Real panel/WES runs with the lab's
expected coverage still need a lab (M2-3); the reviewer sets the thresholds,
not the public CRAM.

### 3.6 M7 — LOH from TCGA ASCAT (open processed data; verify per file)

GDC's CNV pipeline produces **Allele-specific Copy Number Segment** files with
ASCAT (integer total and allele-specific copy number). Query the GDC Data
Portal for project `TCGA-COAD`, data type "Allele-specific Copy Number
Segment", and take the open processed files. LOH can be derived where the minor
copy number is 0.

- GDC CNV pipeline: `https://docs.gdc.cancer.gov/Data/Bioinformatics_Pipelines/CNV_Pipeline/`
- Portal: `https://portal.gdc.cancer.gov/`
- Controlled-access help: `https://gdc.cancer.gov/access-data/obtaining-access-controlled-data`

Use one tumor's ASCAT segments as `--cnv-truth` and compare against the run's
segments. If a file is controlled, use the dbGaP route in §4. The local
COLO829 zip is **not** allele-specific (it has total copy number only), so it
cannot close LOH by itself.

**Run 2026-11-09:** downloaded one open TCGA-COAD ASCAT2 segment file to
`data/cnv/tcga_ascat/TCGA-COAD.ascat2.allelic_specific.seg.txt` (88 lines).
Columns: `GDC_Aliquot`, `Chromosome`, `Start`, `End`, `Copy_Number`,
`Major_Copy_Number`, `Minor_Copy_Number`. LOH can be derived where the minor
copy number is 0. The other open ASCAT2/ASCAT3 files are 2–11 KB each; no
permission is needed for these processed segments.

### 3.7 M7 — MSI labels are open; the matched BAMs are the gate

MSI status labels:

- TCGA-COAD/READ MSI calls (Cortes-Ciriano et al. 2017; cBioPortal
  `coadread_tcga_pub` clinical data).
- CPTAC-COAD MSI status (24/105 MSI-H in the published cohort; supplementary
  table).

Tumor/normal BAMs:

- TCGA raw BAMs: controlled access via dbGaP.
- CPTAC raw WES: controlled via GDC/EGA; processed data may be open.
- Public SRA study with matched normals: search `MSI` + `tumor normal` +
  `WES`/`WGS`; use only one with explicit MSI status.

HCT116 (MSI-H, Cellosaurus CVCL_0291) and SW480 (MSS) are useful cell-line
models and public WES exists (CCLE `PRJNA523380`), but they have **no matched
normal**, and the current MSIsensor seam runs `msisensor msi` tumor/normal.
Do not present a cell-line-only run as the M7-1b validation unless we add and
validate a tumor-only mode.

**Run 2026-11-09:** the GDC TCGA-COAD and CPTAC-2 WXS BAMs are
`access=controlled` (15–50 GB each), so the paired run needs dbGaP/EGA. CCLE
`PRJNA523380` has HCT116 WGS `SRR8639145` (~640M reads) and targeted capture
`SRR8657432`; SW480 targeted capture `SRR8657564`. Those are tumor-only and
do not replace a matched-normal pair.

---

## 4. Permission-gated data

| Data | Route | What to ask | Lead time |
|---|---|---|---|
| TCGA/CPTAC raw tumor/normal BAMs | dbGaP (`https://dbgap.ncbi.nlm.nih.gov/`) or EGA (`https://ega-archive.org/`) | Institutional Data Access Request; research-use statement; IRB/consent as required; a collaborator/PI as signing official | Weeks to months |
| CPTAC processed/open files | CPTAC Data Portal (`https://cptac-data-portal.georgetown.edu/`) and GDC | Confirm which files are open; use open processed files first | Days |
| Lab panel BED / transcript policy | A GMS Genomic Laboratory Hub or an ABRF core facility | One panel BED or gene list + transcript policy; no patient data | 1–3 weeks |
| 2–3 redacted reports | A clinical/research lab under a redaction agreement | Redacted report + who reviews/signs; what “reviewed” means | 2–6 weeks |
| Real coverage runs + thresholds | A core facility / lab | 2–3 panel/WES runs with expected coverage; their ready thresholds | 2–6 weeks |
| MSI/TMB reviewer | AMP (`amp@amp.org`), a molecular pathology lab, or a cancer center | 15–30 min review of the band/definition; published or de-identified values only | 1–3 weeks |
| M8 federation | 2+ labs + legal | Consent/IRB posture, residency, privacy method, tenancy/audit | Months |

**Rules for every request:** run locally; raw reads/BAMs never leave the
machine; use paths/hashed labels in screenshots; no clinical claims; delete on
request. Send the redaction/data-use terms before receiving files.

### Public contact routes (verified 2026-11-09)

- Genomics England / PanelApp: `panelapp@genomicsengland.co.uk`,
  `info@genomicsengland.co.uk`, `https://www.genomicsengland.co.uk/contact`
- North Thames GLH: `https://www.gosh.nhs.uk/wards-and-departments/departments/laboratory-medicine/north-thames-genomic-laboratory-hub/`
- Central & South GLH: `GMSAAdmin@uhb.nhs.uk`, `https://centralsouthgenomics.nhs.uk/about-us/contact-us-2/`
- East Genomics: `cuh.geneticslaboratories@nhs.net`,
  `https://www.eastgenomics.nhs.uk/about-us/genomic-laboratory-hub/contact-us`
  (the old `geneticslaboratories@nhs.net` address rejects external mail with a 550)
- North East & Yorkshire GLH: `https://ney-genomics.org.uk/`
- AMP: `amp@amp.org`, +1 301-634-7987, `https://www.amp.org/`
- ABRF CoreMarketplace: `https://coremarketplace.org/?searchterms=*`
- GDC Help Desk: `support@nci-gdc.datacommons.io`
- nf-core community: `https://nf-co.re/join`
- Biostars: `https://www.biostars.org/`
- r/bioinformatics: `https://www.reddit.com/r/bioinformatics/`

Do not scrape personal emails. Use the organization's public contact page or a
warm intro. If a page lists a generic lab/office address, that is the route.

---

## 5. People: who to ask and how

### 5.1 Channels, in order of yield

1. **nf-core / Nextflow Slack** (`https://nf-co.re/join`) — the highest-density
   pool of computational biologists who run sarek/rnaseq on real data. Post in
   `#help` or the assay channel; ask for a 60-minute feedback session, not a
   sale.
2. **Warm intros** — nf-core maintainers, Nextflow ambassadors, local
   bioinformatics groups, former colleagues. One intro beats 50 cold emails.
3. **ABRF CoreMarketplace** — searchable genomics core facilities with public
   contact routes. Shortlist 20–25, send the one-page brief.
4. **NHS Genomic Laboratory Hubs** — for a real panel BED, a redacted report,
   and the reviewer workflow. Use the public contact pages above.
5. **AMP** — for the MSI/TMB reviewer and the molecular-pathology workflow.
6. **Biostars / r/bioinformatics** — transparent “we built a research-use tool,
   looking for feedback on real data” posts; follow each community's
   self-promotion rules.
7. **Conferences** — ABRF, ASHG, AGBT, Nextflow Summit/nf-core bytesize. Use
   hallway/booth conversations to book sessions.
8. **LinkedIn** — search “genomics core facility director”, “computational
   biologist cancer genomics”, “molecular pathologist MSI”; send a short
   connection note, not a pitch.

### 5.2 Who exactly

| Persona | Where to find them | What to ask for |
|---|---|---|
| Lone computational biologist | nf-core Slack, Nextflow Slack, Biostars | One VCF + filter feedback; 60 min |
| Wet-lab scientist who cannot code | Core facilities, LinkedIn, local labs | One VCF + panel/BED; 60 min |
| Core facility | ABRF CoreMarketplace, university genomics cores | One panel/WES run + coverage expectations; report examples |
| Biotech researcher | LinkedIn, local biotech, nf-core users | Provenance/report workflow feedback |
| Molecular pathologist / MSI-TMB reviewer | AMP, cancer centers, GLHs | 15–30 min band/definition review |
| Lab panel owner | GMS GLHs, core facilities | One panel BED + transcript policy |

### 5.3 Outreach sequence (two weeks)

- **Day 1:** send 5 warm-intro requests; post one nf-core Slack message.
- **Day 2:** email 10 ABRF core facilities with the one-page brief.
- **Day 3:** email 5 GLH/lab contacts for panel/report examples.
- **Day 4:** email AMP for a reviewer; post one Biostars/Reddit message.
- **Day 5:** follow up with everyone; book the first two sessions.
- **Week 2:** run the sessions; fill `scorecard.csv`; ask each partner for one
  referral.

Target: 20 contacted → 8 replies → 5 sessions → 3 completed core tasks.

### 5.4 Templates

**A. Design partner (email/Slack DM)**

> Subject: 60-min feedback on a research-use variant/report workflow?
>
> Hi [name] — I’m validating a local, research-use workflow that takes a VCF
> plus a panel/BED through a filtered variant table, a coverage/readiness table,
> and a shareable HTML report with hashed provenance. It runs on your machine,
> never sends raw reads, and makes no clinical claims.
>
> Would you be open to one 60-minute session on a dataset you already have?
> You’d get the tables/report for your own use, and I’d use anonymized feedback
> to fix the defaults. If yes, reply with the data shape (germline/somatic,
> panel/WES, trio?) and a slot.

**B. Core facility / lab panel + report**

> Subject: One panel/WES example for a research-use readiness/report check?
>
> Hi [name] — I’m validating a research-use coverage-readiness and report
> workflow. I’m looking for one panel or WES run with the coverage you would
> expect, and (separately) 1–2 fully redacted reports you already produce.
> Nothing patient-identifying leaves your lab; I can sign a redaction/data-use
> agreement first. In return I’ll send a short summary of how the readiness
> states and report provenance compare to your expectations.

**C. MSI/TMB reviewer**

> Subject: 15-min review of MSI/TMB verification bands?
>
> Hi [name] — I’m building a research-use biomarker verification check (TMB from
> PASS variants in a callable BED; MSI from MSIsensor output or tumor/normal
> BAMs). I’m not making clinical claims; I need a sanity check on the band and
> definition (coding-only vs all-PASS, MSI-H threshold). Could you spare 15
> minutes, or point me to a published pair/values I should use? De-identified
> or public data only.

**D. Data-access collaborator (dbGaP/EGA)**

> Subject: Collaborator for a public MSI tumor/normal benchmark?
>
> Hi [name] — I’m validating a research-use MSI/LOH verification method and need
> a small number of public tumor/normal BAMs with known MSI status. The analysis
> runs locally; only aggregate results would be reported. Would you be willing
> to be the institutional collaborator/signing official on a dbGaP or EGA
> request, or point me to an already-open SRA/CPTAC alternative?

**E. nf-core Slack post**

> Hi all — I’m validating a local, research-use layer on top of nf-core outputs:
> a filtered variant table, a coverage/readiness table, and an HTML report with
> hashed provenance. It never sends raw reads and makes no clinical claims. I’m
> looking for 3–5 people who’d spend 60 minutes running it on their own
> VCF/panel/BED (or a sarek/rnaseq run) and telling me where the defaults are
> wrong. Happy to share the report and a short summary. Reply/DM if interested.

---

## 6. 30/60/90-day plan

**Days 1–14 — open data and first outreach**
- Run the full GIAB trio; record Mendelian consistency and calibrate the swap
  threshold (M6).
- Build a PanelApp green panel and diff it against the expected gene set (M3).
- Download one TCGA-COAD ASCAT allele-specific segment set; inspect LOH (M7).
- Generate a GIAB-annotated VCF and run the M1 table (M1 data shape).
- Send the first 20 partner/lab/reviewer messages; book 2 sessions.
- Start the dbGaP/EGA collaborator conversation for MSI BAMs.

**Days 15–45 — sessions and permission**
- Run 3–5 design-partner sessions on their data; fill `scorecard.csv`.
- Collect one lab panel BED, 2 redacted reports, and one coverage run under the
  data-use terms.
- Get the MSI/TMB reviewer feedback; record the accepted definitions.
- Decide M5 provider/model and run the frozen eval on a local + hosted model.
- If 2 labs explicitly ask for cross-lab frequency, write the M8 design doc;
  do not build.

**Days 46–90 — decide**
- Calibrate M2 thresholds with the lab's expected coverage; do not change the
  global default without evidence.
- Close or re-file each blocked row based on what arrived.
- Reorder the backlog by partner friction, not by what is easy to code.
- Only then decide whether M8 federation or a new assay is justified.

---

## 7. What I need from you

1. **Sender identity:** which email/domain and name should outreach use? A
   company address is better than a personal one.
2. **Target geography/relationships:** UK, EU, US, or all? Any labs, core
   facilities, or companies you already know? Warm intros are the highest-yield
   channel.
3. **Data-use approval:** approve a one-page redaction/data-use term for
   partner reports and panel/coverage examples.
4. **M5 access:** an OpenAI API key (or approval to use a local Ollama model)
   and the current small model id you want evaluated.
5. **Institutional data access:** dbGaP/EGA requests need a signing official and
   an institutional research-use statement. Do you have an institution/PI to
   sponsor the MSI/LOH request, or should we use only open/CPTAC processed data?
6. **Dashboard decision:** auto-discover research artifacts from a run bundle
   (needs a path convention) or keep the explicit manifest?
7. **Large downloads:** approval to pull the full GIAB trio, TCGA ASCAT
   segments, and any MSI BAMs into `data/` (gitignored). They are several GB to
   tens of GB.

---

## 8. Tracking

Keep `docs/validation/acquisition_tracker.csv` current. One row per blocked
item; update `status`, `owner`, `next_action`, and `date` after every contact.
Review it weekly. A blocked row only moves when its named evidence exists, not
when a message was sent.

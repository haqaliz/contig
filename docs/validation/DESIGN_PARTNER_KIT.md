# Design-partner validation kit

Purpose: test the research-workbench surfaces on a real user's own data before
calling the defaults calibrated. This is the roadmap's own gate, not a demo.

Scope: 3–5 design partners. One 60–90 minute session each. Research-use only.
No clinical diagnosis, ACMG adjudication, treatment advice, or patient data.

---

## 1. What we are testing

| Hypothesis | Signal |
|---|---|
| H1. A researcher can go from their VCF to a filtered evidence table without help | Task completes in <15 min, no rescue |
| H2. Readiness changes what they would interpret | They identify at least one gene they would not interpret |
| H3. The report is shareable without editing | They would send it to a PI/reviewer as-is |
| H4. They trust the verdict and citations | Trust ≥4/5 and they can name the deciding check |
| H5. It is worth paying for | Clear WTP or a named budget/next step |

If H1–H4 fail, do not add features; fix the defaults/UX first.

## 2. Who to recruit

- **Lone computational biologist** — runs variant pipelines, is the lab bottleneck.
- **Wet-lab scientist who cannot code** — has a VCF from a collaborator.
- **Core facility** — runs panels/WES for many labs.
- **Biotech researcher** — needs a defensible provenance/report trail.

At least one germline/panel user and one somatic/tumor user if possible.

## 3. Pre-work request

Ask for the smallest real dataset that exercises their workflow:

- An annotated VCF (VEP `CSQ` or SnpEff `ANN`).
- A panel BED or GTF + gene list.
- A depth TSV (`samtools depth -a`) or a BAM/CRAM + target BED.
- Optional: a trio multi-sample VCF + PED, or a tumor/normal VCF + CNV segments.
- Optional: one redacted report they currently produce (publication/internal).

Privacy:

- Run locally; raw reads/BAMs must not leave their machine.
- Use file paths or hashed labels in screenshots; redact sample IDs.
- No clinical claims; the report is research-use only.

Setup check before the session:

```bash
uv sync
uv run contig --help
uv run contig variants --help
uv run contig readiness --help
uv run contig report --help
```

## 4. Session script (60–90 min)

### 0–5 min: consent and context
- Research-use validation, not a clinical product.
- We record notes and anonymized commands, not raw data.
- They can stop or delete anything at any time.

### 5–15 min: baseline
Ask:
- How do you do this today? Which tools/scripts?
- How long does a first-pass variant shortlist take?
- What usually goes wrong?
- What do you currently hand to a PI/reviewer?

### 15–55 min: tasks on their data

**Task A — Panel (5 min)**
```bash
uv run contig panel-build --name "Partner panel" --genes <their genes> \
  --gtf <their GTF> --hgnc <HGNC TSV> --version 1 --out-dir panels
uv run contig panel-list --dir panels
```
Observe: did HGNC aliases resolve? Was the BED what they expected?

**Task B — Variant evidence (15 min)**
```bash
uv run contig variants <their VCF> --clinvar <ClinVar VCF> --build GRCh38 \
  --gene <their genes> --max-af 0.01 --pass-only --out variants.tsv
```
Optional:
```bash
uv run contig variants <their VCF> --gnomad-api --gnomad-cache gnomad.json --out variants.tsv
```
Observe: did the filters match their mental model? Which columns are missing?
Did they trust “ClinVar reports …” without reading it as a Contig call?

**Task C — Readiness (10 min)**
```bash
uv run contig readiness --depth depth.tsv --bed panels/<id>.bed \
  --caveats homology_caveats_GRCh38.bed --out readiness.tsv
# or: --bam sample.cram --reference GRCh38.fa
```
Observe: did any `not-interpretable`/`caution` state change their plan? Were the
thresholds too strict/too loose for their panel?

**Task D — Report (10 min)**
```bash
uv run contig report <run-id> --variants variants.tsv.json --readiness readiness.json \
  --out report.html --meta report.json
uv run contig report-check report.json
```
Observe: would they send this to a PI/reviewer? What wording is wrong? Is the
HTML/print-to-PDF enough?

**Task E — Ask (5 min)**
```bash
uv run contig ask <run-id> "what is the verdict?" --variants variants.json --readiness readiness.json
uv run contig ask <run-id> "is <gene> ready?" --readiness readiness.json
```
Observe: did the citations make the answer trustworthy? Did they ask something
the router refused that it should answer?

**Task F — Optional family / biomarkers / cohort**
```bash
uv run contig family --vcf trio.vcf --ped trio.ped --out family.tsv
uv run contig biomarkers --vcf somatic.vcf --callable-bed regions.bed \
  --msi-output msisensor.output --reported-msi MSI --out biomarkers.tsv
uv run contig cohort-build --name "Lab cohort" --variants a.json,b.json --out cohort.json
```
Only run the surfaces that match their work.

### 55–75 min: feedback
Ask, in this order:
1. What was the most useful thing you saw?
2. Where did you get stuck or stop trusting it?
3. Which threshold or filter is wrong for your data?
4. What is missing that would make this a weekly tool?
5. Would you pay for it? From which budget? How much?
6. Would you recommend it to a colleague? Why/why not?

## 5. Scorecard

Record one row per partner in `docs/validation/scorecard.csv`:

| Field | Definition |
|---|---|
| partner | Anonymous ID (P1…) |
| persona | comp bio / wet-lab / core / biotech |
| data | germline / somatic / trio / panel / other |
| task_a..f | success: yes / assisted / no |
| time_to_first_table | minutes |
| trust | 1–5 |
| usefulness | 1–5 |
| report_shareable | yes / with edits / no |
| nps | 0–10 |
| wtp | amount + budget source, or “no” |
| top_friction | 1–3 items |
| top_missing | 1–3 items |
| quote | one sentence |

## 6. Decision gate

- **Proceed** if ≥3/5 complete the core tasks (A–D) and either trust ≥4 or a
  clear WTP/next step.
- **Fix first** if tasks complete but trust <4 or the report needs heavy edits.
- **Pivot** if <3/5 complete the core tasks; re-examine the persona, data shape,
  or the wedge. Do not add features to compensate.

## 7. What to change based on evidence

| Finding | Change |
|---|---|
| Filters don’t match their model | Adjust defaults/docs; add a saved preset |
| Readiness thresholds too strict/loose | Record their panel-specific defaults; do not change global blindly |
| Report needs heavy editing | Add template fields/sections; consider PDF |
| Ask refuses too much | Add an intent/eval case; keep citations |
| Trio/CNV/MSI is the real need | Prioritize that follow-up with their data |
| They won’t pay | Stop; revisit the wedge/persona |

## 8. One-page partner brief (email)

> **Contig research-workbench validation**
>
> We are validating a research-use variant/report workflow on real lab data.
> It runs locally on your machine, never sends raw reads, and makes no clinical
> claims. We ask for one 60–90 minute session on a dataset you already have
> (VCF + panel/BED; optional depth/BAM, trio, or tumor/normal).
>
> You will get: a filtered variant table, a coverage/readiness table, a
> shareable HTML report with hashed provenance, and a short feedback session.
> We will use your anonymized feedback to fix defaults and the report.
>
> If you are interested, reply with the data shape you have and a 60-minute slot.

## 9. After the sessions

- Fill `scorecard.csv`; keep anonymized notes.
- Write a one-page findings memo: what worked, what broke, what to build next.
- Reorder `BACKLOG.md` by what partners actually hit.
- Only then decide whether to cut a release or build M8 federation.

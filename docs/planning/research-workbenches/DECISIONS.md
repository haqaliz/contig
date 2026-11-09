# Research-workbench decisions

Date: 2026-11-08. These answers close the open product/technical questions for
the remaining research-workbench work. They are the source of truth for the next
build cycle.

## Deployment and product surface

| Question | Decision |
|---|---|
| Where does the next phase run? | **Local CLI + local dashboard**; no hosted multi-user backend yet. |
| Dashboard scope | **Read-only** first: variants, readiness, report, ask, family, biomarkers, cohort. No launch/approve actions in the first release. |
| Dashboard data source | **Static JSON/bundles from disk**, like the current dashboard; move to an API only when write actions are needed. |
| Dashboard stack | Keep the existing Next.js app. |
| Release timing | **After validation**, not before. |
| First build after validation | **Dashboard integration**. |

## Data and licensing

| Question | Decision |
|---|---|
| Data/licensing policy | **Open-only**: ClinVar, gnomAD, GIAB, 1000G, Iranome, CIViC, ClinGen, HPO, GENCODE, MANE, HGNC. |
| Licensed sources | **Not used**, despite the multi-select interest: the open-only policy wins. OMIM, NCCN, COSMIC, OncoKB, HGMD, and commercial CADD/SpliceAI are out. |
| Iranome access | **Keep the per-gene browser scrape** for now; add **GRCh37→GRCh38 UCSC liftover**. |
| gnomAD / ClinVar | Keep the existing API/cache and FTP/VCF paths; no new work unless rate limits bite. |
| HPO | Add as optional phenotype context for family analysis; no ranking model. |
| CIViC | Add as attributed cancer evidence; no drug/treatment recommendation. |
| VEP | Support **both**: consume VEP `CSQ`/SnpEff `ANN` from input VCFs by default, with an optional local VEP runner/cache. |
| ACMG | **Display-only, ClinVar only**: show ClinVar's aggregate classification and review status, attributed. Contig never computes its own ACMG call. |

## Model and assistant

| Question | Decision |
|---|---|
| LLM path | **OpenAI small/cheap model as the default**, plus a configurable local OpenAI-compatible endpoint. |
| Bundle text privacy | Hosted LLM may receive **redacted bundle text** (paths/sample IDs removed). Raw reads never leave the machine. |
| Assistant scope | Keep the deterministic grounded router as the source of truth; the LLM only paraphrases/answers from the provided context. Actions remain approval-gated. |

## Analysis extensions

| Question | Decision |
|---|---|
| M4 PDF | **Browser print-to-PDF** from the self-contained HTML; no native PDF dependency now. |
| WGS scale | **Require `--region` or `--gene` first** for large VCFs; add streaming/indexing only if a partner hits the guard. |
| M6 family | **Multiple families/quads and carrier/couple views shipped**; X/Y/MT basic rules shipped. Carrier/couple views are autosomal only in this slice. |
| M2 sample QC | **VCF-only sex check shipped** (`--sex-vcf`/`--expected-sex`); relatedness and non-sex sample-identity checks remain deferred. No BAM requirement. |
| M8 | **PRD + architecture only**: consent, k-anonymity/privacy, tenancy, threat model, legal checklist. No federated code until two labs ask. |

## Validation

| Question | Decision |
|---|---|
| Human partner recruitment | **Resume now.** Source/contact routes are in `docs/validation/DATA_AND_PARTNER_ACQUISITION.md`; the executable outreach kit is `docs/validation/OUTREACH_KIT.md`. |
| Agent validation scope | Task completion, command ergonomics, error messages, documentation gaps, reproducibility. |
| Agent validation status | **Run 2026-11-08**; four personas. Blockers fixed (panel versioning, cohort dedupe, report HTML check, signed label, evidence columns, ask actions, frequency naming, gene-level readiness). Remaining findings are backlog. |
| Agent validation limits | Agents **cannot** validate real trust, willingness-to-pay, or messy real-world data. Those still need humans later. |
| Passing bar | If agents hit blockers, fix them before the dashboard. A future human gate is **≥3/5 complete core tasks and trust ≥4**. |
| Partner recruitment | **Resume via the outreach kit**: nf-core Slack, warm intros, ABRF core facilities, NHS GLHs, AMP, Biostars/Reddit. Track in `outreach_targets.csv`. |
| Dashboard auto-discovery | **Explicit `dashboard/research/manifest.json` remains the default.** Read-only per-run auto-discovery of the newest `runs/<run_id>/research/manifest.json` is **shipped**; no dashboard write/launch actions. |
| M5 live LLM | **Local eval run 2026-11-09** with `qwen2.5:1.5b`; 9/9 grounding checks pass after the fidelity guard. Hosted small-model default remains pending the redacted-bundle + provider/privacy check. See `docs/validation/M5_LLM_EVAL.md`. |

## Resulting work order

1. **Agent-partner harness + synthetic validation** — define personas, run the
   task script, fix blockers.
2. **Read-only dashboard** — all surfaces over static JSON.
3. **M5 assistant actions/chat** — OpenAI small/cheap + local endpoint, redacted
   context, approval-gated actions.
4. **M1 data integrations** — UCSC GRCh37→GRCh38 liftover, optional local VEP
   runner, HPO, CIViC (open-only).
5. **M6 multiple families/quads**.
6. **M2 VCF-only sample QC** (sex/relatedness/swap).
7. **WGS region/gene guard** (and streaming only if needed).
8. **M8 PRD + architecture** (no code).
9. **M4 PDF** via browser print (documentation only).

## Explicitly not doing

- Hosted multi-user/cloud deployment.
- Licensed clinical databases.
- Contig-authored ACMG classification.
- Drug/treatment recommendations.
- Federated M8 code before legal/privacy and two-lab demand.
- Native PDF, full document editor, or dashboard write actions in the first release.

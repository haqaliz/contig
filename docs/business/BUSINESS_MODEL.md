# Contig — Business Model, Fundraising & Exit

> **What Contig is.** An agentic bioinformatics analyst. It ingests raw sequencing data, selects and runs the right pipeline on the user's own compute, debugs and self-heals when things break, and returns a *verified, reproducible* result.
>
> **Where the company lives.** Not in Layer 1 (natural-language → script generation — crowded, commoditizing). In **Layer 2: run / debug / self-heal / verify / reproduce, end to end.** That layer is unsolved, and the moat is execution + verification + reproducibility infrastructure plus accumulated workflow-evaluation data — *not* prompting.
>
> **Why now / why fundable.** "AI agents for science" is a live, hot investment thesis. The hard part is engineering — which is exactly the founder's unfair advantage — and the technical bar is high enough to deter most non-technical founders. A working agent that closes the gap from roughly **17% open-answer accuracy** (Claude 3.5 Sonnet on the original BixBench computational-biology benchmark) to something operationally useful on real pipelines is a credible, defensible company.

*Companion docs: detailed go-to-market in `docs/business/GTM.md`. This document covers revenue model, unit economics, segments, fundraising, exit, defensibility, and risks.*

---

## 1. Revenue model

Contig earns money two ways, deliberately bundled:

1. **Per-seat SaaS** — recurring access to the agent (the "analyst").
2. **Usage-based managed compute** — an optional, marked-up layer when Contig provisions and runs pipelines on cloud compute on the customer's behalf (vs. running on the customer's own infrastructure / cloud account, which carries no compute margin but still pays a seat).

This split matters: the **seat captures the value of the intelligence/verification**, and the **compute line captures operational value** for users who don't want to manage their own infrastructure. Customers who bring their own compute (BYOC) still pay full seat price, preserving margin even when we earn nothing on compute.

### 1.1 Pricing tiers

| Tier | Target buyer | Price (anchor) | Seats | Compute | Rationale |
|------|--------------|----------------|-------|---------|-----------|
| **Free / Academic-validation** | Grad students, individual academics, "kick the tires" | $0 (capped runs, BYOC only, watermarked/exportable repro records) | 1 | BYOC only | Adoption + collecting workflow-eval data. Academia is low-ACV but high-volume and the best validation surface. |
| **Individual / Pro** | Lone computational biologist | **$50–200 / mo** per seat | 1 | BYOC or metered | The core wedge persona. $200 if heavy verification/reproducibility features included. |
| **Team / Lab** | A lab or small group (PI + 3–8 members) | **$500–1,500 / mo** (per-lab, banded by seats) | 3–10 | Pooled metered + BYOC | Lands the PI as buyer; shared repro records and run history across the lab. Comparable to Pluto Bio's lab/academia plans at $400–899/mo ([pluto.bio/pricing](https://pluto.bio/pricing)). |
| **Core facility** | Sequencing / bioinformatics core serving many labs | **Custom, $25k–100k+ / yr** + compute margin | 10–50+ | Heavy metered + multi-tenant | Core facilities are a force-multiplier: one contract serves dozens of downstream labs. Strong usage-based upside. |
| **Biotech / Pharma enterprise** | Biotech R&D, pharma computational groups | **Custom, $100k–500k+ / yr** | 25–unlimited | BYOC in their cloud (VPC/private deploy) + premium support | Highest ACV. Buys reproducibility/audit, security, private deployment, SLAs. Longer cycle; venture-scale path. |

> Dollar figures above are **pricing hypotheses to validate** against design-partner willingness-to-pay, not committed list prices. Academic/lab anchors are benchmarked to Pluto Bio's published plans; enterprise anchors are typical for life-sciences R&D SaaS but **[to verify]** for this category.

### 1.2 The compute-usage component

- **BYOC (bring your own cloud):** Contig orchestrates runs inside the customer's AWS/GCP/Azure account or HPC cluster. We charge **only the seat**; the customer pays their cloud provider directly. Zero compute COGS, zero compute margin, but maximum trust (data never leaves their environment — critical for pharma).
- **Managed compute (metered):** Contig provisions compute, runs the pipeline, and bills the customer a **marked-up rate** over our underlying cloud cost. Analogous to how AWS HealthOmics charges per private-workflow run (compute by instance-hour + run-storage per GB-hour) and fixed-price Ready2Run workflows ([aws.amazon.com/healthomics/pricing](https://aws.amazon.com/healthomics/pricing/)), and how Seqera/Latch meter compute per core-hour/credit. **Competitive caveat:** Terra.bio passes Google Cloud cost through with *zero markup* ([support.terra.bio](https://support.terra.bio/hc/en-us/articles/6123082826651-Overview-Costs-and-billing-in-Terra-GCP)) — so Contig cannot justify a compute markup on raw cycles alone. Our markup is earned by *self-healing* (failed runs the agent fixes and re-runs without human intervention) and *verification* (the customer pays for a result they can trust, not just compute time). Where that value isn't credible, default to BYOC and earn on the seat.

**Pricing principle:** never let the compute line cannibalize the seat. Compute is a convenience/margin add-on; the intelligence is the product.

### 1.3 Free tier & academic strategy

- **Goal of free/academic is not revenue — it's the data flywheel and distribution.** Every run (success or failure, on real data) feeds the workflow-eval corpus that *is* the moat.
- Generous free tier for individual academics on BYOC, capped by number of runs/month and gated behind .edu / ORCID verification.
- Paid academic lab plans priced to fit grant budgets (low hundreds/month), matching the Pluto Bio academia band.
- Publish reproducibility records as a feature academics *want to cite* (a Contig run = a shareable, re-runnable methods artifact) — turns users into a citation/marketing channel.

---

## 2. Unit economics (sketch)

### 2.1 What drives cost (COGS)

| Cost driver | Notes |
|-------------|-------|
| **LLM tokens** | Agent loops (plan → run → read errors → fix → re-run → verify) are token-heavy. Self-healing multiplies token spend per task — this is the #1 variable cost on the SaaS line. Mitigate with caching, smaller models for routine steps, and reserving frontier models for hard reasoning. |
| **Managed compute** | Only on the metered tier. Pass-through cloud cost (CPU/GPU/memory + run storage). Failed-and-retried runs add cost — but self-healing is the value, so price it in. |
| **Storage / data egress** | Intermediate files, run artifacts, repro records. Minimal on BYOC; real on managed. |
| **Verification overhead** | Re-running / cross-checking results consumes both tokens and compute — a deliberate cost we monetize as trust. |

### 2.2 What drives revenue

- **Predictable:** per-seat MRR (high gross margin, ~80–90% software-like once token cost per active seat is controlled).
- **Variable:** managed-compute markup (lower gross margin — bounded by cloud cost — but scales with usage and lands expansion revenue).

### 2.3 Gross-margin considerations of bundling compute

| Mix | Gross margin profile | Strategic read |
|-----|----------------------|----------------|
| Seat-only (BYOC) | High (software-like, minus LLM tokens) | Best margin; pursue with technical ICPs and pharma (who insist on BYOC anyway). |
| Seat + managed compute | Blended down by pass-through compute COGS | Lower % margin but larger absolute dollars + stickiness; great for non-technical/wet-lab users who won't run their own infra. |

> **Key tension:** bundling managed compute inflates revenue but dilutes gross margin and can spook margin-focused investors. **Recommendation:** report seat ARR and compute revenue *separately*; lead investor conversations with high-margin seat ARR, treat compute as expansion. Keep the blended gross margin honestly modeled. The biggest controllable risk to margin is **LLM token spend per active seat** — instrument it from day one.

---

## 3. Customer segments (ranked) & recommended sequencing

| Rank by ACV | Segment | ACV | Sales cycle | Willingness-to-pay | Strategic role |
|-------------|---------|-----|-------------|--------------------|----------------|
| 1 | Biotech / Pharma R&D | Highest ($100k–500k+) | Long (3–9+ mo) | Strong (budgets exist) | Venture-scale revenue; demands security/repro/private deploy. |
| 2 | Core facilities | High ($25k–100k+) | Medium | Moderate–strong (grant + chargeback) | One contract → many labs; usage-based upside. |
| 3 | Team / Lab | Medium ($6k–18k/yr) | Short–medium | Moderate (grant-constrained) | PI-led land; good repeatable mid-market. |
| 4 | Lone computational biologist | Low ($600–2,400/yr) | Self-serve, instant | Variable | The wedge ICP; fastest signal; cheapest to acquire. |
| 5 | Individual academic (free) | ~$0 | Self-serve | Low | Data flywheel + distribution, not revenue. |

### Recommended sequencing (land → expand)

1. **Land first: lone computational biologist (self-serve) + free academics.** Fastest path to real usage on real pipelines, lowest CAC, and it builds the eval-data moat. This is where the wedge proves itself and where the product earns word-of-mouth among the people who *evaluate tools for everyone else*.
2. **Then: wet-lab scientists who can't code** (within the same labs) — highest "magic moment," expands seats inside accounts you already touched.
3. **Then: labs and core facilities** — turn happy individuals into team/facility contracts (PI as buyer). Core facilities are the multiplier.
4. **Finally: biotech/pharma enterprise** — pursue once reproducibility, security, and BYOC private deployment are hardened and you have logos/case studies. This is the venture-scale, long-cycle prize — don't start here.

> Rationale: academic = low ACV but grant-funded and ideal for validation; biotech/pharma = high ACV but long cycles. Start where signal is cheap and fast, accumulate proof + data, then climb the ACV ladder. GTM specifics live in `docs/business/GTM.md`.

---

## 4. Go-to-revenue motion (high level)

Two motions, run in sequence and eventually in parallel:

| Motion | Segments | Mechanics |
|--------|----------|-----------|
| **Bottoms-up self-serve** (primary, early) | Individuals, labs, free academics | Frictionless signup, BYOC connect, instant value on a real dataset, usage-based + seat checkout. Product-led growth; community/open-source presence (the bioinformatics world lives on GitHub, nf-core, Biostars, Twitter/Bluesky). |
| **Enterprise sales** (later, higher ACV) | Core facilities, biotech/pharma | Founder-led design partnerships → security review → private/VPC deployment → annual contract with SLA. Reproducibility/audit as the wedge into regulated R&D. |

Net: **land bottoms-up, expand into enterprise.** Detailed channel/positioning/funnel work is in `docs/business/GTM.md`.

---

## 5. Fundraising path

### 5.1 Bootstrap vs. pre-seed vs. seed

| Path | When it fits | What it buys |
|------|--------------|--------------|
| **Bootstrap** | Until a working agent demonstrably beats the ~17% baseline on real pipelines and a handful of users pay | Maximum ownership; forces focus on the hard engineering moat. Viable because the founder *is* the build team. |
| **Pre-seed** | Once there's a demo + early design partners + a credible eval story | Runway to convert the demo into retained, paying self-serve users and to instrument the data flywheel. |
| **Seed** | Once there's repeatable self-serve revenue, retention, and an eval-data moat that's visibly compounding | Hire to build the verification/reproducibility/integration platform and start enterprise motion. |

### 5.2 Milestones that unlock each stage

- **→ Pre-seed:** working end-to-end agent on ≥2 common pipelines (e.g. RNA-seq, variant calling); measurable lift over the BixBench-style baseline; 3–5 active design partners; reproducibility records as a tangible artifact.
- **→ Seed:** self-serve revenue with retention; demonstrable data flywheel (eval corpus → measurable accuracy gains per quarter); first lab/facility contract; evidence the moat is engineering + data, not prompts.
- **→ Series A:** multiple core-facility/biotech logos, expanding net revenue retention, defensible verification infra, and a clear compute-margin story.

### 5.3 What an "AI agents for science" investor wants to see

1. **A real, hard technical moat** — execution/verification/reproducibility infra + accumulated workflow-eval data, *not* a wrapper prompt. (This is the explicit thesis of the wedge.)
2. **Founder-market fit on the *engineering*** — the bar deters non-technical founders; lean into that as the unfair advantage.
3. **Evidence of closing the accuracy gap** on *real* pipelines (the 17% → useful story), with an eval methodology you own.
4. **A data flywheel** that gets better with every run (defensibility over time).
5. **Many credible exit doors** (Section 6) — de-risks the venture bet.
6. **Honest unit economics** — high-margin seat ARR led, compute as expansion.

### 5.4 Comparable funded startups (real figures)

**Closest comps — bioinformatics platforms & agentic tools (the Contig category):**

| Company | What they do | Funding (most recent / total) | Source |
|---------|--------------|-------------------------------|--------|
| **Tamarind Bio** (YC) | No-code AI/simulation platform (AlphaFold, RFdiffusion, 200+ models) — closest "agentic, accessible bio" comp | **$13.6M Series A**, Feb 2026; ~$14M total | [GEN](https://www.genengnews.com/topics/artificial-intelligence/tamarind-bio-secures-13-6m-series-a-to-make-ai-more-accessible-for-biology/) |
| **LatchBio** (YC) | Code-free bioinformatics data + pipeline platform ("AWS×GitHub for biocomputing") | **$28M Series A**, June 2022, co-led by Coatue + Lux; ~$33M total | [latch.bio blog](https://blog.latch.bio/p/announcing-our-series-a-building), [VentureBeat](https://venturebeat.com/data-infrastructure/latchbio-raises-28m-to-corral-bio-data) |
| **Seqera Labs** | Commercial Nextflow / nf-core pipeline orchestration | **$26M Series B**, May 2025 (Addition); prior €22M Series A (2022), $5.5M seed; ~$50–55M total | [seqera.io Series B](https://seqera.io/blog/seqera-raises-26m-series-b/), [pricing](https://seqera.io/pricing/) |
| **Pluto Bio** | Multi-omics analysis platform | **$3.6M** (May 2025, Kickstart, labeled seed); ~$8.3M total | [BusinessWire](https://www.businesswire.com/news/home/20250513706622/en/Pluto-Bio-Raises-%243.6M-to-Expand-AI-Powered-Multi-Omics-Analysis-Platform-for-Pharma), [pricing](https://pluto.bio/pricing) |
| **Lamin Labs** (YC S22) | Data lineage / lineage DB for bio (LaminDB); clearest published seat pricing in the set | ~$500K pre-seed/seed **[to verify]** | [lamin.ai/pricing](https://lamin.ai/pricing) |
| **FutureHouse → Edison Scientific** | Nonprofit "AI Scientist" (authors of BixBench) + commercial spinout (Kosmos "AI co-scientist") | Nonprofit: Schmidt/OpenPhil/NSF-funded (~$20M est. spend by end-2024). Spinout **Edison: $70M seed @ ~$250M val** (Dec 2025, Spark + Triatomic) | [futurehouse.org/about](https://www.futurehouse.org/about), [Endpoints](https://endpoints.news/ai-startup-edison-raises-70m-seed-for-research-software/) |

**Adjacent — "AI for science" / AI-bio model companies (thesis validation, frontier round sizes):**

| Company | What they do | Funding (most recent) | Source |
|---------|--------------|-----------------------|--------|
| **Periodic Labs** | AI-automated science | **$300M seed** @ ~$1.3B val, Sept 2025, a16z | [TechCrunch](https://techcrunch.com/2025/09/30/former-openai-and-deepmind-researchers-raise-whopping-300m-seed-to-automate-science) |
| **EvolutionaryScale** (ESM3) | Protein language models | **$142M seed**, June 2024 (Friedman/Gross/Lux + Amazon, NVIDIA) | [TechCrunch](https://techcrunch.com/2024/06/25/evolutionaryscale-backed-by-amazon-and-nvidia-raises-142m-for-protein-generating-ai/) |
| **Chai Discovery** | Molecular-structure AI | **$130M Series B** @ $1.3B val, Dec 2025 | [Built In SF](https://www.builtinsf.com/articles/chai-discovery-raises-130m-series-b-20251217) |
| **Cradle** | AI protein design | **$73M Series B**, Nov 2024 (IVP); ~$97M total | [TechCrunch](https://techcrunch.com/2024/11/26/cradle-builds-out-its-protein-design-ai-platform-and-wet-lab-with-73m-in-new-funding/) |

**Acquirer-class comps (large platforms — see Section 6):**

| Company | What they do | Funding / valuation | Source |
|---------|--------------|---------------------|--------|
| **Benchling** | Life-sciences R&D cloud / ELN | **$100M Series F @ $6.1B val** (Nov 2021); ~$412M total; ~$210M ARR (2024) **[to verify]** | [Bloomberg](https://www.bloomberg.com/news/articles/2021-11-18/biotech-platform-benchling-valued-at-6-1-billion-in-new-funding), [Sacra](https://sacra.com/c/benchling/) |
| **DNAnexus** | Genomics cloud platform | **$200M Series I** @ ~$600M val (Mar 2022, Blackstone Growth); ~$473M total | [DNAnexus press](https://www.dnanexus.com/press/dnanexus-secures-200-million-funding) |

> **Takeaway for the deck:** the *bioinformatics platform* layer funds Series-A/B rounds in the **$13–28M** range (Tamarind, Latch, Seqera) — a realistic early target for Contig. The broader **"AI for science" thesis is red-hot** ($142M–$300M *seeds* for EvolutionaryScale, Periodic Labs; Edison's $70M seed @ $250M for a science-agent spinout) — validating that investors will pay up for agentic-science teams with a real technical moat. The acquirer tier (Benchling $6.1B, DNAnexus ~$473M raised) shows the eventual buyers have the balance sheets. FutureHouse conveniently *defines the benchmark Contig beats* and then spun out a $250M company on the thesis.

---

## 6. Acquisition thesis

**This is the strongest exit of the ideas considered — many doors.** Contig is a natural tuck-in for anyone who owns either (a) an installed base of scientists or (b) a genomics-compute platform that lacks an intelligent execution/verification layer.

| Acquirer class | Specific acquirers | Why they buy Contig |
|----------------|--------------------|--------------------|
| **Hyperscaler genomics clouds** | AWS HealthOmics, Google Cloud Life Sciences | They own the compute and pipelines but not the *agent* that drives them. Contig makes their platform self-driving and trustworthy → more consumption. |
| **Genomics platforms** | DNAnexus (~$473M raised, $200M Series I 2022), Terra / Broad, Latch Bio, Seqera (Nextflow) | They own workflows/orchestration; Contig adds self-healing + verification + reproducibility on top. Direct capability tuck-in. |
| **Sequencing incumbents** | Illumina | Owns the instruments + downstream analysis ambitions; Contig is the analyst layer that closes the loop from reads to verified result. |
| **R&D cloud / ELN** | Benchling | Owns the scientist's daily workflow; Contig extends from data capture into automated, reproducible analysis. |
| **Pharma R&D** | Large pharma internal platforms | Buy to internalize a verified, auditable analysis agent for regulated pipelines. |

**What makes Contig an attractive tuck-in:** an *installed base of scientists* (distribution) **plus** an *execution/verification layer* (capability the acquirer can't easily build because it requires the same deterring engineering bar). The accumulated workflow-eval data is non-replicable.

**Build to maximize multiple doors (and the multiple):**
- **Cloud-neutral BYOC** — run on AWS, GCP, Azure, and HPC, so no single hyperscaler is the only viable buyer (preserves competitive tension).
- **Pipeline-engine-neutral** — interoperate with Nextflow/nf-core, Snakemake, WDL/Terra so platform acquirers see immediate fit.
- **Reproducibility records as a portable standard** — an asset that travels into any acquirer's product.
- **Logos across academia → core facility → biotech** — proves the installed base every acquirer wants.

---

## 7. Defensibility & moat over time

The moat is **not** the prompt. It compounds:

1. **Workflow-eval data flywheel** — every run (success *and* failure, on real data) teaches the system which pipelines, parameters, and fixes work. This is the asset competitors and foundation-model vendors can't buy. More runs → better self-healing → better results → more runs.
2. **Reproducibility records** — an accumulating corpus of verified, re-runnable analyses becomes both a product feature (citable methods artifacts) and a switching cost.
3. **Execution/verification infrastructure** — the hard, unglamorous engineering of running, debugging, and *proving* results across heterogeneous compute. High to build, high to deter.
4. **Integrations** — connectors to clouds, HPC, pipeline engines, and data sources create distribution + stickiness; each integration is a small moat brick.

Over time, the defensibility shifts from "we have a clever agent" (copyable) to "we have the largest verified-run dataset and the deepest execution integrations in bioinformatics" (not copyable).

---

## 8. Key business risks & mitigations

| Risk | Why it matters | Mitigation |
|------|----------------|------------|
| **Willingness-to-pay in academia** | Academic budgets are grant-constrained; free expectations are strong | Treat academia as validation + data flywheel, not revenue. Price lab plans to grants. Monetize core facilities (chargeback budgets) and climb to biotech for real ACV. |
| **Foundation models commoditize the agent** | If frontier models get good at bioinformatics out-of-the-box, the "intelligence" gap shrinks | Moat is *execution/verification/reproducibility + eval data*, which improves *with* better base models rather than being replaced by them. Stay model-agnostic; ride the wave, don't fight it. |
| **Long enterprise sales cycles** | Biotech/pharma cycles are 3–9+ months; cash risk | Land bottoms-up first for fast revenue + proof; start enterprise motion only once self-serve funds runway. BYOC/private deploy removes security objections early. |
| **LLM token cost erodes margin** | Self-healing loops are token-hungry | Instrument token cost per seat from day one; cache; tier models (small for routine, frontier for hard); price the Pro tier to cover heavy use. |
| **Managed-compute margin dilution** | Bundling compute lowers blended GM and can worry investors | Report seat ARR vs. compute revenue separately; lead with high-margin seat ARR; keep BYOC as a zero-COGS default. |
| **Trust / correctness liability** | A wrong "verified" result in a clinical/biotech context is serious | Founder lacks wet-lab/clinical credentials → stay firmly in *research/analysis* (not diagnostic/clinical) positioning; make verification conservative and auditable; partner for any regulated use. |
| **Incumbent builds it** | Acquirers could build the layer themselves | The deterring engineering bar + accumulated eval data is the defense; move fast on the data flywheel so a build-vs-buy calc favors buy. |

---

### Appendix — key external anchors

**Benchmark (the gap Contig exists to close):**
- **BixBench** (FutureHouse): original open-answer accuracy ~**17%** (Claude 3.5 Sonnet), ~9% (GPT-4o); on multiple-choice with opt-out, frontier models scored *below random chance*. [arxiv.org/abs/2503.00096](https://arxiv.org/abs/2503.00096), [futurehouse.org/research-announcements/bixbench](https://www.futurehouse.org/research-announcements/bixbench)

**Managed-compute pricing models (for the metered tier markup reference):**
- **AWS HealthOmics** — pay-as-you-go: private workflows billed by instance-hour (e.g. `omics.m.xlarge` ~$0.2592/hr, `omics.r.8xlarge` ~$2.72/hr); run storage static $0.0001918/GB-hr or dynamic $0.000411/GB-hr; Ready2Run workflows flat per-run (e.g. GATK germline ~$10/run); sequence stores per gigabase-month. [aws.amazon.com/healthomics/pricing](https://aws.amazon.com/healthomics/pricing/)
- **Terra.bio** — platform is *free*; users pay **Google Cloud costs pass-through with no markup**. Important competitive signal: Contig's metered markup must be *justified by self-healing + verification*, since a major incumbent charges zero platform margin on compute. [support.terra.bio](https://support.terra.bio/hc/en-us/articles/6123082826651-Overview-Costs-and-billing-in-Terra-GCP)
- **Seqera Compute** — usage-based: CPU $0.10/CPU-hr, mem $0.025/GiB-hr, storage $0.025/GB/mo. **LatchBio** — credit-based ($1 = 1 credit), compute metered per core-second. [seqera.io/pricing](https://seqera.io/pricing/), [latch.bio/pricing](https://latch.bio/pricing)

**Seat-pricing benchmarks:**
- **Pluto Bio** — academia/lab plans $400–899/mo. [pluto.bio/pricing](https://pluto.bio/pricing)
- **Lamin** — Free (OSS) / **Pro $30/mo** / **Team from $640/mo** / Enterprise — clearest published bio-data seat ladder. [lamin.ai/pricing](https://lamin.ai/pricing)
- **Bioinformatician salary** (the human Contig augments): US avg ~**$110k/yr** (~$53/hr). [salary.com](https://www.salary.com/research/salary/listing/bioinformatician-salary) — frames willingness-to-pay: a $50–200/mo seat is trivial against a six-figure salary it makes more productive.

> All dollar pricing tiers in this doc are **hypotheses to validate** with design partners; figures marked **[to verify]** are unconfirmed.

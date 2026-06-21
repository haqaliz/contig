# Contig - Go-To-Market Plan

> **Contig** runs raw sequencing data through the right pipeline on the user's own compute, self-heals when steps fail, and returns a **verified, reproducible** result. We sell the part everyone else skips: actually getting a correct, runnable, reproducible answer.

---

## The GTM thesis in one paragraph

Bioinformaticians and wet-lab scientists already feel this pain acutely - ~74% of wet-lab scientists can't program, and even skilled practitioners scavenge fixes from Biostars and paper Methods sections rather than building robust pipelines [arxiv.org/html/2507.20122v1; nature.com/articles/s41598-025-25919-z]. AI tools that *generate* scripts don't solve it; on real analytical tasks they score ~17% accuracy [arxiv.org/abs/2503.00096]. So our GTM is: **be genuinely useful in the communities where the pain lives, show real verified runs as proof, win 5 design partners who pay, then expand bottoms-up before going up-market.** Trust - not features - is the bottleneck, and trust is earned in public.

---

## 1. Ideal Customer Profile

### Primary ICP - the lone computational biologist
A bioinformatician (or the one "computational person") supporting a wet lab or small group. They can code *some* but are drowning: every project means re-deriving a pipeline, fighting environment/format/reference issues, and being the bottleneck for everyone else's data. They feel pain on every project and have the credibility to evaluate us.

**Why them first:** highest-frequency pain, competent to judge our verify/reproduce value, and they live in the exact communities we can reach for ~$0.

### Secondary ICPs
| ICP | Pain | Budget owner | Notes |
|-----|------|--------------|-------|
| **Wet-lab scientist who can't code** | Can't analyze own data; waits weeks for the core/computational person | PI / grant | Largest population (~74% can't program) but needs the most hand-holding; great for self-serve once onboarding is smooth |
| **University core facility** | Swamped with repetitive analysis requests; reproducibility/audit pressure | Facility / institutional | Multiplier: one win = many users; values provenance heavily |
| **Small/mid biotech** | Needs reproducible, auditable pipelines; limited bioinformatics headcount | Team/org budget | Higher ACV, longer cycle, data-governance sensitive - go here later |

### Where they hang out
- **Biostars** - the canonical Q&A site; where pipeline pain is literally posted.
- **r/bioinformatics** - active, opinionated, discovery-friendly.
- **Bioinformatics X/Twitter** - "lab Twitter," #bioinformatics, tool authors, core-facility staff.
- **nf-core Slack** - serious pipeline practitioners; the people who care most about reproducibility.
- **University core facilities** - directly reachable by email/intro; concentrated demand.

---

## 2. Customer-Discovery Playbook - First 5 Design Partners

**Goal:** 5 real bioinformaticians using Contig on THEIR data, ending in a clear paid/no-paid answer. This is the engine of Phase 0 in the roadmap.

### Step 1 - Find them (start Week 1, run in parallel)
| Channel | Tactic |
|---------|--------|
| Biostars | Answer real questions in our pipeline's topic genuinely; in profile/signature mention we're building an agent that runs+verifies that pipeline and seeking a few testers |
| r/bioinformatics | A *non-spammy* post: "I built an agent that runs [RNA-seq DE] end-to-end and self-heals the common failures - looking for 5 people to try it on their own data, free, in exchange for a 30-min call." |
| X/Twitter bio community | DM tool authors / core-facility staff / loud lab accounts who've complained about exactly this |
| nf-core Slack | Participate first, then ask for testers in the appropriate channel |
| Core facilities | Direct email to facility managers offering to take repetitive analyses off their plate |

### Step 2 - Pitch (the framing that converts)
Lead with the *outcome and the proof*, not the tech:
> "You give it raw FASTQ and a sample sheet. It runs the whole differential-expression pipeline on your own machine/cluster, fixes the usual breakages itself, and hands you back results **plus a reproducible record of exactly how it got them**. I want to watch you run it on your real data - free - and hear where it breaks."

Always show a **real verified run** (recorded) before asking for their time. Proof beats promises in this community.

### Step 3 - Watch them use it (don't demo *at* them)
- Have them run it on **their own data**, observing (screen-share or recorded).
- Stay quiet; note every confusion, every failure, every "huh."
- The failures are the product roadmap. The confusions are the onboarding roadmap.

### Step 4 - The willingness-to-pay question (the only one that matters)
Run this script with all 5. The deliverable is a credit card or a clear, reasoned no.

> 1. "On a scale where 0 is 'wouldn't use it' and 10 is 'I'd use this on every project' - where are you, and why that number?"
> 2. "If this saved you [X hours/the typical breakage cycle] per analysis, **would you pay for it?**"
> 3. "**How much** - per analysis, per month, or per seat - feels right to you?"
> 4. "**Whose budget** does that come out of - yours, your PI's, the grant, the facility, the company?"
> 5. "If I gave you a link to subscribe right now at $[their number], **would you put a card in today?**" → ask for the card.

Disqualify enthusiasm that isn't backed by a budget owner. "I love it" with no budget = a no.

### 🚦 Decision gate (mirrors the roadmap)
- **≥3/5 reach for a card → proceed to MVP hardening.**
- **<3/5 → pivot.** Use the notes to decide: wrong pipeline, wrong ICP, value not in verify/reproduce, or budget owner elsewhere. Don't add features and re-ask the same people.

---

## 3. Motion Sequencing - Bottoms-up first, sales later

**Recommended order:**

1. **Design-partner / concierge (Phase 0):** hand-held, free→paid pilots with the 5. Not scalable, not meant to be - it's learning.
2. **Bottoms-up self-serve (Phase 1→2):** individual computational biologists sign up, run on their compute, pay with a card. Low CAC, fueled by community reputation. This is the core early motion because our ICP self-selects and self-evaluates.
3. **Team plans (Phase 2):** the lone bioinformatician pulls in their lab/colleagues → shared workspaces → first org revenue. Land-and-expand inside the same building.
4. **Core-facility / biotech sales (Phase 2→3):** only after self-serve proves value and we have provenance/audit/compliance. These need security reviews, data-governance answers ("runs on your compute, data never leaves"), and reference customers - all of which the earlier phases produce.

**Why this order:** the founder has no wet-lab/clinical credentials, so top-down enterprise selling on credibility alone is weak. Bottoms-up lets *the product and verified runs* earn trust, and turns happy individual users into our reference customers and internal champions for the eventual org sale.

---

## 4. Content & Community Strategy

**Principle: be useful first, sell never (directly).** This community has a strong allergy to marketing and a strong love of people who actually help.

| Tactic | What it looks like |
|--------|--------------------|
| **Answer for real** | Genuinely solve Biostars / r/bioinformatics / nf-core Slack questions in our pipeline's domain. Reputation compounds. |
| **Show real verified runs** | Short recordings: messy real dataset → Contig runs it → it self-heals a failure live → verified result + reproducible manifest. This *is* the marketing. |
| **Failure-mode posts** | "The 5 ways RNA-seq DE pipelines break and how to recover from each" - useful even to non-users, and demonstrates our self-heal expertise. |
| **Reproducibility content** | Posts/threads on reproducible Methods sections; tie to the provenance feature. Resonates hard on nf-core Slack. |
| **Build in public** | Share benchmark progress vs. BixBench-style baselines [arxiv.org/abs/2503.00096]; transparency builds trust and recruits testers. |
| **Open-source goodwill** | Open-source a small, genuinely useful piece (e.g. a failure-detection utility) to seed credibility. |

**Hard rules:** never overclaim "verified" beyond what we actually check; never make clinical/diagnostic claims; never astroturf. One caught overclaim in this community is expensive.

---

## 5. Pricing Conversations & Early Monetization Experiments

### Pricing-conversation guidance
- **Anchor on value, let them name the number first** (Step 4 script). We learn their mental model and budget *before* anchoring.
- **Identify the budget owner explicitly** every time. Per-analysis pain (researcher) and per-seat budget (PI/facility) are different sales.
- **Don't over-engineer pricing in Phase 0.** A simple "$X/month" or "$Y/analysis" Stripe link is enough to get a real card. The card is the data point; the model can be refined later.

### Early monetization experiments (Phase 1)
| Experiment | What we learn |
|------------|---------------|
| **Per-analysis (usage) pricing** | Maps to felt pain; low commitment; good for individual researchers |
| **Flat monthly seat** | Predictable; tests whether usage is frequent enough to justify a subscription |
| **Free tier (1 public-data run) → paid for own data** | Activation funnel; tests conversion from "wow" to "paid" |
| **Paid pilot for core facility** | Tests org budget + provenance value early, even before full self-serve |

Run these as real A/Bs across the early cohort; pick the model with the best conversion-from-card.

---

## 6. Metrics to Track

### North-star
**Runs completed without human intervention** - it's the clearest proxy for "our Layer-2 engine actually works," and it's what justifies payment.

### Funnel & health metrics
| Stage | Metric | Early target |
|-------|--------|--------------|
| **Acquisition** | Testers recruited from community per channel | 5 design partners (Phase 0) |
| **Activation** | % new users reaching first verified result | >60% |
| **Activation speed** | Time-to-first-result | < 1 working day |
| **Core value** | % runs completed without human intervention (north-star) | ≥70% (Phase 1) → ≥75% (Phase 2) |
| **Self-heal** | % of failures auto-recovered | ≥4/5 cataloged (Phase 0) → 80%+ (Phase 1) |
| **Conversion** | % design partners who put in a card | ≥3/5 = gate (Phase 0) |
| **Retention** | Active users running ≥2 analyses/month | majority of paying accounts |
| **Expansion** | % accounts on ≥2 pipelines; NRR | NRR >100% (Phase 2) |
| **Moat proxy** | % of users using methods-export / provenance | rising; cited as top-3 reason to stay |
| **Trust** | Verified-run reproducibility rate | 100% of completed runs reproduce |

### Qualitative signals to log every session
- What broke, and whether we self-healed it.
- Where they got confused (onboarding debt).
- Whether they reached for a card - and whose budget.

---

## GTM in one line
**Be the most helpful person in the room (Biostars/Reddit/nf-core), prove it with real verified runs, win 5 paying believers, grow bottoms-up off their trust, then walk up-market into facilities and biotech.**

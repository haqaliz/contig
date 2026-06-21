# Contig: Product Specification

> **One-liner:** Contig ingests a researcher's raw sequencing data, selects and runs the right pipeline on their compute, debugs and self-heals failures, and returns a verified, reproducible result.

---

## 1. Product Overview

### The core promise

**Contig delivers a verified result, not just a script.**

Most "AI for bioinformatics" tooling stops at translation: you describe what you want in English, and you get back a workflow, a command, or a code snippet. The hard part (the part that actually consumes a researcher's week) is everything *after* the script exists: getting it to run on real data and real compute, diagnosing the cryptic failure on hour 6 of a 9-hour job, knowing whether the output is correct or quietly wrong, and being able to reproduce it next month for a reviewer.

Contig owns that second layer. The user states a goal in plain language and provides raw data; Contig produces a result it has *checked*, plus a re-runnable record that proves how it got there.

### Why this layer

The problem is real and well-documented. Roughly 74% of wet-lab scientists cannot program ([arxiv.org/html/2507.20122v1](https://arxiv.org/html/2507.20122v1)), and building working pipelines requires a rare combination of genomics and computational expertise; researchers commonly scavenge solutions from Biostars threads and paper methods sections. Current agentic systems match human experts only on *easy* tasks and fail on medium and complex ones ([nature.com/articles/s41598-025-25919-z](https://www.nature.com/articles/s41598-025-25919-z)). On a benchmark of real bioinformatics analysis tasks (BixBench), the best systems reach only ~17% accuracy ([arxiv.org/abs/2503.00096](https://arxiv.org/abs/2503.00096)).

That gap is the opportunity. Script generation is commoditizing: Galaxy, KNIME, BioMaster, and general-purpose LLMs all do it. **Reliable, verified, reproducible end-to-end execution is essentially unsolved, and it is where the value sits.**

### The two layers

| Layer | What it is | Status | Contig's stance |
|-------|------------|--------|-----------------|
| **Layer 1** | Translate English → script / workflow | Crowded, commoditizing | Use it as a commodity input; do **not** compete here |
| **Layer 2** | Run it, debug it, self-heal failures, verify output, guarantee reproducibility, on the user's data and compute | Largely unsolved | **This is the product** |

---

## 2. Target Users / Personas

### Persona A: The lone computational biologist
A postdoc or staff scientist who *can* code but is the only person in the lab who can. They are a bottleneck: every pipeline run, every failure, every "can you re-run this for the revision" lands on them. Contig gives them leverage: it absorbs the run/debug/verify toil so they spend time on science, not on Conda environments and SLURM exit codes.

**Pain:** time sink, single point of failure, context-switching cost.

### Persona B: The wet-lab scientist who can't code
A bench biologist with deep domain knowledge and zero programming ability, the ~74% ([arxiv 2507.20122v1](https://arxiv.org/html/2507.20122v1)). Today they wait in a queue for the computational person, or give up on analyses entirely. Contig lets them go from data to a trustworthy answer without writing code, and, crucially, without being handed a script they can't evaluate.

**Pain:** total dependence on others; cannot self-serve; cannot judge correctness of results.

### Persona C: The core facility serving many labs
A sequencing/genomics core that runs standardized analyses for dozens of PI groups. They need throughput, consistency, auditability, and the ability to hand back results a non-expert PI can trust and reproduce. Contig is a force multiplier and a standardization layer across heterogeneous requests.

**Pain:** volume, consistency across operators, reproducibility/audit demands, support load from confused PIs.

### Persona D: The biotech researcher
An industry scientist working under reproducibility, provenance, and (eventually) compliance pressure. They care less about saving $200 of cloud compute and more about a defensible, reproducible record and results they can stand behind internally.

**Pain:** provenance and reproducibility requirements; reproducible-result accountability; speed-to-decision.

---

## 3. Core User Journeys

### 3.1 Primary journey: data + goal → verified result

1. **Drop data + state goal.** The user uploads or points Contig at raw inputs (e.g. FASTQ files) and describes the goal in plain language: *"Find genes differentially expressed between my treated and control samples."*
2. **Clarify & propose a plan.** Contig asks targeted questions only where they materially change the result (organism/reference genome, paired vs. single-end, experimental design, replicate grouping). It then proposes a concrete, human-readable plan: which pipeline, which tools and versions, which reference, expected runtime, and expected outputs.
3. **Approve.** The user reviews and approves the plan (or edits a parameter). Nothing irreversible runs without consent.
4. **Execute on chosen compute.** Contig provisions the environment and runs the pipeline on the user's compute (local workstation, lab cluster, or their cloud) or on Contig-managed compute.
5. **Monitor & self-heal.** Contig watches the run in real time. When a step fails, it diagnoses the cause, applies a targeted fix, and retries, without dumping a stack trace on the user. Genuinely ambiguous decisions are escalated with context.
6. **Verify outputs.** Before declaring success, Contig runs QC and sanity checks appropriate to the analysis and flags anything suspicious. A result that *ran* is not the same as a result that is *correct*.
7. **Return verified result + reproducible record.** The user receives the outputs, a plain-language explanation of what happened, the QC verdict, and a re-runnable, shareable provenance record.

### 3.2 Secondary journeys

- **Reproduce / re-run.** Open a past run, re-execute it bit-for-bit (or with one parameter changed) to satisfy a reviewer or extend the analysis.
- **Hand off / share.** Send a colleague or PI a record they can inspect and re-run themselves.
- **Recover from a failed external run.** Point Contig at an analysis that died elsewhere; it diagnoses and resumes rather than restarting from scratch.

---

## 4. Differentiating Capabilities (Layer 2)

These six capabilities *are* the moat. Each is something Layer-1 tools do not do.

### 4.1 Pipeline selection & planning
Map a fuzzy natural-language goal + the actual shape of the data to a specific, defensible pipeline. Choose tools, versions, references, and parameters; surface the assumptions; produce a plan the user can approve. Prefer established, community-vetted workflows (e.g. nf-core) over ad-hoc generated scripts: proven recipes fail less.

### 4.2 Execution & environment management
Reproducibly provision the exact software environment (containers / pinned versions), stage data and references, and orchestrate execution across the user's compute or managed compute. Handle resource sizing, scheduling, and resumability. **This is the step that breaks most often in practice and is where commoditized translation tools simply stop.**

### 4.3 Failure detection & self-healing
The headline capability. Detect failures (non-zero exits, malformed intermediates, silent stalls, OOM/disk/permission errors), diagnose root cause from logs and state, apply a targeted remediation (bump memory, fix a reference mismatch, repair a malformed input, swap a tool version, adjust a parameter), and retry, looping until success or a confident escalation. The product's value is measured by how rarely a human has to intervene.

### 4.4 Output verification / QC / sanity checks
A run completing is necessary but not sufficient. Contig applies analysis-appropriate quality control and sanity checks (input QC, alignment/mapping rates, expected distributions, output schema and plausibility) and renders a verdict: *trustworthy*, *trustworthy with caveats*, or *do not trust: here's why*. This directly attacks the "ran but quietly wrong" failure mode behind the ~17% real-task accuracy on BixBench ([arxiv 2503.00096](https://arxiv.org/abs/2503.00096)).

### 4.5 Reproducibility & provenance
Every run produces a complete, re-runnable record: inputs and checksums, tool versions, container hashes, parameters, reference genome/build, environment, and the full sequence of steps (including any self-healing actions taken). The record is shareable and re-executable to reproduce the result. This is a first-class deliverable, not an afterthought.

### 4.6 Explanation / teaching
Contig explains, in plain language, what it did, why it chose this pipeline, what the QC means, and what (if anything) the user should be cautious about. For non-coders this builds trust and literacy; for coders it's a reviewable audit trail. Contig narrates decisions instead of hiding them.

---

## 5. MVP Definition: the narrowest first version

### Principle
**One pipeline, end-to-end, with self-healing on its top real-world failure modes.** Depth over breadth. A second pipeline is worthless until the first one is reliable enough that users trust the verified result without checking it themselves.

### The choice: RNA-seq differential expression vs. germline variant calling

| Dimension | RNA-seq differential expression | Germline variant calling |
|-----------|--------------------------------|--------------------------|
| Demand / frequency | Very high; extremely common request | High |
| Pipeline maturity | Highly standardized (e.g. nf-core/rnaseq + DESeq2/edgeR) | Highly standardized (e.g. GATK best practices, nf-core/sarek) |
| Verifiability of output | Strong, well-understood QC signals (read QC, mapping rate, library complexity, PCA of samples, expected DE distributions) | Verifiable but more nuanced; correctness leans toward clinical interpretation |
| Failure-mode tractability | Common, recognizable, fixable failures (wrong reference/annotation, strandedness, memory, sample-sheet errors) | More heavyweight; reference/interval and resource failures; longer runtimes |
| **Clinical / regulatory proximity** | **Low: research interpretation** | **Higher: variant calling sits adjacent to diagnostics** |

### Recommendation: **RNA-seq differential expression**

Reasons:
1. **Highest-frequency, lowest-clinical-risk** entry point. Variant calling sits uncomfortably close to the diagnostic/clinical domain: an explicit non-goal (§6) and a credibility risk for a founder without wet-lab/clinical credentials.
2. **Strong, legible verification.** RNA-seq has well-understood QC and sanity checks (mapping rates, sample PCA/clustering, library metrics), which makes capability 4.4 demonstrable on day one: the differentiator we most need to prove.
3. **Tractable, recognizable failure modes** for self-healing: wrong/mismatched reference or annotation, strandedness misconfiguration, sample-sheet errors, OOM/disk, and malformed FASTQ.

### MVP scope (must-have)

- **Input:** raw FASTQ + plain-language goal + minimal experimental design (conditions, replicates).
- **Plan:** propose a standardized RNA-seq DE workflow (built on a community-vetted base such as nf-core/rnaseq) with reference selection and a parameter summary for approval.
- **Execute:** containerized, version-pinned run on one supported compute target to start (recommend managed cloud first for control of variables, with local execution as a fast follow).
- **Self-heal:** automated detection + remediation + retry for the **top 5-8 RNA-seq failure modes** (reference/annotation mismatch, strandedness, sample-sheet errors, OOM, disk space, malformed input). Confident escalation otherwise.
- **Verify:** automated QC + sanity-check report with an explicit trust verdict.
- **Deliver:** outputs (DE results table + key plots), a plain-language explanation, and a re-runnable provenance record.

### Explicitly out of MVP
Multiple pipelines, multi-organism breadth beyond the top references, arbitrary custom workflows, BYO-cluster execution on every scheduler, team/collaboration features, and billing sophistication.

---

## 6. Scope & Non-Goals

**Contig is NOT:**
- **A no-code GUI workflow builder.** We are not Galaxy/KNIME. The interface is goal + data + a verified result, not a canvas of draggable nodes.
- **A script-generation tool.** We do not compete on Layer 1. We *consume* commodity translation as an internal input.
- **A general-purpose LLM coding assistant.** Scope is bioinformatics pipeline execution, not arbitrary code help.
- **A clinical or diagnostic product.** Contig is for research use only. No diagnostic claims, no clinical decision support, no patient-facing or regulated diagnostic interpretation. (This also shapes the MVP pipeline choice; see §5.)
- **A LIMS, a sequencer-control system, or a data-storage product.**
- **A replacement for the scientist's judgment.** Contig verifies and explains; the researcher owns the scientific conclusion.

---

## 7. Success Metrics

### North-star
**Verified-result rate without human intervention**: the share of runs that go from raw data to a passing, verified result with zero human troubleshooting. This single number captures the entire Layer-2 thesis.

### Supporting metrics

| Category | Metric |
|----------|--------|
| **Autonomy** | % of runs completing end-to-end without human intervention |
| **Self-healing efficacy** | % of detected failures auto-remediated without escalation; mean retries-to-success |
| **Time-to-result** | Wall-clock and human-hands-on time vs. the manual baseline for the same analysis |
| **Verification quality** | QC/sanity-check coverage; false-pass rate (results marked trustworthy that were not), kept near zero, the credibility-critical metric |
| **Reproducibility** | Reproducibility pass rate: % of recorded runs that re-execute to a matching result |
| **Trust & adoption** | % of results users accept without independently re-checking; repeat-use rate; non-coder activation rate |
| **Escalation quality** | % of escalations that were genuinely necessary (low rate of unnecessary interruptions, near-zero rate of *missed* problems) |

A high autonomy rate paired with a high false-pass rate is a failure, not a success; verification correctness gates everything.

---

## 8. Open Product Questions

1. **Compute model first.** Managed cloud (controls variables, faster to make reliable) vs. BYO-compute (matches the "your data, your machines" promise and data-residency needs). Which do we lead with, and how fast must the other follow?
2. **Trust threshold for autonomy.** How aggressively should Contig self-heal vs. escalate? Where is the line between "fixed it for you" and "silently changed your analysis"?
3. **Verification depth vs. overreach.** How much can we claim about correctness without crossing into scientific interpretation we're not credentialed to make (given no wet-lab/clinical background)? What does "verified" honestly mean to a skeptical reviewer?
4. **Reproducibility standard.** Bit-for-bit identical, or scientifically equivalent within tolerance? Different pipelines and users will want different bars.
5. **Pricing unit.** Per run, per result, per seat, or compute-plus-margin? Personas value different things (B/D value trust and time; A/C value throughput).
6. **Failure-mode coverage strategy.** Hand-curated remediations for known failures (reliable, narrow) vs. a more general agentic debugging loop (broad, riskier). What's the right mix, and how do we expand coverage from real run telemetry?
7. **Persona to lead with.** Non-coder (largest TAM, hardest trust bar) vs. lone computational biologist (fastest to value, evaluates us critically) vs. core facility (highest throughput, strictest auditability)?
8. **Handling the genuinely novel.** When no standard pipeline fits the goal, does Contig decline, fall back to assisted Layer-1, or attempt a custom workflow it can still verify?

---

*Sources: [arxiv.org/html/2507.20122v1](https://arxiv.org/html/2507.20122v1) (~74% of wet-lab scientists cannot program); [nature.com/articles/s41598-025-25919-z](https://www.nature.com/articles/s41598-025-25919-z) (current systems match experts only on easy tasks); [arxiv.org/abs/2503.00096](https://arxiv.org/abs/2503.00096) (BixBench ~17% accuracy on real bioinformatics tasks).*

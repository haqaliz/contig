# Contig: Technical Architecture

> **Contig** is an agentic bioinformatics analyst. A researcher hands it raw sequencing data; Contig selects and runs the right pipeline on *their* compute, debugs and self-heals failures, verifies the output, and returns a reproducible result.

---

## 0. The thesis behind this architecture

Layer 1 of the bioinformatics-agent stack (*natural language → workflow script*) is crowded and increasingly solved. LLMs already generate technically accurate Galaxy/Nextflow workflows from NL descriptions, and small models + RAG over tool docs reach expert level on the *conceptual* layer with no heavy compute [arxiv.org/html/2507.20122v1; nature.com/articles/s41598-025-25919-z].

Layer 2, actually **RUN / DEBUG / SELF-HEAL / VERIFY / REPRODUCE** end-to-end on the user's real data and compute, is not solved. Benchmarks show systems fall apart on medium/complex workflows and reach only ~17% accuracy on real analysis tasks [BixBench, arxiv 2503.00096].

**Architectural consequence, and the single idea everything below follows from:**

> The moat is the **execution + verification + reproducibility infrastructure** and the **accumulated workflow-evaluation data**, *not* the prompt and *not* the model. Build the part that gets **better as foundation models improve**, and treat the model itself as a hot-swappable component.

```
   Crowded, ~solved                        Unsolved: Contig's focus
 ┌────────────────────┐   ┌──────────────────────────────────────────────────────┐
 │  Layer 1            │   │  Layer 2                                               │
 │  NL → workflow      │ → │  RUN → OBSERVE → DIAGNOSE → REPAIR → VERIFY → REPRODUCE│
 │  (LLM + RAG)        │   │  (containerized execution + QC + provenance)          │
 └────────────────────┘   └──────────────────────────────────────────────────────┘
        replaceable                    the durable engineering asset
```

---

## 1. Architecture principles

1. **Model-agnostic; the agent is replaceable.** The reasoning model sits behind a thin `AgentProvider` interface. Swapping `claude-opus-4-8` for the next frontier model (or a cheaper local model for sub-tasks) must be a config change, never a re-architecture. No business logic lives in prompts.
2. **The execution + verification infra is the moat.** Every engineering hour goes preferentially into the parts that compound: the sandboxed runner, the failure taxonomy, the QC checks, and the provenance store. These improve with accumulated runs regardless of which model is plugged in.
3. **Reproducibility-first, not reproducibility-eventually.** A run is not "done" until it is *re-runnable by a stranger*. Every run captures pinned container digests, parameters, input checksums, tool versions, and the random seeds. If we cannot reproduce it, we did not finish it.
4. **The user's data and compute are respected.** Genomic data is sensitive and large. Contig runs *on the user's compute* (their laptop, their cloud account, their HPC) by default. Data egress is opt-in, minimized, and auditable. The control plane never needs to see the reads.
5. **Lean on the ecosystem; never reinvent pipelines.** nf-core, Galaxy, Bioconda, and Biocontainers represent thousands of expert-years of validated work. Contig *orchestrates and verifies* them; it does not write pipelines from scratch.
6. **Everything the agent does is data we keep.** Every failure, diagnosis, patch, and QC result is logged in a structured form that becomes the workflow-evaluation dataset: the second moat.

---

## 2. High-level system architecture

```
                        ┌──────────────────────────────────────────────┐
                        │                 USER (researcher)             │
                        │   web UI (chat + run dashboard) / CLI         │
                        └───────────────────────┬──────────────────────┘
                                                 │  HTTPS / WS
┌────────────────────────────────────────────────────────────────────────────────────┐
│  CONTROL PLANE  (Contig-managed, small, stateless, never touches reads)              │
│                                                                                      │
│  (1) Conversational / Planning Agent Layer                                           │
│      ├─ AgentProvider  (model-agnostic; default claude-opus-4-8, adaptive thinking)  │
│      ├─ Planner: data triage → pipeline selection → param proposal                  │
│      └─ Tool surface: search_docs, propose_pipeline, dispatch_run, inspect_logs,     │
│                        diagnose_failure, propose_patch, verify_outputs               │
│                                                                                      │
│  (2) Knowledge / RAG Layer                                                           │
│      ├─ Vector DB over: nf-core docs, Galaxy ToolShed, Bioconda/Biocontainers,      │
│      │                   tool man pages, error→fix corpus, past Contig runs          │
│      └─ Pipeline registry (curated, versioned: which pipeline for which assay)       │
│                                                                                      │
│  (5) Observability + Failure-Detection Loop                                          │
│  (6) Self-Healing / Repair Loop      (the core IP, see §5)                           │
│  (7) Verification / QC Layer                                                         │
│  (8) Provenance / Reproducibility Store  ── Postgres + object store                  │
│                                                                                      │
└───────────────┬──────────────────────────────────────────────┬─────────────────────┘
                │ signed job spec (no data)                      │ logs/metrics/QC (no reads)
                ▼                                                ▲
┌────────────────────────────────────────────────────────────────────────────────────┐
│  DATA PLANE  (the USER's compute: local / their cloud / Contig-managed sandbox)      │
│                                                                                      │
│  (4) Compute Abstraction                                                             │
│      ├─ Executor backends: Local | AWS Batch | GCP Batch | Slurm/HPC | K8s          │
│      └─ Env management: Docker / Singularity(Apptainer) / Conda                      │
│                                                                                      │
│  (3) Execution Engine                                                                │
│      └─ Workflow manager runs IN the sandbox: Nextflow (nf-core) / Snakemake / WDL  │
│         Reads, references, and intermediate files never leave this plane.            │
└────────────────────────────────────────────────────────────────────────────────────┘
```

The hard split between **control plane** (small, Contig-hosted, reasoning + bookkeeping) and **data plane** (user-owned, where bytes and compute live) is the structural expression of principle #4. Everything the agent needs to reason (logs, exit codes, QC metrics, file manifests) is small and shippable; the reads are not, and stay put.

### 2.1 Component responsibilities

| # | Component | Responsibility | Why it exists |
|---|-----------|----------------|---------------|
| 1 | **Conversational / Planning Agent** | Talk to the user; triage the data; pick a pipeline; propose parameters; drive the run loop via tools. | Turns intent into an executable, verifiable plan. Replaceable. |
| 2 | **Knowledge / RAG Layer** | Ground every decision in real tool docs, nf-core configs, and prior runs. | Keeps the model honest about tool flags, versions, assay→pipeline mapping. Compounds. |
| 3 | **Execution Engine** | Run the chosen workflow via an existing workflow manager, inside a sandbox. | We orchestrate validated pipelines; we don't author them. |
| 4 | **Compute Abstraction** | Present one interface over local / user-cloud / managed compute and over Docker/Singularity/Conda. | Lets the *same* run land on a laptop or an HPC unchanged. |
| 5 | **Observability + Failure Detection** | Stream logs/metrics; classify exit states; detect "stuck", OOM, missing-ref, etc. | The agent can only repair what it can see and name. |
| 6 | **Self-Healing / Repair Loop** | detect → diagnose → patch → re-run, bounded and logged. | The core unsolved capability; Contig's reason to exist (§5). |
| 7 | **Verification / QC Layer** | Sanity-check outputs against expected distributions and assay-specific rules. | A run that finishes is not a run that's *correct*. |
| 8 | **Provenance Store** | Persist a complete, re-runnable record of every run. | Reproducibility-first; also the audit trail and the training data. |
| 9 | **Data Store + Security** | Hold metadata, secrets, manifests; enforce the data-plane boundary. | Trust. Genomic data is sensitive even when not clinical. |

---

## 3. Recommended tech stack (for a full-stack + ML solo founder)

Choices optimize for **speed of building, breadth of ecosystem leverage, and one person's ability to operate it.**

| Concern | Choice | Why for a solo founder |
|--------|--------|------------------------|
| **Backend / orchestration** | **Python 3.12 + FastAPI** | One language across ML, agent code, and API. FastAPI is async-native (long-running runs, WS log streaming), Pydantic gives typed job specs for free. |
| **Workflow execution** | **Nextflow + nf-core** (primary); **Snakemake** (secondary); **WDL/Cromwell** (read/import only at MVP) | nf-core ships ~100 peer-reviewed, containerized, portable pipelines. This is the single biggest "buy" decision; it replaces years of pipeline authoring. Nextflow's native executors (local/AWS/GCP/Slurm/K8s) *are* the compute abstraction. |
| **Containerization** | **Docker** (cloud) + **Singularity/Apptainer** (HPC) + **Conda/Bioconda** fallback | Biocontainers + Bioconda give a pinned, reproducible binary for essentially every tool. Singularity is mandatory for HPC (no root). Nextflow already abstracts the three. |
| **LLM orchestration** | **Anthropic SDK directly**, behind a thin `AgentProvider` interface. Default `claude-opus-4-8` with `thinking: {type: "adaptive"}` and the SDK **tool runner** for the agent loop. | Avoid heavyweight framework lock-in (the agent must stay replaceable, per principle #1). A custom manual/tool-runner loop gives the fine-grained control the self-healing loop needs (gating, logging, conditional re-run). Adaptive thinking lets the model spend reasoning where diagnosis is hard without a fixed budget to tune. |
| **RAG / vector DB** | **pgvector** (start) → Qdrant (if scale demands) | pgvector means *one* datastore (Postgres) for metadata, provenance, *and* embeddings: minimal ops surface for one person. Migrate only if recall/latency forces it. |
| **Relational store** | **PostgreSQL** | Provenance, run state, registry, embeddings (pgvector), job queue (via `SELECT … FOR UPDATE SKIP LOCKED` or a light broker). One database to back up. |
| **Object store** | **S3 / GCS / DO Spaces** for *artifacts and metadata only* (QC reports, manifests, logs). Reads stay in the data plane. | Cheap, durable, presigned-URL friendly. |
| **Job/queue + workers** | **FastAPI + a worker pool** (RQ/Celery/arq, or Postgres-backed). Runs are long-lived; the worker babysits Nextflow and streams events back. | Keeps the API responsive; one worker type to reason about. |
| **Frontend** | **Vue 3 + TypeScript + Vite + Tailwind** | Founder's existing strength (per repo conventions). Two surfaces: a chat pane and a **run dashboard** (DAG view, live logs, QC verdicts, "reproduce" button). |
| **CLI** | **Typer (Python)** | Power users and HPC users live in the terminal; the CLI is the local-compute on-ramp and shares the backend's Python models. |
| **Agent runtime in the data plane** | A small **Contig runner daemon** (Python, shipped as a container or pip package) the user installs on their compute. Polls the control plane for signed job specs; executes Nextflow locally; streams logs/QC back. | This is what makes "your data, your compute" real. Outbound-only connection: no inbound ports on the user's machine. |

**Deliberate non-choices at MVP:** no Kubernetes of our own (Nextflow handles cluster submission), no microservices (a modular monolith is faster for one person), no custom workflow language (use Nextflow's), no LangChain-style framework (keeps the agent swappable).

---

## 4. The data and compute planes in detail

### 4.1 Compute abstraction (component 4)

A single `ExecutionTarget` describes *where* and *how* a run executes; the agent never special-cases the backend.

```python
class ExecutionTarget(BaseModel):
    backend: Literal["local", "aws_batch", "gcp_batch", "slurm", "k8s"]
    engine:  Literal["nextflow", "snakemake", "wdl"] = "nextflow"
    container_runtime: Literal["docker", "singularity", "conda"]
    work_dir: str            # in the data plane; reads/intermediates live here
    resource_hints: ResourceHints  # cpus, mem, time; informs auto-repair of OOM
    credentials_ref: str | None    # name of a user-held secret; never the secret itself
```

Because Nextflow already speaks all five backends and all three runtimes, the abstraction is mostly a *mapping layer* (Contig's `ExecutionTarget` → a generated `nextflow.config` profile) plus a uniform event stream, not a re-implementation. This is principle #5 applied to compute.

### 4.2 Execution engine (component 3)

- The chosen workflow (nf-core pipeline + params, or a generated Snakemake/Nextflow script) runs **inside the sandbox in the data plane**.
- Isolation: each run executes in a container with a scoped work dir, no ambient cloud credentials beyond the user's scoped role, network egress restricted by default.
- Contig captures the workflow manager's structured events (Nextflow's `trace`, `report`, `timeline`, and `-with-weblog` JSON) rather than scraping stdout; these are machine-readable and feed components 5-8 directly.

### 4.3 Three compute modes

| Mode | Where it runs | When |
|------|---------------|------|
| **Local** | Researcher's workstation, via the runner daemon | Small assays, dev, max privacy. The MVP default. |
| **User cloud** | Their AWS/GCP account (Batch), Contig submits via their scoped role | Real datasets, no data leaves their tenancy. |
| **Contig-managed** | Sandbox we provision per-run | Convenience tier; explicit opt-in; data is ephemeral and isolated. |

---

## 5. The self-healing loop (core IP)

This is the part competitors don't have and the part that improves as both the model and our failure corpus grow. It is a **bounded, observable, fully-logged** control loop wrapped around the execution engine.

```
        ┌──────────────────────────────────────────────────────────────┐
        │                        RUN LOOP                                │
        │                                                                │
        │   ┌─────────┐   exit/event   ┌──────────────┐                 │
        │   │ EXECUTE │ ─────────────▶ │  5. DETECT    │                 │
        │   │ (NF run)│                │  classify state│                │
        │   └────▲────┘                └──────┬────────┘                 │
        │        │                            │ failure                  │
        │        │ re-run patched      ┌──────▼────────┐                 │
        │        │                     │  6a. DIAGNOSE │  RAG + logs +   │
        │        │                     │   root cause  │  trace + model  │
        │        │                     └──────┬────────┘                 │
        │   ┌────┴─────┐               ┌──────▼────────┐                 │
        │   │ 6c. PATCH│◀──────────────│ 6b. PROPOSE   │  param/env/     │
        │   │  apply   │   chosen fix  │   candidate   │  retry/data fix │
        │   └──────────┘               │   fixes(ranked)│                │
        │        │                     └───────────────┘                 │
        │        ▼                                                       │
        │   ┌──────────────┐   pass    ┌──────────────┐                 │
        │   │ 7. VERIFY/QC │ ────────▶ │   SUCCESS     │ → 8. provenance │
        │   └──────┬───────┘           └──────────────┘                 │
        │          │ QC fail = a failure signal → back to DIAGNOSE       │
        │          └──────────────────────────────────────────────────┘ │
        │                                                                │
        │   Guardrails: max_attempts, cost/time budget, no-progress      │
        │   detector, human-in-the-loop gate for destructive/ambiguous   │
        │   fixes. Every transition written to provenance.               │
        └────────────────────────────────────────────────────────────────┘
```

### 5.1 Detect (component 5)

Classify the run's terminal (or stuck) state from machine-readable signals, **before** invoking the model:

- Exit code + workflow-manager error block (Nextflow names the failing process and command).
- A **failure taxonomy**, the heart of the detector. Examples:
  - `OOM` / `time_limit` (resource) → often auto-fixable by raising `resource_hints`.
  - `missing_reference` / `index_not_found` (data/config).
  - `bad_param` / `incompatible_flag` (config).
  - `container_pull_failed` / `conda_solve_failed` (environment).
  - `tool_crash` (genuine tool error: parse stderr).
  - `no_progress` (heartbeat watchdog: no new tasks for N minutes).
  - `qc_anomaly` (the run finished but output failed verification; see §6).

Pattern-matchers (regex/rules over logs) handle the common, unambiguous cases deterministically and cheaply; the model is only invoked for the residue. This keeps cost down and makes the easy 80% reproducible.

### 5.2 Diagnose (component 6, step a)

For cases the rules can't resolve, the agent assembles a **diagnosis context**: the failing process, its exact command, tail of stderr/stdout, the resolved params, the container digest, and **RAG hits** (this tool's docs, known error→fix entries, and *similar past failures from our own corpus*). The model returns a structured root-cause hypothesis, not prose.

```python
class Diagnosis(BaseModel):
    failure_class: FailureClass
    root_cause: str
    evidence: list[str]          # which log lines / docs support it
    confidence: float
```

### 5.3 Repair: propose → patch (component 6, steps b-c)

The model proposes **ranked, typed, machine-applicable** candidate fixes, never free-text "try changing the config":

```python
class Patch(BaseModel):
    kind: Literal["param", "resource", "env", "reference", "retry", "code"]
    operation: dict        # e.g. {"set": {"params.aligner": "star"}}
    rationale: str
    risk: Literal["safe", "needs_confirmation", "destructive"]
    expected_signal: str   # what we'll check to know it worked
```

Patches are applied to a **new immutable run revision** (the original is never mutated, per reproducibility-first). `risk` drives gating: `safe` patches (bump memory, switch a flag the docs endorse) auto-apply; `needs_confirmation`/`destructive` pause for the user. `expected_signal` lets DETECT confirm the fix actually changed the outcome rather than masking it.

### 5.4 Re-run and converge

Re-execute (ideally resuming from the last good checkpoint via Nextflow `-resume`, so we don't redo successful work). Loop back to DETECT. Bounded by `max_attempts`, a cost/time budget, and the no-progress detector. **Every detect/diagnose/patch/outcome tuple is persisted**: this is the workflow-evaluation dataset that is moat #2 and the eval set for swapping models.

### 5.5 Why this gets better as models improve

The *loop, taxonomy, gating, and corpus* are fixed infrastructure. A stronger model plugged into the `AgentProvider` immediately produces better diagnoses and patches **measured against our existing corpus of labeled failures**, so we can quantify the upgrade before shipping it. We benefit from frontier progress without rebuilding anything.

---

## 6. Verification / QC layer (component 7)

A run that exits 0 can still be **wrong** (truncated BAM, swapped samples, all-zero counts). Verification is what turns "it ran" into "you can trust this," and it is independent of the model.

Layered checks, cheapest first:

1. **Structural / integrity:** outputs exist, non-empty, valid format (`samtools quickcheck`, VCF header validity, index present), checksums recorded.
2. **Tool-native QC, aggregated:** run/parse **FastQC, samtools stats, Picard, MultiQC**. MultiQC's machine-readable output is ingested as metrics, not just shown to the user.
3. **Expected-distribution checks (assay-specific rules):**
   - *RNA-seq:* alignment rate within expected band, sufficient reads in genes, no extreme library-size skew, gene-detection count sane, PCA/sample-correlation outlier flags.
   - *Variant calling:* Ti/Tv ratio in the expected range, het/hom and dbSNP-overlap sanity, coverage uniformity, contamination estimate.
4. **Cross-sample consistency:** sample-swap / sex-check / relatedness flags where applicable.

Each check yields a typed `QCResult{check, status: pass|warn|fail, value, expected_range, message}`. A `fail` is fed back into the self-healing loop as a `qc_anomaly` failure signal, closing the loop between "verify" and "repair." Thresholds live in versioned, per-assay rule packs (data, not code) so they can be tuned and audited without redeploys.

---

## 7. Reproducibility & provenance (component 8)

**A run is re-runnable iff a stranger, given only its provenance record, can reproduce the result byte-for-similar.** That record is captured automatically and continuously, not reconstructed after the fact.

A `RunRecord` pins:

- **Inputs:** content hashes (e.g. SHA-256) of every input file + the sample sheet; never the files themselves leave the data plane.
- **Pipeline:** nf-core pipeline name **and exact revision/commit**, or the full generated Nextflow/Snakemake source.
- **Parameters:** the fully-resolved param set (after all auto-repairs), as JSON.
- **Environment:** every container **image digest** (not just tag) and/or the locked Conda env; the workflow-manager version; Contig's own version.
- **Compute context:** `ExecutionTarget`, resource settings, and any random **seeds**.
- **The full repair history:** the ordered detect→diagnose→patch chain that produced the final revision.
- **Verification:** all `QCResult`s and the overall verdict.
- **Outputs:** manifest + checksums of result files (stored as metadata; artifacts optionally in object store).

What makes it **shareable**: the record serializes to a portable bundle (params JSON + pinned `nextflow.config` + container digests + input checksums + a manifest). Handing that bundle (plus access to the same inputs) to another Contig instance, or a bare Nextflow install, reproduces the run. The "Reproduce" button in the UI does exactly this. Provenance is exportable toward RO-Crate / WDL-style conventions so it interoperates beyond Contig.

---

## 7.5 Operational surface (built today)

The principles above are realized as a CLI and a local dashboard over the same
engine. What is implemented now:

- **Run lifecycle and observability.** A run writes a `status.json` marker and a
  live Nextflow trace, so it is observable before the bundle exists. `contig
  status` / `contig watch` (and the dashboard live view) show task progress, the
  currently running steps, and the self-heal feed in flight. `contig cancel`
  signals the run's process group and marks it cancelled; `contig resume` re-runs
  the same id with `-resume` from the cached tasks. `contig rerun` reproduces a
  past run from its launch manifest under a fresh id.
- **Human-in-the-loop self-heal gate.** Safe patches auto-apply; a
  `needs_confirmation` or `destructive` patch pauses the run (`awaiting_approval`,
  a `pending_approval.json` sidecar) and waits for `contig approve` (or
  `--reject`) with a timeout, so a risky fix is never applied silently. Each
  decision lands in the repair history.
- **Notifications.** Run events (finished, failed, cancelled, awaiting_approval)
  append to `notifications.jsonl`; `contig run --notify <url>` posts a webhook and
  SMTP env vars enable email. The dashboard surfaces them as an activity bell.
  Best-effort: a failing notification never fails the run.
- **Output-integrity re-verification.** Output file checksums are captured at
  finalize; `contig verify <id>` re-hashes the outputs on disk against the record
  and reports drift (the strongest reproducibility claim), surfaced as a dashboard
  badge.
- **Pluggable detector and the eval flywheel.** The detector is a swappable
  interface (`rules`, `rules-strict`, and an optional provider-agnostic `llm`
  detector via Claude or OpenAI, enabled only when an env key is present).
  `contig eval-detector --detector <name>` scores any detector against the labeled
  failure corpus; `--snapshot`/`--history` persist an accuracy-over-time trend
  (moat #2), shown on the dashboard `/eval` page. This is how "gets better as
  models improve" (§5.5) is measured rather than asserted.
- **Curated assays.** RNA-seq (`nf-core/rnaseq`), single-cell RNA-seq
  (`nf-core/scrnaseq`), germline variant calling (`nf-core/sarek`), methylation
  (`nf-core/methylseq`), 16S amplicon (`nf-core/ampliseq`), and shotgun
  metagenomics (`nf-core/mag`), each with its own QC rule pack via the single
  `rule_pack_for(assay)` mapping point. Adding an assay is a registry entry plus a
  rule pack (see ADD_AN_ASSAY.md), not an engine rewrite. The goal-to-assay router
  is deterministic and replaceable (Layer 1, consumed not built).
- **Resource actuals and cost.** Each run records per-task duration, peak memory,
  and cpu from the trace (`RunRecord.resource_usage`); `contig cost` prices a run
  at configurable cpu-hour and memory-GB-hour rates (default 0 for local), shown on
  the run page. `contig estimate` gives a pre-run runtime and cost estimate, learned
  from past runs of the same pipeline with a sample-count heuristic fallback (shown
  on the launch form). This is the basis for the managed-compute usage line.
- **Interoperable provenance.** Beyond the portable bundle, `contig export
  --rocrate` emits an RO-Crate (ro-crate-metadata.json) and `contig methods` emits a
  deterministic, citation-ready methods paragraph from the bundle, so a run is
  publication and audit ready without re-entering anything by hand.
- **Compute backends.** `local` (Docker) and `aws_batch` map through one config
  generator; `contig run --backend aws_batch` refuses up front (a preflight) if the
  queue, region, S3 work dir, or credentials are missing. See the AWS Batch runbook.
- **Access control and tenancy.** The dashboard integrates Auth0 for authentication
  and role-based authorization (writer/admin gates the action routes; read views are
  open to any authenticated user), configured entirely from env so Contig stays open
  source with no tenant baked in, and a documented bypass for local use. Runs are
  owner-tagged at dispatch (an owner.json from the Auth0 user), so each user sees
  only their own runs while admins see all; a Dockerfile and deploy guide cover
  self-hosting.

---

## 8. Security, data handling, and trust

Genomic data is sensitive even when not clinical (it is identifying, familial, and often consented for a narrow purpose). Trust is a product feature.

- **Data never crosses the plane boundary by default.** Reads, references, and intermediates live in the user's `work_dir`. The control plane sees logs, exit codes, QC metrics, file *names and checksums*, never sequence content. Any export is explicit, scoped, and logged.
- **Outbound-only runner.** The data-plane daemon polls the control plane; nothing opens an inbound port on the user's machine or cloud.
- **Least-privilege compute creds.** In user-cloud mode, Contig assumes a scoped role the user grants (specific buckets, Batch queue); we never hold long-lived keys to their account.
- **Secrets management.** API keys and cloud creds are referenced by name (`credentials_ref`), held in the user's environment or a secrets manager, never persisted in the control plane or in provenance.
- **Log scrubbing.** Before any log line is shipped to the control plane (for diagnosis) it passes a redactor that strips paths/identifiers that could leak PHI-adjacent info; raw logs stay in the data plane.
- **Sandboxed execution.** Runs execute in containers with restricted egress and no ambient credentials beyond the scoped role; the agent's generated patches are typed operations, not arbitrary shell, reducing the blast radius of a bad model output.
- **Auditability.** Every agent action (diagnosis, patch, gate decision) is in the provenance record. A destructive or ambiguous patch always requires human confirmation.
- **Tenancy & retention.** Per-user isolation in Postgres/object store; configurable retention; managed-sandbox data is ephemeral by default.

---

## 9. Scalability path & build-vs-buy

**Guiding rule: buy the pipelines and the executors; build the loop and the verification.**

| Capability | Decision | Rationale |
|-----------|----------|-----------|
| Pipelines (RNA-seq, variant calling, …) | **Buy**: nf-core | Peer-reviewed, containerized, maintained. Reinventing them is the classic trap. |
| Tool binaries & environments | **Buy**: Bioconda / Biocontainers | Pinned, reproducible, comprehensive. |
| Workflow execution + multi-backend submission | **Buy**: Nextflow | Already abstracts local/cloud/HPC/K8s. |
| Aggregated QC | **Buy + wrap** FastQC/Picard/MultiQC; **build** the rule packs + verdict logic | Tools exist; the *assay-specific expectation logic* is ours. |
| Self-healing loop, failure taxonomy, gating | **Build** | This is the unsolved problem and the moat. |
| Provenance / reproducibility store | **Build** (lean on RO-Crate conventions) | Differentiator; must integrate tightly with the loop. |
| Evaluation corpus | **Build (accumulate)** | Compounds; gates model upgrades; moat #2. |

**Scaling stages:**
1. **MVP:** modular monolith (FastAPI) + Postgres(+pgvector) + a worker; local + single-cloud execution. One person can run it.
2. **Growth:** split the worker pool, move embeddings to Qdrant if recall/latency demand, add more nf-core pipelines and rule packs. Horizontal scale is just more workers; runs are independent.
3. **Scale:** because compute is the *user's*, Contig's own infra stays small; the control plane scales with *number of runs*, not size of data. This is a structurally cheap thing to scale: a key advantage of the plane split.

---

## 10. Phased build order (MVP = one pipeline, end-to-end)

Pick **one** assay to do *completely* before breadth. Recommended: **bulk RNA-seq differential expression** (`nf-core/rnaseq`): high demand, well-bounded inputs, rich and well-understood QC expectations. (Variant calling via `nf-core/sarek` is the equally valid alternative; the architecture is identical.)

| Phase | Goal | Ships |
|------|------|-------|
| **P0: Run a pipeline at all** | Execute `nf-core/rnaseq` on a fixed sample sheet, local backend, Docker, via the runner daemon. Capture Nextflow events. | Compute abstraction (local only), execution engine, event ingestion. *No agent yet.* |
| **P1: Provenance + reproduce** | Capture the full `RunRecord` and prove the "reproduce from bundle" path works. | Provenance store, container-digest pinning, the Reproduce button. |
| **P2: Verification** | Wire MultiQC/FastQC/samtools ingestion + RNA-seq rule pack → pass/warn/fail verdict. | QC layer + first rule pack. |
| **P3: Observability + detection** | Classify run outcomes against the failure taxonomy; rules handle the deterministic cases. | Detector, failure taxonomy v1, log redactor. |
| **P4: Planning agent + RAG** | NL intake → data triage → confirm `nf-core/rnaseq` + propose params, grounded in RAG over nf-core docs. Model behind `AgentProvider`. | Agent layer, RAG layer, pipeline registry. |
| **P5: Self-healing loop** | Close detect→diagnose→propose→patch→re-run, starting with `safe` auto-fixes (OOM, missing index, bad flag); gate the rest. Persist every transition. | The core IP, end-to-end, on one pipeline. |
| **P6: Second compute backend** | Add user-cloud (AWS Batch) via Nextflow profile generation; scoped-role auth. | Compute abstraction (cloud), security boundary hardening. |
| **P7: Breadth** | Add variant calling (`nf-core/sarek`) + rule pack; generalize the registry. Begin systematic harvest of the eval corpus. | Second assay; corpus pipeline; model-swap eval harness. |

**Definition of done for the MVP (end of P5):** a researcher drops RNA-seq FASTQs, Contig runs `nf-core/rnaseq` on their compute, auto-recovers from at least the common failure classes, verifies the count matrix against RNA-seq expectations, and emits a reproducible, shareable run bundle, with the whole detect/diagnose/repair chain logged.

---

## 11. Key technical risks & mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| **Self-heal masks rather than fixes** (patch makes the run pass but the result is wrong). | High | `expected_signal` on every patch; **QC verification gates success**, so a "fixed" run that produces a bad count matrix fails verification. The repair loop must satisfy §6, not just exit 0. |
| **Model fabricates flags / hallucinates fixes.** | High | RAG-ground every diagnosis in real tool docs; patches are **typed operations** validated against the pipeline schema, not free-text; `needs_confirmation` gating on anything non-trivial. |
| **Low real-task accuracy on complex workflows** (the ~17% BixBench reality). | High | Start with *one* pipeline done excellently; lean on validated nf-core workflows so the agent orchestrates rather than authors; measure relentlessly against the corpus. Don't promise general analysis at MVP. |
| **Data egress / privacy breach.** | Med (high impact) | Plane split: reads never leave the data plane; log redaction; outbound-only runner; scoped creds; audit trail. This is enforced architecturally, not by policy. |
| **Compute heterogeneity** (works on laptop, breaks on HPC: Singularity, Slurm quirks). | Med | Delegate to Nextflow's executor abstraction; pin container digests; test the runner on local + Batch + Slurm early; resource auto-repair handles cluster limits. |
| **Cost/time runaway in the repair loop.** | Med | Hard `max_attempts`, cost/time budgets, no-progress watchdog, `-resume` to avoid redoing work, cheap rule-based fixes before invoking the model. |
| **Model-provider lock-in / model deprecation.** | Med | `AgentProvider` interface + no business logic in prompts; the eval corpus lets us validate a replacement before switching. Principle #1 is the mitigation. |
| **Founder lacks wet-lab/clinical credentials.** | Med | Encode domain expertise as *data*: versioned rule packs and the curated pipeline registry, ideally reviewed by advisors; never position Contig for clinical/diagnostic use; lean on the peer-reviewed nf-core ecosystem rather than inventing methods. |
| **RAG drift** (docs change, pipeline versions move). | Low/Med | Version the knowledge base alongside pipeline revisions; re-embed on pipeline registry updates; provenance pins the exact revision used so a run is reproducible even after docs move. |

---

### Appendix: the two moats, restated

1. **Execution + verification + reproducibility infrastructure**: the loop, the taxonomy, the QC rule packs, the provenance store. Hard to build, compounds with every run, model-independent.
2. **Accumulated workflow-evaluation data**: every labeled detect→diagnose→patch→outcome. It both trains/grounds the system *and* is the harness that lets Contig adopt each new frontier model the day it ships, with measured confidence.

Both grow as foundation models improve. Neither is a prompt. That is the architecture.

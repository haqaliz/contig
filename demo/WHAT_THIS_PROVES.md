# What this demo proves

Contig's thesis is that turning English into a workflow is the commoditizing,
crowded layer (Galaxy, KNIME, general LLMs all do it), and that the unsolved,
defensible layer is everything after: running the analysis on the user's data and
compute, debugging and self-healing the failures, verifying the output, and
guaranteeing reproducibility. Frontier models reach only about 17% on real
bioinformatics analysis (BixBench, arxiv 2503.00096), which is exactly this hard
execution layer. This demo is a five minute proof that Contig owns it.

Each row maps a step you just watched to the part of the moat it demonstrates.

| Demo step | What you saw | Moat pillar it proves |
|---|---|---|
| The run hits exit 137 and recovers on its own | A first attempt fails out of memory; Contig detects the OOM, diagnoses it, applies a safe resource bump, and re-runs to a clean pass, with no human in the loop | Self-heal (the core IP): the bounded detect to diagnose to patch to re-run loop, captured as provenance in the run record's repair history |
| `contig show` prints a PASS backed by QC checks | The verdict rests on alignment-rate and assignment-rate checks per sample, not on a zero exit code | Run-and-verify: Contig ran the real analysis and then judged whether the result is biologically sound, the honest verdict that "it finished" alone cannot give |
| `contig verify` reports `ok: true` | Every recorded output still hashes to what was captured, so the result has not drifted | Reproducibility: pinned versions, checksummed inputs and outputs, an auditable trail; a result a stranger can re-run and a reviewer can trust |
| `contig verify` reports `signed: true, signature_ok: true` | The run record carries a valid Ed25519 signature; the public key ships with the bundle | Tamper-evident provenance: a journal, a collaborator, or a regulator can confirm the result was not edited after the run |
| The failure was captured for review | Every failure Contig sees is stashed as a labeled case for the evaluation corpus | The eval flywheel (moat #2): real failures compound into a labeled dataset that makes the detector better over time, the asset that grows as foundation models improve rather than being made redundant by them |

## Why this is defensible

A better base model makes Contig's orchestrator better (a sharper diagnosis, a
smarter patch), never makes it redundant: the run-and-verify harness, the
reproducibility guarantees, and the accumulated failure-evaluation data are
engineering and data assets, not a prompt. That is the deliberate bet, and it
plays to a full-stack plus ML founder's edge rather than to wet-lab or clinical
credentials.

## The honest part

The self-heal moment in this demo is driven by an injected fake executor, the
same seam Contig's own test suite uses, so the OOM to PASS recovery fires every
time on camera. Everything else is the shipping engine: the detector, the
diagnosis, the patch proposer, the QC verdict, the bundle writer, the signature,
and `contig verify`. The signing key is a throwaway generated for the demo and
discarded; the public key is committed so the bundle verifies for anyone.

## Grounding (real numbers from this repository, not marketing)

- 726 Python tests plus 75 Playwright end-to-end tests, all green.
- 6 assays wired through the same run-and-verify engine: bulk RNA-seq, germline
  variant calling, single-cell RNA-seq, methylation sequencing, amplicon
  profiling, and shotgun metagenomics.
- Two compute backends live-validated on real hardware: the local backend and
  single-node SLURM (a real nf-core/rnaseq run, 234 tasks, 0 failed). AWS Batch,
  GCP Batch, and Kubernetes map through the same layer and are code-tested.
- Two workflow engines behind one engine-agnostic record: Nextflow and Snakemake.
- A from-scratch nf-core/rnaseq run (building STAR, Salmon, and RSEM indices from
  raw FASTA and GTF) reached a verified PASS on a real x86 Linux box: 90 tasks, 0
  failed, with output integrity, resource actuals, and cost all captured.

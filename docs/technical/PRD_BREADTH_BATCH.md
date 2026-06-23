# PRD: SLURM backend, structural QC, shareable report, Snakemake, signed records

Status: approved, in build. Target branch: master (commit and push per feature as it goes green).

Five items in one pass. Two engine streams + one dashboard stream own disjoint
files; the orchestrator wires the signing CLI, integrates, and runs the live SLURM
validation after the code lands.

## Decisions (locked with the user)

1. SLURM: wire the Nextflow slurm executor + a preflight + offline tests + a runbook,
   AND a live single-node SLURM validation on root@vpn after the build (orchestrator).
2. Structural QC: a missing or empty expected output (or a corrupt one) FAILs the
   verdict; softer issues WARN.
3. Shareable report: enhance the self-contained contig show --html into a polished,
   print-to-PDF-friendly report. No new dependency, no hosting.
4. Snakemake: the engine-adapter foundation (build/run/ingest behind the Engine
   abstraction + a small example workflow), not a full curated assay yet.
5. Signed records: an Ed25519 detached signature over the bundle's content hash, key
   from CONTIG_SIGNING_KEY env or generated and stored, checked by contig verify.

## File ownership (no two streams touch the same file)

- Engine-Compute (SLURM + Snakemake): nfconfig.py, runner.py, events.py, cli.py,
  NEW snakemake adapter module(s), docs/technical/SLURM_RUNBOOK.md, + their tests.
  Does NOT touch models.py, verification/*, report.py, bundle.py, signing.py.
- Engine-Verify (structural QC + signing + report): verification/*, report.py, NEW
  signing.py, bundle.py, models.py, + their tests. Does NOT touch cli.py, runner.py,
  nfconfig.py, events.py.
- Dashboard: dashboard/** + e2e fixtures.
- Orchestrator: wire the signing CLI (contig keygen + verify signature check) in
  cli.py against signing.py, integrate, and run the live SLURM validation.

The signing CLI is the only cross-file wiring; the orchestrator does it, so neither
engine stream edits the other's files.

---

## Pinned contracts

### A. SLURM backend (Engine-Compute)

nfconfig.generate_nextflow_config emits a `slurm` executor when target.backend is
slurm, reading partition/account/time/qos from target.backend_options.
`preflight_slurm(target) -> list[str]` returns problems (partition missing, account
missing when required, sbatch/sinfo not on PATH). `contig run --backend slurm`
(with --queue used as the partition, --region unused, plus --backend-option style
knobs) runs the preflight and refuses before launching. Offline tests for the
config text and each rejection. docs/technical/SLURM_RUNBOOK.md: how to point Contig
at a real SLURM cluster (partition, account, the exact contig run command).

### B. Snakemake adapter foundation (Engine-Compute)

An Engine adapter seam: runner builds either the Nextflow or the Snakemake command
from target.engine ("nextflow" | "snakemake", both already in the Engine literal).
A snakemake module: build the `snakemake` command (a Snakefile + cores + the run
dir), run it through the same executor injection, and ingest its outcome into the
same TaskEvent/RunRecord shape (parse Snakemake's job results or a benchmark/log so
a run produces a RunRecord that verify, report, and the bundle all consume
unchanged). `contig run --engine snakemake --snakefile <path>` (no nf-core pipeline
needed). Ship a tiny example Snakefile for tests. QC may be limited for Snakemake in
this foundation pass; the point is a Snakemake run flows through capture, record,
verify, and bundle, proving engine-agnosticism.

### C. Structural and integrity QC (Engine-Verify)

NEW verification/structural.py: checks that emit QCResult entries: expected outputs
present, non-empty, expected index files present, gzip and BAM integrity, expected
output count per sample. A per-assay expected-output manifest drives which outputs
are required. Wire these into run_qc so they land in RunRecord.qc_results (so the
existing computed verdict picks them up). A missing or empty REQUIRED output, or a
corrupt file, is status "fail" (so the verdict FAILs); a soft issue (an optional
file absent) is "warn". Tests cover a present-and-valid run (pass), a missing output
(fail), and an empty/corrupt output (fail).

### D. Polished shareable HTML report (Engine-Verify)

report.render_run_report_html gains a polished, self-contained, print-to-PDF-friendly
layout: the verdict, QC (including the new structural checks), the repair chain, the
pinned provenance, and the signature status when present. Print CSS so a browser
Save-as-PDF yields a clean one-document report. Still no scripts, no network, fully
escaped. The existing contig show --html and the dashboard download button render it.

### E. Signed records (Engine-Verify provides; orchestrator wires CLI)

NEW signing.py (Ed25519 via the stdlib-friendly `cryptography` package if present,
else a clear "signing unavailable" path): generate_keypair() -> (private, public);
sign_record(record, private_key) -> a detached signature over a CANONICAL content
hash of the bundle (the same bytes contig verify can recompute); verify_signature(
record, signature, public_key) -> bool. bundle.write_bundle writes a sidecar
runs/<id>/signature.json {algo:"ed25519", public_key, signature, signed_sha256} when
a signing key is configured (CONTIG_SIGNING_KEY env, hex or base64), otherwise no
sidecar. The signature signs the canonical record content, never the signature file
itself. Orchestrator wires cli.py: `contig keygen [--out]` (print/write a keypair)
and extends `contig verify` to also check signature.json when present, adding
`signed` and `signature_ok` to its JSON.

### F. Dashboard (surface the new things)

- A Download report button on the run page (a read-only route serving contig show
  --html as a downloadable file).
- A signed/verified badge: when signature.json is present and contig verify reports
  signature_ok, show "signed, signature verified" near the output-integrity badge.
- Structural QC checks render in the existing QC panel (they are QCResult entries);
  label or group them as structural where helpful.
- Launch-form selectors: a backend selector (local, slurm with partition and account
  fields) and an engine selector (nextflow, snakemake) that thread --backend /
  --engine (and slurm knobs) into the dispatch argv (validated, --opt=value).

---

## Verification

- Engine: strict TDD (RED before GREEN). Full `uv run pytest` green (currently 597).
  No test may hit a real cluster or the network; inject fakes, env-gate optionals.
- Dashboard: tsc + lint clean; Playwright green with CONTIG_AUTH_DISABLED=1; new
  fixtures under e2e/fixtures, provisioned by the global setup, never the real runs dir.
- Live SLURM (orchestrator): install single-node SLURM (slurmctld, slurmd, munge) on
  root@vpn, run a real Nextflow job through the slurm executor, confirm a PASS, save
  proof locally, then tear SLURM and the toolchain down and restore the box.

## Style / security constraints (carried)

- No em dash, en dash, or hyphen-as-pause anywhere (code, comments, docs, commits).
- Any user value reaching the CLI is validated (charset, no leading dash) and passed
  as `--opt=value` with a `--` terminator before positionals.
- Signing keys come only from env or a generated key file, never logged or committed;
  the signature signs content, never itself; structural checks never execute outputs.

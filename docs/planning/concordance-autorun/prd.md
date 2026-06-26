# PRD: concordance-autorun (Contig runs the second caller)

Status: draft for review. Owner: aliz. Branch: `feat/concordance-autorun/aliz`.
Sources: `docs/planning/_card/issue.md`, `docs/planning/_card/understanding.md`,
follow-on to C1 (shipped v0.2.0).

## Problem Statement

C1 cross-tool concordance shipped, but it requires the user to **pre-compute and
format a second VCF** themselves (`contig verify --concordance-vcf <vcf>`). That is
real friction: producing a second independent call set is exactly the work a
researcher wants offloaded. The dig confirmed a finished germline bundle does not
carry the aligned BAM (it lives in Nextflow `work/`, not `results/`), so Contig
cannot fully auto-discover the inputs. The chosen slice: Contig **runs the second
caller for you** when you point it at the aligned BAM and the reference, removing
the hand-built-VCF step while staying honest about the one input the bundle lacks.

## Goals & Success Metrics

- `contig verify <run> --concordance-auto --bam <bam> --ref <ref>` runs a second
  variant caller (bcftools by default) on the BAM and reference, producing a second
  VCF, and compares it to the run's primary VCF via the existing
  `evaluate_concordance`. The concordance checks render exactly like the
  user-supplied-VCF path (`kind="concordance"`, at most WARN, exit code unaffected).
- The second-caller execution is behind an **injectable seam** so the whole engine
  test suite still runs with no tool execution and no network: tests inject a fake
  caller that returns a recorded VCF; bcftools is never invoked in CI.
- Honest failure: if the caller binary is missing, or the BAM/reference is missing
  or unreadable, Contig prints a clear message and emits no concordance result
  (never a false PASS, never a crash).
- Germline-only (`variant_calling`); other assays print a clear skip note.
- Zero regression to the 757 passing tests; reuses `kind="concordance"` so no
  report or dashboard change.

## User Personas & Scenarios

- **A, lone computational biologist**: has a germline run and its BAM; wants
  "corroborate this call set with a second tool" in one command instead of
  installing and scripting bcftools and reformatting a VCF.
- **C, core facility**: wants a consistent second-tool corroboration step they can
  point at the aligned BAM without bespoke glue.

## Requirements

### Must-have (this slice)
- A `VariantCaller` seam: `Callable[[bam_path, ref_path, out_dir], str]` returning
  the produced VCF path. Default `run_bcftools_caller` shells out
  (`bcftools mpileup -f <ref> <bam> | bcftools call -mv -Oz -o <out>`), mirroring the
  `Executor` injection in `runner.py`.
- `contig verify --concordance-auto --bam <bam> --ref <ref>`: resolves the run's
  primary VCF (as the existing `--concordance-vcf` path does), invokes the caller to
  produce the second VCF, calls `evaluate_concordance(primary, second, assay)`, and
  surfaces the results (text + `--json`), never changing the exit code.
- Injectable caller in the CLI path so tests pass a fake (no bcftools, no network).
- Honest edges: missing caller binary (catch the spawn error) -> clear message, no
  result; missing/unreadable BAM or ref -> clear error before invoking; non-germline
  assay -> skip note; caller produces no/empty VCF -> unverified, never PASS.
- The second VCF and the caller used are identified in the output for auditability.
- **Manual-verification gate (part of "done")**: because the suite injects a fake
  caller, it never proves the default `bcftools` command produces a comparable VCF.
  Before the PR is final, run the real `bcftools` once on a real germline BAM and
  reference and confirm a concordance result is produced. The default command is
  provisional until that passes.
- **Sample alignment note**: concordance keys on `(CHROM,POS,REF,ALT)` site keys,
  so site overlap is sample-name independent; genotype concordance compares the
  first sample's GT in each VCF, which is correct for single-sample germline (the
  slice-1 scope). Multi-sample is out of scope.

### Should-have
- Record which second caller and version were used in the result message.

### Nice-to-have (explicitly later, not now)
- In-pipeline auto-run (both callers during the germline run, no user-supplied BAM).
- Auto-discovering the BAM/reference from the run record.
- A second caller other than bcftools (DeepVariant).

## Technical Considerations

- **Reuse**: `evaluate_concordance(primary_vcf, second_vcf, assay)`
  (`verification/concordance.py`) is path-based and unchanged. The verify CLI already
  resolves the primary VCF (`_evaluate_run_concordance`).
- **Injection seam**: define `VariantCaller` and `run_bcftools_caller` in a new
  `verification/second_caller.py` (or in concordance.py). The CLI auto path takes
  `caller: VariantCaller = run_bcftools_caller`; tests inject a fake. This mirrors
  `Executor`/`default_executor` in `runner.py`, the established no-tool-in-tests
  pattern.
- **Determinism / reproducibility**: the comparison is deterministic; the caller is
  the only nondeterministic/tool-dependent step and is fully isolated behind the
  seam. The produced second VCF is written under the run dir (or a temp dir) so the
  result is auditable; record the caller identity.
- **Verification honesty**: concordance stays corroboration (at most WARN), never
  promotes UNVERIFIED to PASS; a failed/absent caller yields no PASS.
- **No raw-read egress**: the caller runs locally on the user's BAM.

## Data Model / Artifact Contracts

- No model change. Reuses `QCResult` (`kind="concordance"`). The result message
  names the second caller and the two call sets.

## Risks & Open Questions

- **bcftools command correctness**: the exact `mpileup | call` invocation and flags
  (ploidy, regions) need to be right; mitigated by keeping the default caller small
  and the seam injectable, and by not running it in tests.
- **Caller availability at runtime**: handled by catching the spawn failure and
  emitting a clear message, no PASS.
- **BAM/reference mismatch** (BAM aligned to a different reference) would produce a
  garbage second call set; out of scope to detect in slice 1, documented.
- Open: where the produced second VCF is written (a temp dir cleaned up, vs under
  the run dir for audit). Tech-plan detail.

## Out of Scope

- In-pipeline auto-run; auto-discovering BAM/reference; non-bcftools callers;
  multi-sample; FAIL-severity concordance; any clinical claim.

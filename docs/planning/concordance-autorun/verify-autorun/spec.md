# Aspect spec: verify-autorun (concordance-autorun slice 1)

Parent PRD: `../prd.md`. One buildable aspect: `contig verify --concordance-auto
--bam <bam> --ref <ref>` runs a second caller (bcftools) and compares to the run's
primary VCF, behind an injectable seam so tests never execute the tool.

## In scope
- `verification/second_caller.py`: a `VariantCaller` type, a pure
  `bcftools_command(bam, ref, out)` argv builder, and `run_bcftools_caller(bam, ref,
  out_dir) -> str` that runs it and returns the VCF path, with a clear error when
  bcftools is absent.
- `cli.py`: `--concordance-auto`, `--bam`, `--ref` on verify, and an auto helper
  that resolves the primary VCF, validates inputs, invokes the caller (injectable),
  and feeds `evaluate_concordance`; never changes the exit code.

## Out of scope
- In-pipeline auto-run; BAM/ref auto-discovery; non-bcftools callers; multi-sample;
  FAIL severity; report/dashboard changes (reuses kind="concordance").

## Acceptance criteria (testable in CI, no tool execution)
- `bcftools_command` builds the expected argv (mpileup -f ref bam | call -mv ...).
- `run_bcftools_caller` raises a clear error (not a bare FileNotFoundError) when the
  bcftools binary is absent.
- `verify --concordance-auto --bam --ref` with an INJECTED fake caller (returns a
  recorded VCF) emits the concordance checks (text + --json), at most WARN, exit
  code unchanged.
- Missing/unreadable BAM or ref -> clear skip message, no result, no crash.
- A fake caller that raises (simulating a missing binary) -> clear skip message,
  no PASS.
- Non-germline assay -> skip note.
- Full suite stays green (757); bcftools never runs in CI.

## Manual-verification gate (part of done, not CI)
- Run the real `bcftools` once on a real germline BAM + reference; confirm a
  concordance result is produced. The default command is provisional until then.

## Dependencies and sequencing
- Reuses `evaluate_concordance`. Sequence: caller module -> CLI auto path.

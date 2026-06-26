# concordance-autorun, Phase 2 understanding

Graphify-first code map. File:line against the worktree.

## Ready to reuse (good)

`evaluate_concordance(primary_vcf, second_vcf, assay)`
(`verification/concordance.py:236-249`) takes two VCF **paths** and is agnostic to
how they were produced. Only new work: produce the second VCF and pass its path.
The verify CLI already resolves the primary VCF (`cli.py:661-690`).

## Injectable-caller seam (test-only execution) is available

The engine has the pattern: `Executor = Callable[[list[str], Path], int]`
(`runner.py:69-72`), default shells out (`runner.py:88-99`), injected into
`run_pipeline(executor=...)` so tests inject a fake (`tests/test_runner.py`). The
second caller mirrors it: `VariantCaller = Callable[[primary, bam, ref], str]`,
default = real bcftools, tests inject a fake returning a recorded VCF. So the
no-tool-execution test rule is satisfiable.

## The contradiction the brief missed (CRITICAL)

A **finished** germline bundle does not carry what a second caller needs:
- The **BAM is absent** (nf-core/sarek writes it to Nextflow `work/`, not
  `results/`; the bundle and checksums cover `results/` only; the variant manifest
  is `["*.vcf.gz"]`). Users often delete `work/`.
- The **reference** is in `launch.json` (`fasta`/`genome`) but may be unlocatable
  (a bare `--genome hg38` stores only the name).

So "turnkey from a finished run" is not achievable as stated. Options:
- **A. In-pipeline:** run the second caller during the germline run (both VCFs
  together). Most reproducible; a run-time feature, not post-hoc verify.
- **B. Post-hoc with explicit inputs:** `contig verify --concordance-auto --bam
  <bam> --ref <ref>`, Contig runs bcftools for you, you point it at the BAM and
  reference. Simple, testable, unblocks the value (no hand-built second VCF).
  RECOMMENDED slice 1.
- **C. Best-effort discovery:** fragile, silent failures, maybe network. Avoid.

## Affected areas
- `cli.py` verify: add an auto path mirroring `_evaluate_run_concordance`, with an
  injectable `caller`.
- new `verification/second_caller.py`: `VariantCaller` protocol + `run_bcftools_caller`.
- Tests mirror `tests/test_concordance.py` + `tests/test_cli.py`; inject a fake
  caller so bcftools never runs. Reuses `kind="concordance"`; no UI change.

## Open questions for the interview
1. A (in-pipeline) vs B (post-hoc explicit `--bam`/`--ref`). Recommend B.
2. Second caller = bcftools call for slice 1.
3. Missing-binary at runtime -> unverified/skip with a clear message, never PASS.

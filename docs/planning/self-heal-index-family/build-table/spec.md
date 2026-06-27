# Aspect spec: build-table (extension-dispatched index build)

Parent PRD: `docs/planning/self-heal-index-family/prd.md`. This is the sole aspect of the
slice; it generalizes the `.fai`-only missing-index self-heal to `.bai`/`.tbi`/`.csi`
via a path-extension→command table.

## Problem slice & user outcome

A missing `.bai`/`.tbi`/`.csi` is detected (`missing_index`) but never recovered, because
the parse/build helpers are `.fai`-only. Outcome: those three kinds now build-and-retry
autonomously, with the same honest give-ups, on the same injected seam.

## In scope

- A general missing-index parser returning `(path, ext)` for `.fai|.bai|.tbi|.csi`.
- A table-driven build-command builder: `.fai`→`samtools faidx`, `.bai`→`samtools index`,
  `.tbi`→`tabix -p vcf`, `.csi`→`bcftools index`.
- Wiring both into `_apply_patch_and_maybe_build`, generalizing the detail strings.
- Per-kind golden corpus seeds + detector tests; full suite stays green.

## Out of scope

`.dict`; BAM-`.csi` (`samtools index -c`); STAR/BWA dir indexes; pipeline-regenerate
route; stale-index detection; risk-tier change; dashboard rendering. (See PRD Out of Scope.)

## Acceptance criteria (testable)

- AC1 — For each of `.bai`/`.tbi`/`.csi`: an injected "fail-then-succeed" run heals to a
  succeeded record with `repair_history[-1].outcome == "built_index_and_retried"`, exactly
  one build, and a real re-run (executor called twice).
- AC2 — Exact argv per kind: `.bai`→`["samtools","index","<x.bam>"]`;
  `.tbi`→`["tabix","-p","vcf","<x.vcf.gz>"]`; `.csi`→`["bcftools","index","<x.vcf.gz>"]`;
  `.fai`→`["samtools","faidx","<fasta>"]` (unchanged).
- AC3 — A non-zero build for any kind yields `outcome == "index_build_failed"` with the
  index path in `detail`, an unsucceeded record, and no further retry.
- AC4 — An evidence set with no supported token yields `outcome == "index_unresolvable"`,
  no builder call, unsucceeded record.
- AC5 — Deterministic parse: a line naming both `<x.bam>` and `<x.bam>.bai` resolves to the
  `.bai`; the existing `.fai` boundary cases still hold.
- AC6 — The four existing `.fai` end-to-end tests and the existing pure-parse tests pass
  (updated only for the renamed helpers).
- AC7 — `detector_corpus.jsonl` gains one realistic case per new kind; `uv run pytest`
  (incl. detect/corpus tests) is green.

## Dependencies & sequencing

Parser (P1) → command table (P2) → wiring (P3). Corpus/detector (P4) is independent of
P1–P3 and may run in parallel. Docs (P5) last.

## Risks specific to this aspect

- Renaming `_parse_missing_fai`/`_fai_build_command` touches existing tests
  (`test_self_heal.py:937-1033`, `:981-1000`) — update them in the same phase to avoid a
  red suite.
- `.csi`/`.tbi` both strip to `<x.vcf.gz>`; the only difference is the tool — keep that in
  the table, not in the parser.

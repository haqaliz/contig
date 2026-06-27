# self-heal-index-family (extend missing-index recovery to the rest of the single-file index family)

- **Type:** feat
- **Id/slug:** self-heal-index-family
- **Owner:** aliz
- **Branch:** feat/self-heal-index-family/aliz
- **Source:** inline brief (no GitHub issue; handed off from `contig-next`)

## Brief

Extend the just-shipped missing-index self-heal so the `IndexBuilder` seam recovers
the rest of the **single-file** index family — `.bai` (`samtools index`), `.tbi`/`.csi`
(`tabix -p vcf` / `bcftools index`), and `.dict` (`samtools dict`) — by generalizing
the missing-path parse and the path→build-command mapping that today only handles
`.fai`.

Build test-first against the existing fake-builder/executor pattern (no real
samtools/tabix or Nextflow run in CI), record `built_index_and_retried` on success and
the honest `index_unresolvable`/`index_build_failed` give-ups on failure, and seed a
golden corpus case per new kind.

Explicitly scope OUT directory-shaped STAR/BWA indexes (different multi-file shape —
leave deferred) and stale-index detection (the detector only catches fully-missing
today). Stay Layer-2, bounded by `max_attempts`, no raw-read egress.

## Provenance / why this is next (from contig-next ranking)

- Immediate follow-on slice of the `.fai`-via-`samtools faidx` slice that just shipped
  on a new injectable `IndexBuilder` seam (CHANGELOG Unreleased).
- `docs/technical/CAPABILITY_ROADMAP.md:103-109` explicitly lists "the rest of the
  missing-index family (`.bai`, `.tbi`/`.csi`, `.dict`, STAR/BWA) … on the same seam"
  as deferred next.
- The detector already keys on `.fai .bai .tbi .csi`
  (`docs/planning/self-heal-missing-index/understanding.md:22-26`), so detection is done;
  only the build-command mapping + path-parse generalization is new.
- Moves the headline reliability metric (unattended-completion rate, ROADMAP Phase 1)
  and each new kind is a golden corpus case (moat #2 compounding).

## Known caveats to settle in the dig

1. STAR/BWA indexes are directory-shaped (multi-file), not a single path parsed from
   the diagnosis — keep deferred; this slice is single-file-index only.
2. Detection covers fully-missing only ("no such file"); stale-index detection/repair
   is out of scope (`docs/planning/self-heal-missing-index/understanding.md:63-66`).

## Open questions for the interview

- Exact build-command mapping per extension (`.bai` → `samtools index <bam>`;
  `.tbi` → `tabix -p vcf <vcf.gz>`; `.csi` → `bcftools index <vcf.gz>` or
  `tabix --csi`; `.dict` → `samtools dict <ref.fasta> -o <ref.dict>`). Confirm the
  argument shapes against how the `.fai` builder is invoked today.
- Does the path-parse generalization need per-extension regexes, or does the existing
  `.fai` parse already capture an arbitrary missing path?
- One golden corpus case per kind, or a single representative? (Brief leans: per kind.)
- Surface footprint: `repair_history` + `repair_progress.jsonl` only (like the `.fai`
  slice), or also a report/verdict line? (Lean: match the `.fai` slice.)

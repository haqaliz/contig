# self-heal-dict-index (GATK sequence-dictionary self-heal)

- **Type:** feat
- **Id/slug:** self-heal-dict-index
- **Owner:** aliz
- **Branch:** feat/self-heal-dict-index/aliz
- **Source:** inline brief (no GitHub issue; handed off from `contig-next`)
- **Capability:** C2 (self-heal breadth) — next slice on the shipped single-file
  index-build seam.

## Brief (from the contig-next handoff)

Add the GATK sequence-dictionary (`.dict`) kind to the shipped single-file self-heal
index family. When a run fails with a missing-`.dict` signature (GATK/Picard "no
sequence dictionary" / "fasta.dict not found"), the engine should resolve the source
FASTA, build the dictionary (`samtools dict -o ref.dict ref.fa`, behind the existing
injectable `IndexBuilder` seam at `src/contig/self_heal.py:77`), and retry — recording
`built_index_and_retried`, and giving up honestly (`index_unresolvable` /
`index_build_failed`) on an unresolvable source or failed build, never a false pass.

Two touch points:
- **Detector change** (`src/contig/detect.py:168` recognizes `.fai`/`.bai`/`.tbi`/`.csi`
  today — add `.dict`).
- **New entry** in the `_INDEX_BUILD_COMMANDS` extension→command table
  (`src/contig/self_heal.py:77`).

Test-first with injected-builder/executor fixtures and one seeded golden corpus case
(mirror the `missing-index-tbi` case in `data/detector_corpus.jsonl`); no real
`samtools` or pipeline run in CI.

## Caveat to dig on FIRST (the key design risk)

`.dict` source-FASTA resolution differs from every shipped kind. For `.fai`/`.tbi`/
`.bai`/`.csi`, the build input is the named file with the index suffix *stripped*
(`ref.fa.fai` → `samtools faidx ref.fa`; `calls.vcf.gz.tbi` → `tabix calls.vcf.gz`).
For `.dict`, the missing file is `ref.dict` but the build input is `ref.fa` /
`ref.fasta` / `ref.fa.gz` — a **different base file** reached by *replacing* the
`.dict` extension, not stripping a suffix. Confirm whether the current derivation
assumes "strip the index suffix" and therefore needs a new resolution branch for
`.dict`, and where the FASTA candidate-extension list should live. Do not let the
slice ship a `.dict` builder that feeds it `ref.dict` as the source.

## Why this was picked (contig-next ranking)

- It is the explicitly-named next slice on a shipped seam
  (`CAPABILITY_ROADMAP.md:108-111`: "`.dict` — needs a detector change plus
  source-FASTA resolution"); not invented.
- Deepens the strongest self-heal surface — raises unattended-completion rate (the
  headline reliability metric) and seeds a golden corpus case. Serves the
  already-shipped germline assay (GATK requires a sequence dictionary).
- Unblocked, low-risk, single-file (matches the shipped `IndexBuilder` seam) vs.
  directory-shaped STAR/BWA or the murkier C2 reference-mismatch repair.

## Open questions for the interview

- **Source-FASTA resolution mechanism** (the caveat above): new `.dict`-specific
  branch vs. generalizing the existing derivation. Where does the FASTA
  candidate-extension list (`.fa`/`.fasta`/`.fa.gz`/`.fasta.gz`) live, and what if
  none of the candidates exist on disk → `index_unresolvable`?
- **Build command:** `samtools dict -o <out.dict> <ref.fa>` (matches the `samtools`
  family already used for `.fai`) vs. `gatk`/`picard CreateSequenceDictionary`.
  Prefer `samtools dict` for consistency with the shipped seam; confirm.
- **Detector signature(s):** which exact log lines classify a missing `.dict` as
  `missing_index` (GATK "A USER ERROR has occurred: ... .dict", Picard
  "CreateSequenceDictionary", "Could not read sequence dictionary")? Keep
  conservative to avoid mis-classifying a genuine *reference-mismatch* (wrong
  contigs) as a buildable missing dict.
- **Corpus seed:** one `missing-index-dict` case mirroring `missing-index-tbi`;
  reuse `FailureClass.missing_index` (no new class).
- **Output path:** does `.dict` sit beside the FASTA as `ref.dict` or `ref.fa.dict`?
  GATK/Picard convention is `ref.dict` (replace extension); the build `-o` must match
  what the pipeline looks for. Pin this against the detector's extracted path.

## Guardrails (CLAUDE.md)

- **Layer 2 only** (self-heal/execution). In scope.
- **No raw-read egress** — builds an index from a local FASTA on the user's compute.
- **No correctness over-claiming** — honest `index_unresolvable`/`index_build_failed`
  give-up; never a false `built_index_and_retried`.
- **Test-first**; injected builder/executor, no real `samtools` in CI.

## Out of scope (deferred — do not drift)

- Directory-shaped STAR/BWA indexes (break the single-file seam shape).
- BAM/CRAM form of `.csi`; stale-index detection.
- Reference/build-*mismatch* repair (wrong reference, not a missing buildable index).
- Peak-RSS-informed resource scaling.

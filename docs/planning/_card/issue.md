# reference-mismatch-detector (pre-flight reference-consistency check)

- **Type:** feat
- **Id/slug:** reference-mismatch-detector
- **Owner:** aliz
- **Branch:** feat/reference-mismatch-detector/aliz
- **Source:** inline brief (no GitHub issue; handed off from `contig-next`)

## Brief (from the contig-next handoff)

Build the **C5 reference/build mismatch detector, slice 2** — a pre-flight check
that catches a mismatched reference before a run silently produces empty output.

Scope this first slice to **reference-internal consistency**: compare the FASTA
contig naming (`>` headers) against the GTF contig naming (column 1) on
explicit-`--fasta`/`--gtf` runs, and refuse or WARN with the exact mismatch named
(e.g. "FASTA uses `chr1`, GTF uses `1`"), reusing the `ReferenceIdentity` capture
that shipped in v0.6.0. Test-first, deterministic, local-only, no network;
iGenomes (`--genome KEY`) cleanly skips since there are no local files to inspect.

**Caveat to carry into the dig:** the harder "sample data vs reference"
assembly-signature comparison is out of scope here and must stay deferred — raw
FASTQ has no contig naming and the finished bundle does not carry the aligned BAM
(it lives in Nextflow `work/`, not `results/`), so there is no reliable
sample-side signature at pre-flight. Do not let the slice drift into it.

## Why this was picked (contig-next ranking)

- It is the named next C5 slice; its dependency (the reference-identity **capture**
  slice) shipped in v0.6.0 — `ReferenceIdentity` already holds the FASTA/GTF paths
  this detector reads. (`docs/technical/CAPABILITY_ROADMAP.md:224-241`)
- Kills a notorious silent-failure class: "a run 'succeeds' against the wrong
  genome." A FASTA/GTF naming mismatch yields empty quantification that passes
  structural checks — the "make every verdict harder to fool" framing.
  (`CAPABILITY_ROADMAP.md:247-251`)
- Clean, testable, deterministic, local-only slice; seeds reference-mismatch corpus
  cases and feeds C2's deferred reference/build-mismatch repair (`missing_reference`
  is already a `FailureClass`). (`CAPABILITY_ROADMAP.md:109-111`)

## Open questions for the interview

- **Where does the check run?** A pre-flight hook before launch (preferred — catches
  it before compute is wasted), vs a verify-time check. Confirm the existing
  pre-flight surface (`reference.py`, planner/launch path) and where to attach.
- **Severity & gating:** refuse (hard error, block launch) vs WARN-and-proceed?
  Likely refuse on a clear naming-scheme mismatch, since it guarantees empty output;
  confirm.
- **What exactly is compared:** the set/style of contig names (e.g. `chr`-prefixed
  vs not), or full set membership (FASTA has `{chr1..chrM}`, GTF references `1`)?
  Define the mismatch rule precisely and conservatively (avoid false positives on
  legitimate partial references / scaffolds).
- **Parsing scope:** read only FASTA `>` headers and GTF column 1; handle gzipped
  FASTA/GTF (`.fa.gz`, `.gtf.gz`); bound the read (don't slurp whole files).
- **Reuse:** does this consume the shipped `ReferenceIdentity` (paths already
  resolved/captured), or re-resolve paths from params? Prefer reuse.
- **iGenomes skip:** `--genome KEY` → no local files → clean skip with a note.
- **Eval data:** emit a reference-mismatch case into the corpus when caught?
  Confirm the `FailureClass`/corpus shape (`missing_reference` exists; is a new
  class needed, e.g. `reference_mismatch`?).

## Guardrails (CLAUDE.md)

- **Layer 2 only** (verify/pre-flight). In scope.
- **No raw-read egress** — reads only reference files (FASTA headers, GTF col 1),
  all local.
- **No correctness over-claiming** — name the exact mismatch; never fabricate.
- **Test-first.**

## Out of scope (deferred next slices)

- Sample-data-vs-reference assembly-signature comparison (needs the aligned BAM /
  has no FASTQ signal).
- Known-sites / BED vs reference consistency.
- Annotation/GTF *version* resolution.
- The C2 reference/build-mismatch *repair* (this slice only detects).

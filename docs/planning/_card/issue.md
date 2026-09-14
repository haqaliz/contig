# Card: feat/concordance-autorun-inputs/aliz

**Source:** inline brief (no GitHub issue — `id` is a slug). Picked by
`contig-next` as the next feature; the release of the prior slice
(`sibling-peak-rescue`) is held to ship together with this one.

**Owner:** aliz · **Branch:** `feat/concordance-autorun-inputs/aliz`
(worktree `.claude/worktrees/feat-concordance-autorun-inputs`, branched from
`origin/master` @ 7a8c0e3; independent of the unmerged sibling-peak-rescue branch)

---

## Brief

Make the shipped concordance **autorun** axes turnkey by deriving their inputs
from the run record, instead of requiring the user to re-supply them. This is
the named still-deferred item of the two most recent C1 slices
(`docs/technical/CAPABILITY_ROADMAP.md:71-73` and `:129-130`):

1. **RNA-seq autorun (`contig verify --concordance-counts-auto`)**: a
   persisted-sheet `--reads` fallback (the run's own sample sheet), and an
   in-seam kallisto index build from a `--transcriptome`.
2. **Single-cell autorun (`contig verify --concordance-sc-counts-auto`)**:
   auto-derive `--reads` and `--index` from the run record (persisted sample
   sheet; in-seam STAR genome build from the run's resolved `fasta`/`gtf`,
   mirroring the shipped C2 directory-index heal). `--whitelist` and
   `--chemistry` stay user-supplied — Contig persists neither
   (`CAPABILITY_ROADMAP.md:129-130`).

Scope rules:
- The flags' explicit forms keep working unchanged; derivation only fills
  absent inputs.
- Every unrunnable path (non-matching assay, missing persisted inputs, build
  failure) stays an honest skip/refusal — never a fabricated index or a silent
  wrong-input run.
- No real kallisto/STARsolo/STAR in CI — the index-build and quantifier
  subprocesses stay behind the shipped injectable seams.

## Honest limits to carry into the writeup

- Push, not demand-pull: no design partner asked; the friction it removes is
  reasoned, not observed.
- The RNA-seq transcriptome rung has a feasibility question the dig must
  resolve: does a run bundle carry (or allow derivation of) a transcriptome
  FASTA for the kallisto index? If not, that rung stays user-supplied
  (`--transcriptome`) or is deferred — say so, don't paper over it.
- The single-cell rung needs the in-seam STAR build to be reproducible-safe
  (re-derivable on `rerun`/`resume`, scratch not baked into the manifest) per
  the C2 precedent.

## Guardrail check

Layer 2 (verification turnkey-ness for the shipped C1 axis). No Layer 1, no
wet-lab/clinical dependency, no raw-read egress, no verdict/exit-code change.
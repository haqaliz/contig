# Issue Card: stale-index self-heal

## Brief (inline, from contig-next recommendation)

Build the C2 stale-index slice: detect a supplied index whose build predates its
reference (htslib's "The index file is older than the data file" family) and rebuild
it via the shipped IndexBuilder seam, retrying the run — mirroring the missing-index
build-and-retry contract (honest `index_unresolvable`/`index_build_failed` give-ups,
bounded to one rebuild per path, golden corpus case seeded, detector guard held at
100%).

Caveats from contig-next:

- This is push, not demand-pull — organic frequency is unmeasured.
- Anchor the detector on htslib's specific phrase with a narrow AND-guard, so it
  neither over-matches nor collides with the shipped `missing_index` branch.
- Keep the wrong-reference-index flavor (index built against a different FASTA) out
  of scope — mtime-stale case first.
- Stay test-first with injected executors (no real nf-core in CI).
- Template: `docs/planning/self-heal-missing-index/` and the bgzip-reference slice's
  detector/scratch/redirect pattern.

Sources in the roadmap:

- `docs/technical/CAPABILITY_ROADMAP.md` (C2): "the still-missing single-file index
  kind (the BAM/CRAM form of `.csi`) plus **stale-index detection on the same seam**"
  — deferred, unblocked.
- The shipped `IndexBuilder` seam: `runner.py:655`, `default_index_builder`, and the
  `build_index` repair path in `self_heal.py` / `repair.py:60`.
- The `missing_index` FailureClass detector + golden corpus cases seeded per kind
  (`.fai`, `.bai`, `.tbi`, `.csi`, `.dict`), and the STAR directory-index slice.

## Decision record

- Feature slug: `stale-index-heal` (docs/planning/stale-index-heal/)
- Branch: `feat/stale-index-heal/aliz`
- Owner: aliz

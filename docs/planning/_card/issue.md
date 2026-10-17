# feat star-index-corrupt-heal, heal a corrupt/partial STAR genome index

Source: inline brief (no GitHub issue; from `/contig-next` handoff, 2026-10-17).
Owner: aliz. Type: feat. Slug: `star-index-corrupt-heal`.
Branch: `feat/star-index-corrupt-heal/aliz`.

## Brief

Add a C2 detector branch (and heal coverage) for a **corrupt/partial STAR genome
index**, the `FATAL GENOME INDEX FILE error: … is corrupt` signature that today
falls through to `tool_crash`, distinct from the shipped missing
(`genomeParameters.txt`) and version-incompatible (`Genome version`+`INCOMPATIBLE`)
STAR branches (`src/contig/detect.py:270-295`). Classify it `missing_index` at
0.85 and reuse the **unchanged** `_build_star_index` rebuild+redirect heal
(`src/contig/self_heal.py:919`): the user's index is never mutated, the retried
run points at run-scoped scratch, and every give-up is honest. Seed one golden
corpus case + one heal-guard scenario, keep the detector guard at 100%, and pin
negative controls (genuine missing/version-incompatible STAR text, plus a corrupt
line that must still classify `missing_index`), the needle must be AND-guarded so
it does not steal from the sibling branches. Caveat to carry: this is push not
demand-pull and the case is **"rarer"** (`docs/planning/self-heal-dir-index/prd.md:153`);
organic frequency is unmeasured and no real STAR runs in CI, so the real-run check
stays a manual post-merge gate.

## Source references

- C2 deferral listing the corrupt/partial STAR signature: `docs/technical/CAPABILITY_ROADMAP.md:556`.
- The slice that deferred it (N1): `docs/planning/self-heal-dir-index/prd.md:153`
  ("`FATAL GENOME INDEX FILE error ... is corrupt`, deferred this slice (rarer;
  same rebuild heal, easy follow-on)").
- The shipped STAR directory-index heal this extends: `docs/technical/CAPABILITY_ROADMAP.md:261-275`
  (STAR/BWA directory-index slice).
- Strategic grounding: `CLAUDE.md` (the moat is the run/self-heal/verify/reproduce
  layer); `docs/ROADMAP.md` Phase-1 metric (unattended-completion rate).

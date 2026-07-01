# PRD: self-heal-bwa-mem2-index (bwa-mem2 missing-index **detection**)

Status: draft for review. Owner: aliz. Branch: `feat/self-heal-bwa-mem2-index/aliz`.
Sources: `docs/planning/_card/issue.md` (contig-next brief), `understanding.md` (Phase-2
dig), shipped STAR slice `docs/planning/self-heal-dir-index/` (the precedent).
Capability: **C2 self-heal breadth** — the detector half of the next aligner-index kind,
after STAR (v0.10.0) and classic-BWA-detector-only (v0.10.0).

> **Scope was narrowed at the Phase-2 review gate.** The contig-next pick asked for
> bwa-mem2 **build + redirect**. The dig found that half **blocked — no live trigger**:
> sarek auto-builds a missing bwa-mem2 index; AWS-iGenomes ships classic BWA (not
> bwa-mem2), so the STAR iGenomes-staleness trigger doesn't transfer; and Contig's `run`
> exposes no flag to supply a broken index (`cli.py:200-225`). This PRD therefore covers
> only the **detection** half — the same honest, unblocked pattern classic BWA shipped
> with in v0.10.0. Build/redirect is deferred with the blocker named.

## Problem Statement

When a bwa-mem2 alignment fails on an unreadable index, bwa-mem2 prints
`ERROR! Unable to open the file: <ref>.bwt.2bit.64` and exits non-zero. Contig's detector
recognizes STAR and **classic** BWA index failures (`detect.py:203-244`) but **not**
bwa-mem2's distinct loader message. The exact string `ERROR! Unable to open the file:
<ref>.bwt.2bit.64` carries none of `not found`/`missing`/`no such file` (so it misses the
generic index branch, `detect.py:159-176`) and not `no such file or directory` (so it
misses the `missing_reference` branch, `detect.py:246-255`); it therefore **degrades to
`tool_crash`** today (`detect.py:257+`) — a dead-end verdict with a wrong diagnosis and no
corpus signal.

This is squarely moat #2 (`CLAUDE.md`): correct failure classification is what seeds the
accumulating detector corpus and the eval flywheel. Even with the build deferred,
classifying the failure correctly (a) gives the researcher an accurate root cause instead
of a misleading one, and (b) captures a golden corpus case that improves the detector for
everyone and is ready the day a build trigger exists.

**Evidence it's real:** the bwa-mem2 loader string is quoted from source
(`src/FMI_search.cpp`: `fprintf(stderr, "ERROR! Unable to open the file: %s\n", ...)` then
`exit(EXIT_FAILURE)`; real instances in bwa-mem2 issues #18, #141). sarek's default
aligner is bwa-mem2, so this is the loader a sarek variant-calling run would hit if it ever
staged a broken index. Named as pending on "the same seam"
(`CAPABILITY_ROADMAP.md:149-158`).

## Goals & Success Metrics

- **G1 — Classify a bwa-mem2 index failure as `missing_index`.** `diagnose_failure` on a
  log carrying `Unable to open the file: <ref>.bwt.2bit.64` returns
  `failure_class == "missing_index"`. *Metric:* a `test_detect.py` case asserts it, mirroring
  the STAR/classic-BWA detector tests (`test_detect.py:237-267`).
- **G2 — Narrow enough not to over-match.** The branch does **not** fire on (a) a
  wrong-reference / contig-mismatch line, (b) a classic-BWA `bwa_idx_load_from_disk`
  failure (that keeps its own class-`missing_index` branch, `detect.py:233-244`), or (c) a
  benign log line mentioning bwa-mem2. *Metric:* negative-control tests (mirroring the
  existing guards at `test_detect.py:211-231, 270-283`) stay green.
- **G3 — Golden corpus case, detector stays 100%.** One `missing-index-bwamem2`
  `FailureCase` line is appended to `detector_corpus.jsonl` with `expected_class ==
  "missing_index"`, and `contig eval-detector` reports 100% accuracy (no regression on the
  existing cases). *Metric:* the eval-detector assertion in the suite passes.
- **G4 — Honest give-up end-to-end (no false pass).** A bwa-mem2 index failure driven
  through `self_heal_run` with an injected builder is detected as `missing_index`, the
  parser does not resolve a build target (`.bwt.2bit.64` is not a buildable token this
  slice), so the outcome is `index_unresolvable` and the verdict is non-passing — the
  builder is never called. *Metric:* a `test_self_heal.py` case mirroring
  `test_self_heal_bwa_missing_index_gives_up_unresolvable` (`test_self_heal.py:190-216`).
- **G5 — No regression.** The full suite (**baseline: 948 passed, 1 skipped**) stays
  green; no tool executes and no network is used (injected fixtures only).

## User Personas & Scenarios

- **A, lone computational biologist** running germline/somatic variant calling
  (nf-core/sarek, bwa-mem2 default): if a bwa-mem2 index ever fails, wants an accurate
  "your bwa-mem2 index is unreadable/incompatible — rebuild it" diagnosis, not a
  misleading "missing reference" or an opaque "tool crashed."
- **C, core facility**: wants every failure class correctly labelled so the accumulating
  corpus and the eval trend stay trustworthy across the many runs they shepherd.

## Requirements

### Must-have (this slice)

- **R1 — bwa-mem2 detector branch.** A sixth narrow branch in `detect.py`, after the
  classic-BWA branch (`detect.py:244`), that returns `missing_index` when the log carries
  bwa-mem2's loader signature. Gate on the **discriminating token `bwt.2bit.64`** (the
  bwa-mem2-only sidecar named in the error) — AND-guarded with the `unable to open the
  file` phrase — so it cannot collide with the classic-`bwa_idx_load_from_disk` branch or
  swallow a wrong-reference line (which carries neither token). Case-insensitive match,
  consistent with the surrounding branches.
- **R2 — One golden corpus case.** Append a single `missing-index-bwamem2` line to
  `src/contig/data/detector_corpus.jsonl` (after line 22), shape per `FailureCase`
  (`models.py:341-349`): `source:"synthetic"`, one event `{process:"BWA_MEM2_MEM",
  status:"FAILED", exit:1}`, `log_text` the real error string
  (`ERROR! Unable to open the file: /work/idx/genome.fasta.bwt.2bit.64`),
  `expected_class:"missing_index"`.
- **R3 — Honest give-up wired through the self-heal loop.** No change to
  `_parse_missing_index` / the build seam this slice: because `.bwt.2bit.64` is not a
  buildable token, the parser returns `None` and the loop yields `index_unresolvable`
  (an honest FAIL, never a false pass) — exactly the classic-BWA behavior. A
  `test_self_heal.py` case asserts this end-to-end with an injected builder that is never
  called.
- **R4 — Reuse the `missing_index` `FailureClass`.** No new `FailureClass` member
  (`models.py:202-219` unchanged) — rebuild is the eventual heal for all these cases, and
  reuse keeps the detector/corpus contract stable, mirroring STAR and classic BWA.
- **R5 — Tests-first.** Every requirement lands as a failing test first (RED → GREEN):
  the detector positive case, the negative controls, the corpus/eval-detector assertion,
  and the self-heal give-up case. No real bwa-mem2, no network.

### Should-have

- The detector branch carries a short comment citing the bwa-mem2 loader source and the
  `bwt.2bit.64` discriminator rationale (why it's AND-guarded), matching the explanatory
  comments on the STAR/classic-BWA/`.dict` branches (`detect.py:181-232`).

### Nice-to-have (explicitly later, not now)

- A `root_cause`/message hint that names "rebuild with `bwa-mem2 index`" — copy only, no
  build. Deferred to keep the slice to detection + corpus.

## Technical Considerations

- **Chokepoint:** `src/contig/detect.py`, one new branch after `:244`; one appended line
  in `data/detector_corpus.jsonl`. No change to `self_heal.py`, `runner.py`, `repair.py`,
  `models.py`, `reference.py`, or the CLI.
- **Signature specificity:** bwa-mem2's `ERROR! Unable to open the file: %s` is *generic*
  (any unopenable file); the index-specific discriminator is the `.bwt.2bit.64` suffix in
  the path. Keying on `bwt.2bit.64` is the single safest token (it is the primary index
  file bwa-mem2 opens, `cp_file_name`, and is bwa-mem2-only). This is why the branch
  AND-guards on that token rather than on the generic phrase alone.
- **No collision with classic BWA:** classic BWA's branch keys on
  `bwa_idx_load_from_disk` + `fail to locate the index` (`detect.py:233-244`); bwa-mem2's
  keys on `bwt.2bit.64` + `unable to open the file`. Disjoint tokens → no double-classify,
  no ordering dependency.
- **No pre-emption by earlier branches:** the new branch is placed after `detect.py:244`.
  The generic index branch (`:165-169`) filters `notfound_lines`, which bwa-mem2's error
  line is not part of (no `not found`/`missing`/`no such file`), so it cannot grab the
  line first. Even in the unlikely case bwa-mem2 emitted an ancillary "not found" line,
  the generic branch's class is *also* `missing_index` — so there is no wrong-class risk,
  only a less specific `root_cause`. The corpus case's `log_text` is the isolated error
  line so the test targets the new branch directly.
- **eval-detector baseline:** G3 requires 100% on all existing cases + the new one; the
  tech-plan should record the exact current case count from `detector_corpus.jsonl` at
  implementation time (it grows per slice) rather than hard-coding a number here.
- **Reproducibility / verification impact:** none to run artifacts — detection only.
  Strengthens the eval corpus (moat #2) and keeps the honest-verdict guarantee
  (misclassification → correct classification; still an honest FAIL).
- **No raw-read egress:** reads only the run's own log text, locally.

## Risks & Open Questions

- **R-risk-1 — Generic error string over-matches.** Mitigated by requiring the
  `bwt.2bit.64` token, not the bare "unable to open the file" phrase. A non-index file
  that happens to be unopenable won't carry that token. Residual risk near-zero.
- **R-risk-2 — A future build slice must not break this branch.** When build/redirect is
  eventually wired (once a trigger path exists), `_parse_missing_index` will need a
  bwa-mem2 recognizer; this branch's token contract (`bwt.2bit.64`) is the natural key to
  reuse. Documented as a forward note, not built now.
- **Open:** none blocking — all scope decisions resolved at the review gate (detector-only,
  one corpus case).

## Out of Scope (confirmed deferred, blocker named)

- **Build + redirect of a bwa-mem2 index.** BLOCKED: no live trigger — sarek auto-builds a
  missing index; iGenomes ships classic BWA not bwa-mem2; Contig exposes no flag to supply
  a broken index. Revisit only when a trigger path exists (a deliberate user-supplied-index
  flag, or a follow-on that adds one). See `understanding.md`.
- **A second/version-incompatible corpus case.** bwa-mem2 emits no distinct
  version-incompatible string — one signature covers missing/truncated/wrong-version/
  wrong-tool, so one case suffices (confirmed at the review gate).
- **Classic-vs-mem2 aligner-mismatch heal; corrupt/partial STAR signature; BAM/CRAM
  `.csi`; peak-RSS scaling; assembly-signature reference mismatch.** Separate C2 items.
- Any clinical claim; any Layer-1 workflow authoring.

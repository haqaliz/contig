# Understanding — self-heal-bwa-mem2-index (Phase-2 deep dig)

Grounded in a full code map + domain research (two read-only agents) and the shipped
STAR slice's own Phase-0 findings. Path:line and URLs cited inline.

## What the pick asked for

Extend the C2 `IndexBuilder` self-heal seam to **build + redirect** a missing/incompatible
**bwa-mem2** aligner index on nf-core/sarek, mirroring the STAR directory-index slice
shipped in v0.10.0. The contig-next premise: "sarek defaults to bwa-mem2, so bwa-mem2 is
the live redirect target that classic BWA lacked."

## 🔴 The premise is inverted: the build+redirect half is BLOCKED (no live trigger)

The contig-next caveat flagged the right question ("does sarek auto-build a missing
index?"). The dig resolves it — and the answer kills the build+redirect scope:

1. **Sarek auto-builds a missing bwa-mem2 index.** `PREPARE_GENOME`/`BWAMEM2_INDEX` runs
   `bwa-mem2 index` from the FASTA when no index is supplied (nf-co.re/sarek usage;
   nf-co.re/modules/bwamem2_index). So on the default path the index is **never missing
   at alignment** — there is nothing to heal.
2. **STAR's live trigger does not transfer to bwa-mem2.** STAR's heal is reachable because
   **AWS-iGenomes ships a *prebuilt, often stale* STAR index**: `--genome KEY` auto-
   populates `--star_index`, and an old-version index fails under a newer STAR
   (`prd.md` problem statement; `phase0-findings.md:3-6`). **iGenomes ships classic
   `BWAIndex/` (`.amb/.ann/.bwt/.pac/.sa`), NOT a bwa-mem2 index** — so `--genome` +
   `--aligner bwa-mem2` makes sarek auto-build a fresh, compatible bwa-mem2 index. No
   stale bwa-mem2 index is ever staged.
3. **Contig exposes no flag to supply a broken bwa-mem2 index.** `cli.py:200-225` (the
   `run` command) accepts only `--genome/--fasta/--gtf` — no `--bwa`/`--bwamem2`/
   `--star-index`. The STAR redirect works by writing `params["star_index"]`, which the
   runner passes through as `--star_index` (`runner.py:190`); but the *trigger* for STAR
   comes from iGenomes, not a user flag. bwa-mem2 has neither an iGenomes trigger nor a
   user-flag trigger. The only failure mode (a user-supplied incompatible/partial/
   wrong-tool index) **cannot be reached through a Contig-launched run.**

**Conclusion:** this is the same "no *default* supported pipeline reaches a buildable
index in a failing state" blocker that deferred classic-BWA build/redirect
(`phase0-findings.md:18-24`) — and marginally stronger, since bwa-mem2 can't even be
reached via the iGenomes-staleness path STAR uses. Forcing build+redirect would wire a
redirect for a failure that no current run can produce: speculative machinery against a
guardrail (CLAUDE.md #2 — harden real run/verify surfaces, not hypotheticals).

## ✅ What IS honest and unblocked: detector + golden corpus case (mirror classic BWA)

The **detection** half is real and valuable even with no build. This is exactly the
pattern classic BWA shipped with in v0.10.0 (detector signature + one golden corpus case,
build deferred). For bwa-mem2:

- **Signature (confirmed from source):** `bwa-mem2` prints, verbatim,
  `ERROR! Unable to open the file: <ref>.bwt.2bit.64` then `exit(EXIT_FAILURE)`
  (`src/FMI_search.cpp`; issues #18, #141). There is **no distinct version-incompatible
  string** — missing, truncated, and wrong-version indexes all funnel through this one
  message.
- **Sidecar set (confirmed):** `.0123 / .amb / .ann / .bwt.2bit.64 / .pac` beside the
  FASTA; discriminating files are `.0123` and `.bwt.2bit.64` (bwa-mem2-only). NOT
  interchangeable with classic BWA (bwa-mem2 README; FMI_search.cpp).
- **Wiring:** a sixth narrow branch in `detect.py` after line 244, AND-guarded on the
  bwa-mem2-specific tokens (`bwt.2bit.64` / `unable to open the file`) so it does not
  collide with the classic-`bwa_idx_load_from_disk` branch (`detect.py:233-244`) or
  swallow a wrong-reference. One `missing-index-bwamem2` line appended to
  `detector_corpus.jsonl` after line 22 (process `BWA_MEM2_MEM`,
  `expected_class:"missing_index"`). `eval-detector` must stay 100%.
- **Give-up honesty:** because `_parse_missing_index` will (deliberately) not resolve a
  build, the outcome is `index_unresolvable` → honest FAIL — exactly like the existing
  `test_self_heal_bwa_missing_index_gives_up_unresolvable` (`test_self_heal.py:190-216`).
  This captures corpus/eval data (moat #2) without ever a false pass.

This slice is small (S), test-first, and future-proofs the build for when a trigger path
exists (a user-supplied-index flag, or a follow-on that adds one deliberately).

## Affected code (from the code map, cited)

- Build seam + parser + derivers + outcomes: `self_heal.py:60-188, 477-701` (STAR branch
  `:657-668`, `_build_star_index :477-584`, build table `:156-162`).
- IndexBuilder seam: `runner.py:86,116-126`; injected `cli.py:489-498`.
- Detector: `detect.py:159-247` (classic BWA `:233-244`); `FailureClass` `models.py:202-219`.
- Corpus: `data/detector_corpus.jsonl:20-22` (STAR/STAR-version/classic-BWA lines).
- Patch proposal: `repair.py:56-65` (diagnosis-agnostic `build_index` — no change needed).
- Tests: `test_self_heal.py:190-216` (bwa give-up), STAR block `:1761-2137`; detector
  `test_detect.py:233-283`. Fake-builder/executor pattern established — no real tool in CI.
- Registry: sarek supported (`registry.py:20-21`, assay `variant_calling`).
- Baseline suite: **948 passed, 1 skipped** (this worktree).

## Decision required (review gate before any PRD)

The full **build+redirect** pick is blocked (no live trigger). Options for the user:
1. **Detector + corpus only** (recommended) — honest, unblocked, mirrors classic BWA;
   defer build/redirect with the blocker named. Small.
2. **Abandon + re-pick** via `contig-next` for a fully-unblocked slice.
3. **Force full build+redirect** against injected fixtures despite no live trigger
   (speculative; violates the unblocked/live-target discipline).

## Guardrails (CLAUDE.md) — the detector-only slice is clean

Layer-2 (self-heal detection); no raw-read egress; no over-claiming (honest
`index_unresolvable`, never a false pass); test-first with injected fixtures.

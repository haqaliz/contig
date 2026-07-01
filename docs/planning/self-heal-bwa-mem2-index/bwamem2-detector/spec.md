# Aspect spec — bwamem2-detector

The single aspect of `self-heal-bwa-mem2-index`: classify a bwa-mem2 unreadable-index
failure as `missing_index`, seed one golden corpus case, and lock the honest
`index_unresolvable` give-up. Build/redirect is out (blocked — no live trigger; see
[PRD](../prd.md) and [understanding](../understanding.md)).

Treated as ONE aspect: the change is tiny and cohesive (one detector branch + one corpus
line + contract tests), touching only `detect.py`, `detector_corpus.jsonl`, and the test
suite. No parallelism worth splitting.

## Problem slice & user outcome

A bwa-mem2 index failure (`ERROR! Unable to open the file: <ref>.bwt.2bit.64`) is
currently mislabelled `tool_crash`. Outcome: it is correctly classified `missing_index`
(accurate root cause + a golden corpus case that feeds moat #2 / the eval flywheel), while
the run still ends in an honest FAIL (`index_unresolvable`) because building is deferred —
never a false pass.

## In scope

- A sixth narrow branch in `detect.py` (after `:244`) → `missing_index`, AND-guarded on
  the `bwt.2bit.64` token + the `unable to open the file` phrase.
- One `missing-index-bwamem2` line in `data/detector_corpus.jsonl`.
- Contract test locking the `index_unresolvable` give-up through `self_heal_run`.

## Out of scope

Build/redirect; `_parse_missing_index`/build-seam changes; a new `FailureClass`; a second
corpus case; a `root_cause` "rebuild" hint. All per the PRD.

## Acceptance criteria (the Phase-6 RED tests)

1. `diagnose_failure` on `ERROR! Unable to open the file: /work/idx/genome.fasta.bwt.2bit.64`
   → `failure_class == "missing_index"`, evidence carries the bwt.2bit.64 line.
2. A wrong-reference control and a classic-bwa line are each still classified correctly
   (bwa-mem2 branch does not swallow them; classic-bwa keeps its own branch).
3. The shipped-corpus guard (`test_shipped_seed_corpus_loads_and_detector_scores_it`,
   `test_corpus.py:146-153`) stays at `accuracy == 1.0` WITH the new case present.
4. `self_heal_run` driven with a bwa-mem2 failure + injected builder → last outcome
   `index_unresolvable`, verdict `fail`, builder never called (mirrors
   `test_self_heal.py:190-216`).

## Dependencies & sequencing

Detector branch (P1) precedes the corpus line (P2) — the corpus guard only stays green
once the branch exists. The give-up contract test (P3) depends on P1. No external deps.

## Open questions / risks

None blocking. Risk: the generic `ERROR! Unable to open the file` string is not
index-specific — mitigated by AND-guarding on `bwt.2bit.64` (bwa-mem2-only). Documented
in the PRD (R-risk-1).

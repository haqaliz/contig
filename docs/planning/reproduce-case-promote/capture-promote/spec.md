# Spec — capture-promote (aspect of reproduce-case-promote)

## Problem slice and user outcome

Capture real `contig reproduce` runs' outcomes into a pending corpus and promote
reviewed cases into a golden corpus, mirroring the shipped verification-track
machinery (`pending_verify_corpus.jsonl` + `contig verify-case-promote`). Outcome:
the C6 reproduce track gains its capture/promote channel — the corpus stops being
synthetic-only as real runs feed it — with zero impact on the signed record and the
13/14 guard baseline.

## In-scope requirements

1. **Models (additive, `models.py`):** `ReproduceCaseClaim` (claim_id, claimed,
   observed, tolerance, family, expected_status), `ReproduceCase` (case_id,
   description, source, repo, run_command, claims_sha256, claims, repair,
   exit_code, expected_exit_code, known_miss), `ReproduceCaseResult`, 
   `ReproduceCorpusReport` (total, correct, claim_match_rate, per_family,
   mismatches), `ReproduceCorpusSnapshot` (timestamp, case_count, corpus_sha,
   claim_match_rate, per_family, contig_version). All defaulted where possible;
   no existing model changes.
2. **Gate:** `should_capture_reproduce(record)` — capture iff any claim status is
   `diverged` or `unverified`, OR `repair_history` non-empty, OR `exit_code != 0`.
   A clean all-`reproduced` run files nothing.
3. **Builder:** `reproduce_case_from_record(record, *, claims=None)` —
   `case_id=f"{reproduce_id}-reproduce"`, `source=f"pending:{reproduce_id}"`,
   per-claim inputs from `ClaimResult` (claimed/observed/tolerance), family derived
   via `claim_family(claim)` from the **in-scope `Claim` objects** (the record does
   not carry locators; `claims` param supplies them; an unmatched claim_id degrades
   to `"unknown"`, never fabricated), `repair` from `repair_history[-1].outcome`,
   `exit_code` from the record.
4. **Sidecar I/O:** `append_reproduce_case`, `load_reproduce_cases` (blank/malformed
   lines skipped), `save_reproduce_cases`.
5. **Capture wiring (CLI):** in the `reproduce` command, after
   `write_reproduce_bundle(...)` succeeds, gated by `should_capture_reproduce`,
   always on (no flag), default `<runs_dir>/pending_reproduce_corpus.jsonl`;
   `claims_list` (in scope at `cli.py:1013-1017`) passed to the builder. A bundle
   write failure ⇒ no capture.
6. **Promote:** `promote_reproduce_case(case_id, pending, golden, *, expected_claims,
   expected_repair, expected_exit_code)` — missing id / duplicate id errors; source
   `pending:`→`confirmed:`; append to golden, rewrite pending minus the case;
   partial labeling legal; label-less confirm legal.
7. **Scorer:** `evaluate_reproduce_cases(cases, *, classifier=None)` — re-derives
   statuses via the shipped `classify` (injectable classifier seam); claim match
   requires `expected_status is not None` and equality; case match adds
   `expected_repair`/`expected_exit_code` when set; `claim_match_rate` over labeled
   claims only; per-family rates; mismatches informational. Unknown families never
   crash.
8. **CLI `contig reproduce-case-promote`:** positional `case_id`; `--expected-claims`
   (repeatable `id:status`, validated against `ClaimStatus` and the case's claim
   ids, exit 1 before any write); `--expected-repair` (validated against
   `RepairOutcome`); `--expected-exit` (int); `--pending`
   (default `runs/pending_reproduce_corpus.jsonl`); `--golden` (default
   `src/contig/data/reproduce_corpus.jsonl`); `--history-file` (default
   `src/contig/data/reproduce_corpus_history.jsonl`); auto-snapshot of the grown
   golden (`corpus_sha=sha256_file(golden_path)`, `cli.py:2497` precedent) appended
   to the history file. `--json` and `--history` optional should-haves.
9. **Mutation-control pin:** a stored case's re-derived status flips under a mutated
   classifier; an unlabeled claim never matches. The four shipped guards, all
   baselines, and `reproduce_scenarios.jsonl` are untouched.
10. **Docs:** CAPABILITY_ROADMAP C6/C8 deferral paragraphs updated; CHANGELOG
    [Unreleased] entry per house style.

## Out-of-scope boundaries

- No new CI guard; `reproduce-guard` and its 13/14 baseline untouched.
- No dashboard surface.
- No changes to `ReproduceRecord` / `ClaimResult` / the signed bundle (a field
  addition to `ClaimResult` would be a signature break — that is why family comes
  from the in-scope claims list, not the record).
- No capture of clean runs; no verify-time capture for blocked concordance families.
- No signing/attestation of the corpus; dedupe by `case_id` only.

## Acceptance criteria (testable)

- AC1: a record with a `diverged` claim, a record with `unverified` claims only, a
  record with a non-empty `repair_history`, and a record with `exit_code != 0` each
  capture; an all-`reproduced`/`within_tolerance` exit-0 record with no repair does
  not.
- AC2: a captured case round-trips: `append` → `load` yields identical JSON;
  malformed/blank lines are skipped without raising.
- AC3: `promote_reproduce_case` moves `pending:`→`confirmed:`, appends to golden,
  removes from pending; unknown id and duplicate id each raise; a label-less promote
  leaves `expected_status=None` everywhere.
- AC4: the CLI refuses a bad `--expected-claims` status, an unknown claim id, a bad
  `--expected-repair`, and a non-int `--expected-exit` — all exit 1 with nothing
  written.
- AC5: `evaluate_reproduce_cases` excludes unlabeled claims from
  `claim_match_rate`; a stored case flips under a mutated classifier (mutation
  pin); per-family rates report; unknown families don't crash.
- AC6: a scripted-executor CLI reproduce run with a diverged claim writes exactly
  one pending line to `<runs_dir>/pending_reproduce_corpus.jsonl` and never touches
  the record's signed bytes; a clean run writes nothing.
- AC7: `uv run pytest` green (existing suite untouched — in particular
  `tests/test_reproduce_guard_corpus.py` still pins 13/14 and no baseline file or
  scenario file changed).
- AC8: CAPABILITY_ROADMAP and CHANGELOG carry the honest-scope update.

## Dependencies and sequencing notes

- Strict dependency chain: models → corpus module → CLI wiring. Docs last.
- Reuse: `classify` (`verification/reproduce.py:797-835`), `claim_family`
  (`reproduce_guard.py:74-88`), `sha256_file`, `FamilyScore`, I/O patterns from
  `verify_corpus.py:314-345, 492-531`.
- The mutation pin and CLI capture wiring are the two genuinely new-logic test
  surfaces; everything else mirrors shipped precedent.

## Open questions or risks

- The record does not carry locators ⇒ family derivation requires the in-scope
  claims list at the capture point; the builder's `claims` param is optional so the
  pure path stays testable. Unmatched claim → `"unknown"` family (honest, never
  fabricated).
- Corpus history file is deliberately separate from `reproduce_history.jsonl`
  (guard trend is scenario-shaped; do not merge).
- Corpus starts empty; revisit trigger (20 real runs, zero cases ⇒ restate as
  taxonomy-only) recorded in the PRD, roadmap, and CHANGELOG.

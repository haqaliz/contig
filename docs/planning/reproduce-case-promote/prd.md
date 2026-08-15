# PRD: reproduce-case-promote — capture/promote channel for the reproduce track (C6)

Status: for review. Feature slug: `reproduce-case-promote`.
Branch: `feat/reproduce-case-promote/aliz`.

## Problem Statement

The C6 eval flywheel's reproduce track shipped the **guard** (`contig reproduce-guard`,
14 frozen synthetic scenarios, committed baseline 13/14) but **not the capture half**.
The guard's own docstring names the gap: *"the corpus only becomes non-tautological as
real runs feed it through the pending-capture/promote channel"* (`cli.py:3109-3111`).
CHANGELOG [Unreleased] (reproduce-eval-fold-in) states it as the pending follow-on
slice: *"capture of reproduce outcomes (pending `ReproduceCase` + promote, the
capture-promote aspect) remains the pending follow-on slice."*

Today a `contig reproduce` run writes only a bundle (`cli.py:1125`) and the
`ReproduceRecord` is a dead end — nothing feeds C6, so the "whole new,
publicly-sourced stream of failure-and-fix data" C8 promises
(`docs/technical/CAPABILITY_ROADMAP.md:2142-2144`) is not being captured. The
verification track already closed the same gap with `pending_verify_corpus.jsonl`
capture (`self_heal.py:1754-1765`) + `contig verify-case-promote`
(`cli.py:2446-2504`); the reproduce track has no analogue.

## Goals & Success Metrics

- **Goal:** real reproduce runs feed a pending corpus, humans confirm/correct per-claim
  expectations, and promoted cases land in a golden corpus — making the reproduce track
  non-tautological as field data accumulates.
- **Goal:** the shipped guard and its 13/14 baseline are untouched: `reproduce-guard`
  still defaults to the frozen `reproduce_scenarios.jsonl`; the golden corpus is
  deliberately never its default (verify precedent `verify_corpus.py:305-311`).
- **Goal:** the signed `ReproduceRecord` is never mutated; capture rides a sidecar
  (verify precedent: capture at `self_heal.py:1754-1765` writes only the pending file).
- **Success metric:** the pending file fills from real runs (countable by line count of
  `<runs_dir>/pending_reproduce_corpus.jsonl`), and promoted cases re-derive statuses
  under the shipped `classify` — proven band-sensitive by a mutation-control pin.
- **Honest scope (recorded, not softened):** the corpus starts **empty**; capture is
  **push, not demand-pull** (organic reproduce-run volume is unmeasured); there is **no
  real repo/network in CI** (scripted executor/installer seams, verify-track
  convention); the guarded 13/14 number is live only via the frozen scenarios and the
  existing anti-tautology pins — **not** via this channel.

## User Personas & Scenarios

- **A, lone computational biologist / D, biotech researcher** running `contig reproduce`
  on a paper repo: after the run, a pending case quietly records *why* the run was
  interesting (a diverged claim, an unverified claim, a healed environment, or a
  failure), ready for a one-command promote.
- **Founder / maintainer** curating the C6 corpus: `contig reproduce-case-promote
  <id> --expected-claims c1:diverged` confirms or corrects the provisional state,
  growing the golden corpus the flywheel compounds on.

## Requirements

### Must-have

1. **`ReproduceCase` model** (additive, `models.py`, `VerificationCase`
   `models.py:701-721` pattern): `case_id`, `description`, `source`
   (`synthetic | pending:<reproduce_id> | confirmed:<reproduce_id>`), `repo`,
   `run_command`, `claims_sha256`, per-claim **pre-classification inputs** — `claim_id`,
   `claimed`, `observed` (`None` when never bound), `tolerance`, `family`
   (`flat|json|table|pattern|notebook`), `expected_status: ClaimStatus | None = None` —
   plus `repair: RepairOutcome | None = None` (the recorded repair outcome, `None` when
   none), `exit_code: int`, `expected_exit_code: int | None = None`, `known_miss: bool =
   False`. Stored values are the inputs `classify` consumes
   (`verification/reproduce.py:797-835`), **never** the derived statuses — band-sensitive
   by construction (verify precedent, `verify_corpus.py:1-9`).
2. **Capture predicate** `should_capture_reproduce(record) -> bool` (new
   `src/contig/reproduce_corpus.py`, mirror `should_capture_verification`
   `verify_corpus.py:445-462`): capture when **any** claim status is `diverged` or
   `unverified`, **or** `repair_history` is non-empty (an env-resurrection was enacted or
   attempted), **or** `exit_code != 0`. "Interesting outcomes only" — a clean
   all-`reproduced` run files nothing.
3. **Builder** `reproduce_case_from_record(record)` (mirror `verification_case_from_run`
   `verify_corpus.py:465-489`): `case_id = f"{reproduce_id}-reproduce"`,
   `source = f"pending:{reproduce_id}"`, claims from `record.claim_results` (observed
   from `ClaimResult.observed`, tolerance from `ClaimResult.tolerance`, family from the
   locator-derived `claim_family`), `repair` from `repair_history[-1].outcome` when
   present, `exit_code` from the record.
4. **Sidecar I/O** `append_reproduce_case` / `load_reproduce_cases` (blank/malformed
   lines skipped, mirror `verify_corpus.py:314-345`).
5. **Capture wiring** in the `reproduce` CLI immediately after the bundle write
   (`cli.py:1125`), after the remote pins are finalized (`cli.py:1112-1123`): gated by
   the predicate, **always on, no flag** (verify precedent `self_heal.py:1754-1765`),
   default path `<runs_dir>/pending_reproduce_corpus.jsonl`. The signed record is never
   touched.
6. **Promote** `promote_reproduce_case(case_id, pending, golden, *, expected_claims,
   expected_repair, expected_exit_code)` (mirror `promote_pending_verify_case`
   `verify_corpus.py:492-531`): missing case → error; duplicate in golden → error;
   `source` `pending:`→`confirmed:`; append to golden + rewrite pending minus the case.
   **Partial labeling is allowed** — unlabeled claims stay `expected_status=None` and
   score as unlabeled (never a false match); a label-less confirm is legal (verify
   precedent `cli.py:2466-2477`).
7. **CLI `contig reproduce-case-promote`** (mirror `verify-case-promote`
   `cli.py:2446-2504`): positional `case_id`; `--expected-claims` (repeatable
   `id:status`, validated against the `ClaimStatus` literal and against the case's own
   claim ids, exit 1 before any write on a violation); `--expected-repair` (validated
   against `RepairOutcome`, `none` clears); `--expected-exit` (int); `--pending`
   (default `runs/pending_reproduce_corpus.jsonl`); `--golden` (default the shipped
   `src/contig/data/reproduce_corpus.jsonl`); `--history-file` (default
   `src/contig/data/reproduce_corpus_history.jsonl`).
8. **Scorer** `evaluate_reproduce_cases(cases)` (new; sibling of
   `reproduce_guard.evaluate_reproduce` `reproduce_guard.py:179-273`, verify analog
   `evaluate_verify` `verify_corpus.py:241-275`): re-derives each claim's status via the
   **shipped `classify`** with an injectable classifier seam (the mutation-control
   seam); claim match = `expected_status is not None and re-derived == expected`;
   per-case match additionally requires `expected_repair`/`expected_exit_code` to match
   when set; headline `claim_match_rate` over labeled claims only; `per_family` rates;
   mismatches informational. Reuses `claim_family` (`reproduce_guard.py:74-88`).
9. **Mutation-control pin** (mirror `test_verify_corpus.py:66-94` and
   `test_reproduce_guard_scorer.py:193-224`): a stored case's re-derived status flips
   under a mutated classifier (e.g. a looser tolerance), proving capture writes inputs,
   not thresholds; and promote's labels are not laundered into the match (an unlabeled
   claim never matches).
10. **Promote auto-snapshot**: after promote, evaluate the grown golden corpus and
    append a `ReproduceCorpusSnapshot` line to the corpus history file (verify precedent
    `cli.py:2490-2504` — note: **separate history file** from the guard's
    `reproduce_history.jsonl`, because the guard's trend is scenario-shaped; the corpus
    trend is case-shaped and must not corrupt the guard's append-only history).
11. **Docs**: `docs/technical/CAPABILITY_ROADMAP.md` C6/C8 deferral paragraphs updated
    (capture/promote channel closed; honest scope restated), plus a CHANGELOG [Unreleased]
    entry per house style.

### Should-have

- A `--history` flag to print the corpus eval trend, and `--json` for the eval report
  (guard-command flag family, `cli.py:3083+`).
- Golden-corpus eval snapshot command form (`contig reproduce-corpus-eval` or a
  `--eval` mode) to inspect the grown corpus without promoting — nice for curation
  review; fold into promote if it stays small.

### Nice-to-have

- Promotion by source run id with a `--from-run <id>` lookup (`load_reproduction`,
  `bundle.py:120-129`); not needed for slice 1 (promote operates on the pending JSONL
  like its siblings).

## Data Model

New additive models in `src/contig/models.py` (all defaulted where possible; no
existing model changes — `ReproduceRecord` stays byte-identical):

- `ReproduceCaseClaim`: `claim_id: str`, `claimed: float`, `observed: float | None`,
  `tolerance: float`, `family: str`, `expected_status: ClaimStatus | None = None`.
- `ReproduceCase`: `case_id`, `description`, `source`, `repo`, `run_command`,
  `claims_sha256`, `claims: list[ReproduceCaseClaim]`, `repair: RepairOutcome | None`,
  `exit_code: int`, `expected_exit_code: int | None = None`, `known_miss: bool = False`.
- `ReproduceCorpusReport` / `ReproduceCorpusSnapshot`: mirror `VerifyEvalReport` /
  `VerifySnapshot` (`models.py:743-767`) — `timestamp`, `case_count`, `corpus_sha`,
  `claim_match_rate`, `per_family`, `mismatches`, `contig_version`.

Golden corpus `src/contig/data/reproduce_corpus.jsonl` **does not ship** — created by
the first promote (verify precedent `verify_corpus.py:305-311`: golden is never the
guard's default).

## Technical Considerations

- **Integration point:** capture hangs off the `reproduce` CLI at `cli.py:1125`
  (the reproduce path has no `_finalize`; the CLI is the only persistence point —
  `run_reproduction` is pure). Remote-run pins are finalized before it
  (`cli.py:1112-1123`), so the case carries `repo` = URL for remote runs.
- **Band-sensitivity:** statuses are re-derived with the shipped `classify`
  (`verification/reproduce.py:797-835`), so a future change to classification rules
  flips stored cases — the corpus records *inputs*, never *outputs*.
- **No signature impact:** capture and promote touch only sidecar JSONL files and the
  shipped data files; the signed `ReproduceRecord` and its canonical bytes are
  untouched (no new signed fields — a deliberate break-free slice).
- **No new dependencies:** stdlib only; reuses `classify`, `claim_family`, `RepairStep`
  fields, and the `verify_corpus.py` I/O patterns.
- **Testability:** capture wiring is tested with the scripted-executor seam convention
  (`tests/test_cli_reproduce.py:49-69` pattern); scorer and promote are pure and tested
  with on-disk fixture JSONL; **no real repo, git, network, or pip in CI**.
- **Capture ordering and failure posture:** capture runs **after** `write_reproduce_bundle`
  succeeds — if the bundle write fails (e.g. disk full), no case is filed, mirroring the
  existing "validation fails ⇒ nothing written" contract of the reproduce command
  (`cli.py:987-1064`). Promote's append-golden-then-rewrite-pending is non-atomic; a
  crash between the two leaves the case in both files, and a re-run of promote then hits
  the dedupe error — identical exposure to the shipped `promote_pending_verify_case`
  (`verify_corpus.py:530-531`), accepted and mirrored, not newly introduced.
- **Effort estimate:** **M** (medium) — one aspect, ~4 plan tasks. The only genuinely
  novel logic is the scorer re-derivation + mutation pin; the rest mirrors shipped
  verify-track plumbing (`ReproduceCase` model, predicate, builder, sidecar I/O, promote,
  CLI command, snapshot).
- **Reproducibility/verification impact:** none on the verdict path; this slice only
  adds the corpus channel. The 13/14 `reproduce_baseline.json` and the frozen
  `reproduce_scenarios.jsonl` are untouched.

## Risks & Open Questions

- **Empty-corpus honesty (accepted):** the guarded number stays synthetic until real
  runs feed the channel; the roadmap/CHANGELOG must say so, per house style. **Committed
  revisit trigger (quantified):** if the **next 20 real `contig reproduce` runs** (counted
  as bundle writes under `--runs-dir`) file **zero** non-authored pending cases, the
  channel is restated as taxonomy-only in the roadmap and no further investment rides on
  it — the `qc_anomaly` "0 of 17" and catalog-coverage "next 20" precedents, counted
  without new instrumentation.
- **Partial-label semantics:** an unlabeled claim scores as unlabeled (excluded from
  `claim_match_rate`), never as a mismatch — pinned by test so a half-labeled promote
  can never inflate or deflate the rate silently.
- **Family derivation:** `claim_family` is deriveable from `ClaimResult`/locator
  fields; if a future locator family is added the case model is untouched (string
  field), but `evaluate_reproduce_cases`' `per_family` table must not assume a closed
  set (unknown families degrade honestly, never crash).
- **Snapshot file split:** the corpus history deliberately lives in a separate file
  from the guard's `reproduce_history.jsonl`; documented in the PRD so nobody merges
  them later (they hold different snapshot shapes).
- **Open:** exact `ReproduceCorpusReport` field names will be settled during
  planning against `VerifyEvalReport`; nothing here changes the signed contract.

## Out of Scope

- **No new CI guard** — no `reproduce-case-guard`; the four existing guards and all
  baselines are untouched.
- **No dashboard surface** (the verify-track corpus has none either; `dashboard/`
  currently reads only `pending_corpus.jsonl` for the detector track).
- **No verify-time capture** for the blocked concordance families
  (`concordance_genotype` / `concordance_spearman`, S1 — second set exists only at
  verify time; revisit trigger unchanged).
- **No changes to `reproduce-guard`, its scenarios, or its baseline** (13/14 stays).
- **No capture of every run** (clean all-`reproduced` runs file nothing).
- **No signing/attestation of the corpus**; no corpus dedupe beyond `case_id`.
- **No Layer 1 work; no clinical/wet-lab surface** — this is pure eval-data plumbing.

# Understanding — verify-time concordance capture

Deep dig note (2026-08-18). Verified against the worktree code at v0.54.0 (HEAD 669eac5).

## What the work is really asking

Close the last C6 R4a capture gap: `concordance_genotype` (germline) and
`concordance_spearman` (RNA-seq + single-cell) are the only verification families whose
pre-band inputs are not captured into the eval corpus, because their second call set /
count matrix exists only at `contig verify` time (user-supplied or autorun), not in the
run dir. Ship a **verify-time capture channel**: append a pending `VerificationCase`
to the shared sidecar when `contig verify --concordance-*` actually computes a
concordance check, promotable via the existing `verify-case-promote`, with round-trip /
mutation-control pins — without touching the signed record and without moving any guard
baseline.

## What the dig found (file:line)

### The scorer is DONE — this is purely a producer-side gap

- `_CONCORDANCE_FAMILY_KINDS` already enumerates all four concordance families
  including `concordance_spearman` and `concordance_genotype`
  (`src/contig/verify_corpus.py:90-95`), with the comment at :80-89 explicitly naming
  capture "still deferred" for the two verify-time families — the exact item this task
  closes.
- `_CONCORDANCE_KIND_THRESHOLDS` (`verify_corpus.py:105-110`) already re-derives
  per-kind `(warn_below, min_shared)` from current module constants: spearman
  (0.90, 10), genotype (0.90, **1** — floor 1 because genotype rate is None when no
  shared site has a known GT in both).
- `_concordance_status` (`verify_corpus.py:166-187`) scores from `{"value", "n_shared"}`
  per sample; missing keys → unverified; n_shared < floor → unverified; value <
  warn_below → warn; else pass. Concordance never FAILs (WARN-capped by contract).
- The holdout already contains 6 concordance cases (`verify_corpus_holdout.jsonl`
  lines 16-21, incl. `verify-concordance-spearman-pass/warn/unverified` and
  `verify-concordance-genotype-warn`), all matched 1.0 in the baseline
  (`verify_baseline.json` per_family).
- **verify-guard cannot move from capture alone**: it scores only the sha-pinned
  holdout (`cli.py:3113`); the pending sidecar is never a guard input
  (`verify_corpus.py:305-311`). Precedent locked in CHANGELOG v0.53.0 ("Guards unmoved,
  no baseline refreeze").

### The producers lack capture out-params

- `evaluate_concordance` (`verification/concordance.py:236-249`), `evaluate_count_concordance`
  (`count_concordance.py:341-354`), `evaluate_sc_count_concordance`
  (`sc_count_concordance.py:173-215`) return `list[QCResult]` and have **no**
  `capture_metrics` out-param.
- The precedent to mirror: `somatic_concordance.py:120-149`
  (`capture_metrics: dict[str, dict[str, float]] | None = None`, populated with raw
  `{"value": jaccard, "n_shared": float(union)}` under a descriptive pair key, **on both
  the normal and the too-few-sites paths** so a low-n case stays self-describing;
  additive and back-compat) and `annotation_concordance.py:162-187`.
- Raw stats already exist internally: `ConcordanceStats` (`concordance.py:135-148`:
  shared, rate, overlap) and `CountConcordanceStats` (`count_concordance.py:177-191`:
  shared, rho, fraction_agreeing, overlap). QCResult has **no n_shared field** — it
  lives only in the message text, so the out-param (not message parsing) is the honest
  channel.
- Single-cell reuses `results_from_counts` (`sc_count_concordance.py:215`) — the
  count-cores get the out-param once and both RNA-seq and sc inherit it
  (byte-identical RNA-seq behavior is a pinned property).

### The capture hook

- `verify()` command: `cli.py:1461-1710`. Six mutually exclusive concordance flags
  (:1592-1612); dispatch :1630-1651 produces the `concordance` local
  (`list[QCResult]`, `[]` on honest skip, `None` when no flag).
- **Natural capture point: immediately after cli.py:1651** — `record`, `runs_dir`,
  `run_id`, and the results are all in scope; covers all four terminal paths.
- Sidecar: reuse `append_verify_case` (`verify_corpus.py:340-345`, pure append, needs
  only a constructed `VerificationCase` + path) and the **shared** default path
  `<runs_dir>/pending_verify_corpus.jsonl` (the `self_heal.py:1763` precedent; already
  the `verify-case-promote --pending` default, cli.py:2510).
- **The verify path never writes the signed payload**: `load_run` is read-only
  (workspace.py:26-36), no `write_bundle` anywhere in verify, drift re-hash ignores
  unrecorded files (cli.py:1442-1443), signature covers the record not sidecars
  (bundle.py:38-39). An unrecorded sidecar is invisible to everything signed.

### Open design decisions (for the interview)

1. **Sample key** for run-level (whole-VCF / whole-matrix) results: holdout uses `"S1"`;
   somatic precedent uses the pair key `mutect2_vs_strelka2`. Scorer takes the worst
   across samples, so any stable key works; need a deterministic, self-describing
   convention (e.g. `"S1"` to match holdout shape, or the second-tool name).
2. **Capture gating**: finalize capture is gated on run verdict fail/warn
   (`should_capture_verification`, verify_corpus.py:445-462 — RunRecord-shaped, not
   reusable here). Verify-time the run verdict may be pass; the honest gate is
   "concordance actually produced results" (non-empty list), always-on no flag
   (finalize precedent: always on).
3. **case_id uniqueness**: `verification_case_from_run` uses `f"{run_id}-verify"`
   (verify_corpus.py:479) — a verify-time case for the same run must NOT collide
   (append doesn't dedupe; promote finds by case_id). Use a distinct id, e.g.
   `f"{run_id}-verify-concordance"` (one family per invocation, flags mutually
   exclusive).
4. **source convention**: keep `"pending:{run_id}"` prefix so the existing
   promote rewrite (`pending:` → `confirmed:`, verify_corpus.py:520-525) works
   unchanged.
5. **expected_verdict**: None until promote (same as finalize captures); the brief's
   "expected status" is assigned at promote time via `--expected-verdict`.
6. **Mutation-control / anti-tautology pin**: mirror the round-trip pin style
   (`tests/test_verify_capture_roundtrip.py:233-260`) — capture → promote → re-derive
   under current thresholds → statuses match; a threshold change flips a stored case.
   The existing family-key enumeration pin (:438-464) scans **runner.py only** — a
   cli.py-side writer does not trip it; decide whether to extend it deliberately.
7. **Autorun caveat**: autorun paths run real tools (bcftools/kallisto/STARsolo) — never
   in CI (manual gate); capture after the tool result exists, so capture itself is pure
   I/O and CI-testable with injected seams.

## Guardrails check

Layer 2 (eval-data capture / C6 flywheel), inside the founder's edge, stdlib-only, no
new dependencies, test-first. Capture must not move verify-guard (95.5%),
eval-guard (92.9%), heal-guard (100%), reproduce-guard (13/14); must not touch the
signed record. Honest scope: push, not demand-pull — organic `--concordance-*` usage is
unmeasured, and the corpus only becomes non-tautological as real runs get labeled.

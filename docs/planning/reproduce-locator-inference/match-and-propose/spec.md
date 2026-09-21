# Spec — match-and-propose (C8 locator-inference aspect 2 of 3)

Unit: `feat/reproduce-locator-matcher/aliz`. Parent PRD:
`docs/planning/reproduce-locator-inference/prd.md` (requirements M1-M9, S1-S4,
risks R1-R6; this spec scopes aspect 2 only). Interview decisions (2026-09-21):
R3 = float-repr precision; fixtures = inline `tmp_path` repos (sweep precedent);
S2 = pure sidecar-text builder ships in this aspect.

## Problem slice and user outcome

A user today runs `extract-claims` on a paper, gets a locator-less draft, and must
open the repo and hand-write a locator per claim before `contig reproduce` binds
anything. Aspect 1 (shipped Unreleased) enumerated every numeric value in the
repo's JSON/table artifacts as re-resolvable coordinates. This aspect matches
those candidates against the draft's claim values and **proposes** a binding site
per claim — only on unambiguous evidence — so the human's job shrinks from
"write a locator" to "review proposed locators". No CLI: the pure matcher module,
its fixture corpus, and a pure sidecar-text builder, feeding the PRD's evidence
gate before aspect 3.

## In-scope requirements (from PRD)

- **M2 — JSON locator inference.** Over `sweep_repo` candidates with
  `kind == "json"`, match a claim value against `Candidate.value`; exactly one
  match → emit `Locator(source=Candidate.source, path=Candidate.path)`.
  Never synthesize a path — reuse `Candidate.path` (already round-trip-pinned
  through the shipped `_parse_path` by the sweep's token-equality backstop).
- **M3 — Table locator inference.** Over `kind == "table"` candidates, exactly
  one match → emit a **complete** `TableLocator(source, column, row, header)`
  (fields carried 1:1 from the candidate; `delimiter` NOT set — `load_claims`
  re-derives it, and setting it is a trap). Header mode: str `column` + data-row
  int `row` (header=True); headerless: int column + all-rows int row.
- **M4 — The ambiguity rule, at site granularity.** A **site** is a distinct
  (source, coordinate) pair — `source` + JSON `path`, or `source` + table
  (column, row). Two candidates holding the same value at the same site (e.g.
  duplicated table rows) count as **one** site, not ambiguity; the same value at
  different sites ⇒ **no locator emitted**; the candidate **count** is recorded
  for the sidecar. Never an arbitrary pick.
- **M5 — Scale reconciliation, disclosed.** Attempt both `v` and `v/100`
  (raw and percent-on-repo scale). Each scale independently yields either zero
  sites, one site, or >1 sites. Exactly one scale with exactly one site → emit
  with the scale recorded; both scales with one site each (necessarily *different*
  sites, since `v == v/100` only at `v == 0`, which M9 refuses) → ambiguous →
  emit nothing; either scale with >1 sites → ambiguous → emit nothing. Never
  silently rescale. (The dead "both scales, same site" branch is deliberately
  absent — it is arithmetically unreachable.)
- **M9 — Refuse low-information values.** A claim whose value falls below an
  information threshold (small deny-list + "integer with ≤ 2 significant
  digits") is refused with the reason recorded, never bound. Conservative
  uncalibrated engineering default, named as such.
- **M7 — Never raises.** Sweep skips are disclosed non-candidates, never errors;
  malformed/absent claim inputs degrade honestly; the matcher never crashes the
  sweep or aborts other claims.
- **M6 — Round-trip invariant (module-level).** Every emitted locator, when
  assembled into a claim dict and passed through the **unchanged** `load_claims`,
  validates (no `ClaimsError`). Pinned by a universal test over the fixture
  corpus — the same guarantee the CLI round-trip (M6) will enforce in aspect 3.
- **G1 — hard gate.** Exactly 0 wrong locators on the fixture corpus (a wrong
  locator = a proposed binding whose re-resolved value differs from the claim
  value at the claimed precision, or points at a different site than the matched
  candidate).
- **G3 — ambiguity/absence reported.** Every non-bound claim records the
  candidate count and reason, via the pure sidecar builder.
- **Public API (pinned).** New module `src/contig/verification/locator_match.py`
  (sibling of `locator_inference.py`, import-only discipline). Stable surface:
  - `MatchOutcome` — frozen dataclass: `claim_id: str`, `value: float`,
    `scale: Literal["raw", "pct"] | None`, `locator: Locator | TableLocator |
    None`, `site_count: int`, `reason: str` (one of `"bound"`, `"ambiguous"`,
    `"refused_low_information"`, `"no_candidates"`).
  - `match_claims(candidates: Sequence[Candidate], claims: Sequence[Claim]) ->
    list[MatchOutcome]` — one outcome per claim, claims order preserved, pure
    and never-raises; an empty `claims` yields `[]` (no per-claim outcome
    exists, so there is no `"no_claims"` reason). Site grouping, exactly-one,
    and M9 refusal all live here.
  - `match_site_count(...)`-level helpers may be private; nothing else is
    exported. The evidence-gate tooling and aspect 3 consume only these three
    names plus `sidecar_text` (below).
- **S2 — Pure sidecar-text builder.** A deterministic
  `sidecar_text(outcomes: Sequence[MatchOutcome], claims: Sequence[Claim]) -> str`
  pure function renders per-claim provenance: matched artifact + coordinate,
  scale (`raw` / `÷100`), and for a miss the candidate count + reason. Must
  include the PRD R6 disclosure per emitted locator: the exact repo-relative
  path whose rewriting the locator depends on (stated as a fact, not a
  guarantee). CLI consumes this text in aspect 3.
- **G4 — Verdict contract.** An inferred locator must produce exactly the verdict
  a hand-written identical locator would: pins re-run the emitted locators
  through `classify` (and the `reproduce_guard` `claim_family` dispatch) on
  fresh fixtures.

## Out-of-scope boundaries

- **No CLI** (`contig infer-locators` is aspect 3, gated on the evidence gate).
  No `--dry-run`, no `--force`, no `--out` handling (S1/S4 → aspect 3).
- **No `models.py`, verdict, bundle, signing, or exit-code change.** No edit to
  `reproduce.py` or `claim_extraction.py` (import-only discipline, sweep
  precedent). No new dependency (stdlib only).
- **`pattern` and notebook inference** — blocked (synthesized regex vs
  `resolve_match`'s exactly-one rule, `prd.md:173-179`).
- **Figure/plot claims** — hard-blocked (no plot-hash, stdlib-only).
- **The evidence gate itself** — it runs AFTER this aspect, on one real
  published repo, and is recorded; it is not part of the module's test suite.
- **No network, no repo fetching, no raw-read egress.**

## Acceptance criteria (testable, per requirement)

1. A fixture repo with a claim's value in exactly one JSON leaf → one `Locator`
   emitted; re-resolving it through `resolve_pointer` yields the value.
2. The same value in two JSON leaves (or one JSON + one table cell) → no locator;
   count = 2 recorded.
3. A claim value that only matches at `v/100` scale → locator emitted, scale
   `÷100` recorded; a value matching both scales at different sites → no locator.
4. A low-information claim (`0`, `1`, `0.5`, `0.05`, `100`, integer with ≤ 2
   significant digits) → refused with reason, never bound — except where the
   fixture deliberately exercises the deny-list boundary.
5. A table candidate match → complete `TableLocator` (`from`+`column`+`row`+
   `header`), header-mode str column with data-row index; headerless int/int.
6. Round-trip: every emitted claim dict passes the unchanged `load_claims`.
7. Never-raises: unreadable dir, oversized artifact, malformed JSON, garbage
   claims file — each yields honest skip/refusal, no exception.
8. Sidecar text: per-claim line names artifact + coordinate + scale + count +
   reason, and the R6 path disclosure on every emitted locator.
9. G4: emitted locators classify identically to hand-written identical ones
   under `classify` on fresh fixtures and under `reproduce_guard`'s
   `claim_family`.
10. Full suite green, no signature break, no new dependency (`uv run` check);
    baseline guards unmoved (eval/heal/verify/reproduce-guard).

## Dependencies and sequencing

- Consumes: `locator_inference.sweep_repo`/`Candidate`/`SweepSkip` (shipped
  Unreleased in this worktree's history); `reproduce.py` `Locator`/
  `TableLocator`/`Claim`/`load_claims`/`classify`/`resolve_pointer`/
  `resolve_cell` (import-only); draft shape from `claim_extraction.py`/CLI.
- Sequencing: this aspect → evidence gate (manual, recorded) → aspect 3 CLI.
  The evidence gate's question: how many claims bind, how many ambiguous, how
  many refused, and is any bind wrong (report any R6 fresh-path mismatch).

## Open questions / risks (carried from the PRD)

- **R1 residual**: a repo where only a *coincidental* equal value exists yields a
  confident wrong bind; M9 + the sidecar's "proposed, pending human review"
  framing (rendered by this aspect's builder) are the mitigations. G1 is
  self-graded and stated as such.
- **R3 settlement**: float-repr precision (interview decision). A candidate
  matches when it equals the claim value rounded to the claim's own printed
  precision (repr-derived). Compare via exact equality after rounding; tie-break
  rules pinned by tests (e.g. `0.1+0.2`-style reprs, `0.91` vs `0.9134`).
- **R6**: stale-coordinate/fresh-path mismatch — accepted, disclosed in sidecar,
  to be observed at the evidence gate.
- **Candidate.value int/float nuance**: JSON int leaves are stored as `int`;
  comparisons must not be fooled (e.g. `7 == 7.0`), and scale/rounding math must
  be float-safe.
# PRD: reproduce-paper-claims (paper-claim extraction for `contig reproduce`)

Status: draft for review. Owner: aliz. Branch: `feat/reproduce-paper-claims/aliz`.
Sources: `docs/planning/_card/issue.md` (contig-next handoff, 2026-07-24),
`docs/planning/_card/understanding.md` (Phase-2 dig), `docs/technical/CAPABILITY_ROADMAP.md`
C8. Capability: **C8, next slice** — the paper-parsing step named as deferred in every C8
slice deferral list (`CAPABILITY_ROADMAP.md:1073`; `CHANGELOG.md:420,523,595,686`).

## Problem Statement

`contig reproduce <repo> --run "<cmd>" --claims <file>` (slices 1–7, v0.40.0 → v0.48.0)
issues a per-claim verdict — `REPRODUCED` / `WITHIN-TOLERANCE` / `DIVERGED` / `UNVERIFIED` —
over a **claims file the user hand-authors** by reading the paper and transcribing every
stated number into JSON. That hand-authoring is the last manual step between "a published
paper" and "a checkable reproduction," and it is exactly what keeps `contig reproduce`
a maintainer demo rather than a turnkey tool. The reproduce PRD's own review gate named
externally-credible reproduce the point of C8; **claim extraction is what makes it turnkey.**

**Who has the problem.** Persona A (lone computational biologist reproducing a paper before
building on it) and Persona D (biotech researcher checking a published result). Both currently
transcribe numbers by hand — slow, error-prone, and a barrier to even trying.

**Evidence it's real.** The C8 problem statement is built on the reproducibility crisis (of
27,271 biomedical-paper notebooks only ~3.2% reproduced — Samuel & Mietchen 2024, cited in
`docs/planning/reproduce-notebook-locator/`). The whole reproduce spine exists; only the
claims-input step is manual.

## Goals & Success Metrics

1. **Turnkey first step.** `contig extract-claims <paper.txt|md> --out <draft.json>` turns a
   paper's text into a **draft** claims file the user reviews and completes, instead of a
   blank file they fill from scratch.
2. **Never emit an invalid draft.** The emitted claims JSON **always** loads through the
   unchanged `load_claims` — enforced by round-tripping it in the command itself and pinned by
   a test. *Measure:* 100% of emitted drafts parse; a draft that would not load is a bug that
   fails the build.
3. **Honest recall on the target shapes.** The deterministic core extracts named-metric +
   number claims from labeled fixture text. *Measure:* on a committed labeled fixture corpus,
   report precision/recall as counts (not a marketing number) — the bar is "finds the obvious
   claims, emits no malformed entry," not "perfect extraction."
4. **Zero blast radius on the verdict path.** No change to `run_reproduction`, `classify`,
   `ClaimResult`, `ReproduceRecord`, the bundle, signing, or any exit code. *Measure:* the
   entire existing reproduce test suite is untouched and green.
5. **The extractor gets better as models improve** (`CLAUDE.md` #3): an optional, env-gated
   LLM assist adds recall without ever being required, and without touching CI.

## User Personas & Scenarios

- **A — lone computational biologist.** Has a paper's repo cloned and its text saved as
  markdown. Runs `contig extract-claims paper.md --out claims.draft.json`, opens the
  `.review.md` sidecar, prunes the candidates, adds a `from`/`path` or `pattern` locator to
  each real claim, then runs `contig reproduce`. Saves the transcription toil, keeps full
  editorial control.
- **D — biotech researcher.** Wants a defensible check that a published result regenerates.
  The draft + sidecar give a reviewable, provenance-carrying starting point.

## Requirements

### Must-have (v1)

- **M1 — Deterministic extractor core** (`src/contig/verification/claim_extraction.py`, pure,
  stdlib-only, **never raises**). `extract_claims(text: str) -> list[ExtractedClaim]`:
  - Targets **named-metric + number** shapes only: a curated metric vocabulary (AUC, accuracy,
    precision, recall, F1, sensitivity, specificity, correlation/r, R², MSE/RMSE/MAE, fold
    change / log2 fold change, …) joined to a number by a connective (`of`, `was`, `=`, `:`,
    `reached`, `achieved`, `is`). Value parsed via `float()`; non-finite skipped.
  - **Percentages:** the raw number is the `value` (e.g. `87` from "87%"); the `%` unit is
    recorded on the `ExtractedClaim` for the sidecar and **not** auto-divided by 100 — the
    repo's output could be `87` or `0.87`, so the human resolves it, we never guess.
  - **Inequalities skipped** (`p < 0.001`, `≥`, `≤`): an inequality is not a single reproducible
    point value.
  - **id generation:** a deterministic, human-editable slug from the metric word, uniquified
    within the file (`auc`, `auc_2`, …). No randomness (must be reproducible / journal-safe).
  - **Dedup:** identical (metric, value, near-context) collapses to one candidate.
  - Malformed / empty input → empty list, honest (never raises).
- **M2 — Optional LLM assist** (`extract_with_llm`, behind a single injectable seam), following
  the `detect.py` `llm`-detector precedent exactly:
  - **Env-gated** through the *same* mechanism (`CONTIG_LLM_PROVIDER` + provider→key map,
    reusing `detect._selected_provider()` as the single source of truth). Unconfigured → the
    LLM contributes nothing and the deterministic core stands alone.
  - **One network/SDK touch point** — a `_llm_complete`-shaped seam local to the extractor that
    tests monkeypatch; the provider SDK is imported lazily inside it and **never** in CI.
  - **Defensive parse:** the reply is parsed into candidate claims; any parse/provider/network
    error is swallowed (mirroring `_diagnosis_from_reply`) so the LLM path never crashes the
    command — a failed LLM call degrades to core-only output.
  - **Merge:** LLM candidates are merged and deduped with core candidates; each claim's origin
    (`heuristic` | `llm`) is recorded for the sidecar.
- **M3 — `contig extract-claims` CLI command** (`src/contig/cli.py`, a new `@app.command()`
  after `reproduce`; it must **not** call `run_reproduction`):
  - `contig extract-claims <paper>` positional (a local `.txt`/`.md` path), `--out <path>`
    (required, the draft claims JSON).
  - Reads the input as UTF-8; **size-bounded** (`stat()` before read; reuse the 8 MiB
    `_MAX_MATCH_BYTES` bound or a sibling constant), over cap → exit non-zero naming the size.
    Missing / unreadable / non-UTF-8 input → exit non-zero, **nothing written**.
  - Runs the extractor (core always; LLM assist merged when configured), writes two files:
    1. `<out>` — the draft claims JSON: a list of **locator-less** `{id, value, tolerance}`
       objects (tolerance = the default `0.1`), and **nothing else** (all provenance goes to
       the sidecar, so the JSON stays clean and schema-minimal).
    2. **Review sidecar** `<out>.review.md` (derived: `.json` → `.review.md`, else append
       `.review.md`) — per claim: id, value, unit, origin (`heuristic`/`llm`), and the **source
       sentence**; plus a header explaining that each claim needs a locator
       (`from`+`path` / `pattern` / `column`+`row` / `cell`+`pattern`) added before running
       `contig reproduce`.
  - **Self-validating invariant:** before writing, the command round-trips the draft through
    `load_claims` and fails loud if it would not load — we never emit a file that our own
    reproduce path would reject.
  - **Empty extraction is not an error:** write `[]` + a sidecar saying "no numeric claims
    found; add claims by hand or check the input," exit 0.

### Should-have

- `--force` to overwrite an existing `--out` (default: refuse, to protect a hand-edited draft).
- A `--provider`/`--no-llm` style override note (the env gate is primary; a `--no-llm` flag
  that forces core-only even when a provider is configured is a cheap, honest addition).
- Origin/confidence surfaced in the sidecar as a "review first" ordering (llm-only or
  low-confidence candidates flagged for extra scrutiny).

### Nice-to-have (explicitly deferred, not this slice)

- Locator **inference** (guessing `from`/`path`/`pattern` from the repo's output) — a separate,
  harder slice; v1 emits locator-less drafts by design.
- Table-in-text extraction (markdown tables of results).
- A dashboard "extract claims" surface.

## Technical Considerations

- **Where it sits in the pipeline.** This is claims-file **input generation** — strictly
  upstream of the unchanged `load_claims → run_reproduction → verdict → bundle` path. It
  produces an artifact the human edits; it never binds or verifies.
- **Schema contract** (`reproduce.py:531-794`): a claim needs `id` (unique), `value` (numeric
  non-bool), optional `tolerance` (> 0, default 0.1); a locator-less claim (id/value/tolerance
  only) is valid and is exactly what we emit. Confirmed the round-trip is the safety net.
- **LLM seam precedent** (`detect.py:410-633`): reuse `_selected_provider()` for the env gate;
  give the extractor its **own** `_llm_complete`-shaped seam (extraction-specific prompt, its
  own monkeypatch point) so extraction is independently mockable and importing the module never
  pulls a provider SDK. `tech-plan` settles reuse-vs-replicate of the completion call.
- **Reproducibility / verification impact.** Positive and bounded: it lowers the effort to
  *start* a reproduction and carries provenance (source sentence) into the sidecar. It cannot
  produce a false `REPRODUCED` — an unreviewed or wrongly-extracted claim that the user leaves
  unbindable degrades to `UNVERIFIED` at reproduce time. No raw-read egress (operates on paper
  text the user supplies; emits a claims file).
- **Determinism / CI discipline** (the C8 standard): the core is pure and fully CI-tested
  against on-disk fixture `.txt`/`.md`; the LLM path is prompt/shape-tested with the seam
  monkeypatched and is **run for real only at a manual pre-merge gate** — no real LLM, network,
  or provider SDK in CI. Stdlib-only for the core (`re`); no new runtime dependency (the
  provider SDK is a lazy, optional import inside the seam, as with the `llm` detector).
- **No `models.py` change** — the output is a claims file, not a new record type.

## Risks & Open Questions

- **R1 — Heuristic precision/recall on real prose is the feasibility crux.** A regex core will
  miss claims phrased unusually and over-match some prose. *Mitigation:* (a) draft-**for-review**
  (the human is the precision filter), (b) the verdict contract (`UNVERIFIED`, never false pass),
  (c) the optional LLM assist for recall. *Measure honestly* on the fixture corpus; do not
  over-claim.
- **R2 — Percentage unit ambiguity** (`87` vs `0.87`). *Mitigation:* emit the raw value + the
  `%` unit in the sidecar; the human reconciles against the repo's output convention. We never
  auto-scale.
- **R3 — id collisions / churn.** Auto-slugs must be unique and stable. *Mitigation:*
  deterministic uniquifier; ids are human-editable in the draft.
- **R4 — LLM non-determinism, cost, no CI coverage.** *Mitigation:* the seam is optional and
  mocked in CI; the core always works without it; a manual gate exercises the real path once
  pre-merge (the `test_detect_llm.py` discipline).
- **R5 — Scope creep toward locator inference or PDF/DOI.** *Mitigation:* explicit non-goals
  below; v1 emits locator-less drafts from local text only.
- **Open:** exact sidecar ordering/format details; the metric vocabulary's initial membership
  (settle in `extractor-core` spec); whether `--no-llm` ships in v1 or as a fast-follow.

## Out of Scope (explicit)

- **PDF parsing, DOI resolution, and paper *fetching*** (network + parsing) — deferred.
- **Auto-verification of unreviewed claims** — extraction only ever produces a draft.
- **Locator inference** — no guessing where a number lives in the repo's output.
- **Figure/plot and table-image claims** — hard-blocked (no plot-hash, stdlib-only).
- **Any change to the verdict / locator / bundle / signing / exit-code contract.**

## Proposed aspect decomposition (for `tech-plan`)

1. **`extractor-core`** — the pure deterministic `claim_extraction.py`: `extract_claims`,
   `ExtractedClaim`, the metric vocabulary + connective patterns, percentage/unit handling,
   id-generation + dedup, never-raises. Fully CI-tested against fixture text.
2. **`llm-assist`** — the optional env-gated `extract_with_llm` seam + defensive reply parse +
   merge/dedup with the core; mocked in CI, manual gate pre-merge.
3. **`cli-command`** — `contig extract-claims`: I/O, size/encoding guards, the `load_claims`
   round-trip invariant, the review-sidecar writer, exit codes, empty-extraction handling.

## Guardrail check (CLAUDE.md)

**Layer 2, clean.** This extracts verification *input* (claims to verify); it does not author
workflows from English (Layer 1). The LLM is a replaceable, optional dependency consumed behind
a seam — never the product — and the whole feature "gets better as base models improve." No
wet-lab/clinical/proprietary-data precondition.

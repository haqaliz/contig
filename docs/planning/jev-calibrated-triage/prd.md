# PRD — Jev calibrated triage (C9, slice 1)

**Stage:** draft for review gate · **Date:** 2026-10-10 · **Owner:** aliz
**Source:** inline brief (contig-next handoff 2026-10-10) + C9 PRD/roadmap text from
`origin/feat/jev-triage@888df6c` (`docs/planning/_card/c9-prd-branch.md`, `c9-roadmap-branch.md`)
**Slug:** `jev-calibrated-triage` · **Branch:** `feat/jev-calibrated-triage/aliz`

---

## Problem Statement

The verified verdict (concordance, plausibility, structural checks) and the self-heal
loop are Contig's trustworthy-but-costly core. Deep checks are eager and unprioritized:
`_discover_qc` evaluates every rule-pack check in a flat samples×checks loop
(`verification/rule_pack.py:601-621`), `overall_verdict` is order-agnostic
(`models.py:85-111`), and the verify-time concordance evaluators run one-per-invocation
with no sense of which run is worth the expensive corroboration (`cli.py:2188-2232`).
We want a cheap, *calibrated* signal that decides which QC anomalies are worth an
expensive deep check — without letting a cheap cloud model near the verdict or raw
reads. Everything triage-related must be measurable against the execution-grounded
outcome, or the vendor's "calibration" claim becomes marketing.

## Goals & Success Metrics

- **Slice 1 success:** a fully injectable, off-by-default triage seam with a
  measurable calibration ledger, wired at one real decision site, with zero behavior
  change when triage is off (byte-identical) and zero correctness-loss when it is on.
- **Measured:** `contig triage-stats` over the sidecar reports confidence-vs-actual
  rows per surface; the number of skipped checks in active mode is honest and small;
  triage on vs off yields identical verify verdicts on the checks that ran (CI test).
- **Non-goal for slice 1:** proving Jev improves anything (needs real keyed runs).

## Personas & Scenarios

- **A, lone computational biologist:** wants the run/verify loop to spend computing
  attention where it matters; a WARN-spam run should skip corroboration it doesn't
  need, with an honest record of what was skipped.
- **C, core facility (future managed tier):** shadow/active triage is a cost knob on
  their compute — the ledger is the audit trail that keeps it honest.

## Requirements

### Must (slice 1)

**R1 — `Triage` seam, `NullTriage` default.** New `src/contig/triage.py` exposing a
Callable seam in the house injectable pattern (precedent: `Executor`/`Fetcher`/
`Sleeper`, `runner.py:718-744`): `Triage = Callable[..., TriageResult]`, `NullTriage`
(the default — returns "no triage" without touching anything), and
`default_jev_triage` (the real one). All failure modes degrade to the Null behavior —
never raise, never change behavior (precedent: `extract_with_llm` degrades to `[]`,
`claim_extraction.py:423-442`; deliberately NOT the `get_detector` registry which
raises when unkeyed, `detect.py:741-748`).

**R2 — BYOK env gate, off by default.** `CONTIG_JEV_KEY` (precedent:
`CONTIG_SIGNING_KEY`, `bundle.py:33`). Absent/empty ⇒ NullTriage, **no network, exit
unchanged** (asserted on the constructed request/env). Key present ⇒ JevTriage, but
**shadow mode is the default**: everything runs, Jev is logged alongside, nothing is
skipped. The key is never logged and never leaves the machine in any payload.

**R3 — Active mode only behind an explicit flag + threshold budget.** `--triage-active`
on `contig run` and `contig verify` (off by default), with `--triage-threshold <0-1>`.
Flag without a key is refused naming `CONTIG_JEV_KEY` (companion-refusal precedent:
`_validate_stall_flags` via `get_parameter_source`, `cli.py:367-399`; the URL/DOI
refusals `cli.py:1130-1150`). Threshold without active is refused, not ignored. In
active mode a check whose Jev confidence is below the threshold is **skipped and
recorded UNVERIFIED** (never PASS, never silent — the PRD's honest-limit contract).

**R4 — The skip rule is a precise, testable predicate: a check is skippable iff
`kind == "concordance"` or its rule carries no `fail_*` bound.** This is NOT "all
WARN-capped plausibility checks": `VARIANT_RULE_PACK` carries FAIL bands
(`ts_tv`/`het_hom`/`variant_count`) and `SOMATIC_PLAUSIBILITY_PACK` has
`somatic_variant_count fail_below: 1` — those never route through the skip decision,
and neither do structural/did-it-run checks. The skippable set is enumerated and
pinned by a test walking the shipped rule packs against the predicate (rule-level:
`rule_pack.py:545-564` band dicts). A skipped check surfaces as an honest
UNVERIFIED `QCResult`/note with the threshold and the skipped reason — never a silent
absence, never less information than today.

**R5 — Slice 1 wires two sites, but exactly ONE carries active-mode skipping.** The
seam threads into `self_heal_run` as an injectable kwarg (precedent: `propose`,
`sleeper`, `self_heal.py:1186-1201`) at the QC-anomaly verdict-trigger branch
(`self_heal.py:1250-1304`) and into the verify-time concordance dispatch
(`cli.py:2188-2232`), plus `run_heal_scenario` (`heal.py:229-246`) so CI stays
deterministic. Honest grounding: the qc_anomaly branch has **no deep re-check to
pre-screen today** — it synthesizes a Diagnosis and captures a corpus case, both
cheap honesty machinery — so at that site the seam is **ledger-only** (record Jev's
confidence against the actual QC-FAIL results; the data that later calibrates "which
QC anomalies are worth deep corroboration"), while the **verify-time concordance
dispatch is the only active-mode skip surface** (R4-predicate checks). The qc_anomaly
trigger itself always fires — it is not skippable. Triage on vs off ⇒ identical
verify verdicts on the checks that ran (the PRD's core invariant, enforced by a test,
and in active mode the check-level contract of R4).

**R6 — Whitelisted egress payload, asserted by test.** The Jev request carries only
numeric QC metrics and metadata: each `QCResult`'s numeric `value` + `check` +
`kind`/`status` (never `message`), the run's numeric summary (task counts, failed
count, repair-attempt count, verdict string of the checks that ran), file **sizes and
sha256 hashes only** (never paths, never read bytes). Never: FASTQ/BAM/VCF/read data,
paths, raw log text, sample identifiers beyond a per-run opaque id. The whitelist is a
single declaration in `triage.py`; the constructed payload is asserted in a test that
a raw-read field can never appear (mutation control).

**R7 — Contig-defined JSON over stdlib `urllib`, https-only.** `default_jev_triage`
POSTs the R6 payload to a base URL (`CONTIG_JEV_URL`, default documented;
configurable) with a strict 30 s timeout and a response-size bound (precedent:
`_FETCH_TIMEOUT`, `paper_intake.py:236`, `_urlopen` patch point `:249-251`). The
endpoint must be `https://` — a non-https URL is refused by the seam (the payload
carries a bearer key; `http://localhost` allowed for the manual live gate only,
behind an explicit env opt-out named in the docs). Response is Contig-owned JSON
`{"items": [{"id": ..., "confidence": 0-1}]}` parsed defensively (never raises;
malformed ⇒ Null behavior). Item ids are `{run_id}:{surface}:{check}` — the
whitelisted payload keys, so a response item always addresses a real check. No new
dependency (pydantic/typer/cryptography only — stdlib `urllib`/`json`).

**R8 — Calibration ledger + read-only stats.** Each triaged decision appends one row
to an unsigned sidecar `runs/triage-ledger.jsonl` (precedent:
`runs/pending_verify_corpus.jsonl`, `cli.py:2327-2350`): run_id, attempt, surface
(`qc_anomaly` | `verify_concordance`), mode (`shadow` | `active`), the whitelisted
inputs, Jev confidence, and the actual outcome (which checks ran; their recorded
statuses/UNVERIFIED-when-skipped). `contig triage-stats` reads it across runs
(repair-stats precedent, `cli.py` 0.57.0): row counts by surface, mode mix,
confidence-vs-actual cross-tab where outcomes exist, and an honest note when the
ledger is empty/absent or confidence is not yet measurable. No new C6 guard (a
triage-guard would be tautological until real keyed runs accumulate — recorded as
deferred with a revisit trigger).

### Should (slice 1, only if cheap)

- **S1 —** Mention shadow-mode status in `contig show`/text report footer when a key
  is present ("triage shadow active — nothing skipped").
- **S2 —** A `manual`-marked live-call test for the owner smoke check (BYOK), never
  run in CI.

### Won't (this slice)

- Verdict authority for Jev, ever (no verdict promotion/override, no FAIL→PASS).
- Default-on behavior; no bundled or proxied key.
- Raw-read egress under any flag.
- Self-heal attempt ordering across `max_attempts` (no ordering axis exists; recorded,
  not built).
- A fifth C6 guard; a dashboard surface; budget tuning from ledger data.
- Any vendor SDK / new dependency.

## Technical Considerations

- **Placement:** new `src/contig/triage.py` (seam, NullTriage, JevTriage, payload
  builder, response parser, ledger row builder) with wiring in `self_heal.py` and
  `cli.py`; kw-only injectable threading through `run_heal_scenario` for CI.
- **Models:** the ledger is an unsigned sidecar; **no `models.py` change** in slice 1
  (post-v0.63.0 signatures verify stored text, `signing.py:72-85,170-182`, so additive
  fields would be safe — but a sidecar avoids the question entirely).
- **Budget:** `--triage-threshold` defaults (e.g. `0.5`, reasoned-uncalibrated, named
  as such) plus a module `_TRIAGE_TIMEOUT=30` / size-bound constant (house pattern:
  `_MAX_MATCH_BYTES`, `_MAX_INSTALLS`, `CEILING_*`).
- **Reproducibility / verification impact:** the verdict reduction and signed record
  are untouched; only corroborative check *scheduling* changes, and only in active
  mode with an honest UNVERIFIED record. Shadow mode is byte-identical behavior.
- **CI:** Jev seam injected everywhere the loop runs (self_heal, heal scenarios,
  verify); real `default_jev_triage` is asserted on for URL/JSON shape only, never
  executed; no network in CI.
- **Docs:** the payload whitelist and egress contract are documented in
  `docs/technical/ARCHITECTURE.md`-adjacent notes or `triage.py` docstring, and the
  CAPABILITY_ROADMAP C9 section is re-baselined onto master (the branch text is 76
  commits stale).

## Risks & Open Questions

- **Vendor API unverified** — nothing in the repo references Jev/TypeSafe. Mitigated
  by the seam + Contig-owned JSON contract + manual live gate; the CI-observable
  truths are ours (payload, ledger, verdict identity).
- **Latency in active mode** — a slow Jev could delay a run/verify; timeout + degrade
  to Null + shadow-by-default bound it. Worst case in active mode: checks skipped →
  UNVERIFIED with the reason, never a false pass.
- **Under-claiming calibration** — the ledger accrues nothing until real keyed runs
  exist; `triage-stats` must say so rather than present zero rows as proof.
- **"Ordering" grounding** — slice 1 implements pre-screen/skip at the verify-time
  site and ledger-only capture at the qc_anomaly site; genuine ordering of self-heal
  attempts stays unbuilt (no axis), recorded in the roadmap.
- **Committed revisit trigger (house discipline; counted via `contig triage-stats`,
  no new instrumentation):** if the next **20 real keyed runs** (`CONTIG_JEV_KEY` set)
  either produce no ledger rows or show Jev confidence with no measurable
  relationship to outcomes (all shadow mode, no check ever skipped, or a threshold
  that never fires), the triage layer is restated as taxonomy-only and no further
  breadth is built on push alone. If HTTP(S)-transport upstream breaks against real
  calls, revisit the contract, not the seam.

## Out of Scope

Layer-1 authoring; clinical judgement; raw-read egress; verdict authority; default-on
triage; a guarded fifth C6 eval number; dashboard surfaces; budget calibration from
ledger data; vendor SDKs.

## Eval Data Captured

The calibration ledger: Jev's confidence per triaged run/step vs the verdict the
execution-grounded check later produced — the C6 fold-in successor (reliability
curve/ECE and "at threshold, how many real failures were deprioritized" become
possible once real keyed runs accrue). It is the reason the seam exists and the
moat-compounding part.

## Aspect decomposition (proposed, confirm at planning)

- `seam` — `src/contig/triage.py`: seam + NullTriage + JevTriage + payload whitelist
  (R1, R2, R6, R7) + tests incl. whitelist mutation control.
- `wiring` — active-mode flags + refusal validation + QC-anomaly/verify wrap sites +
  heal-scenario threading + skip rule + verdict-identity tests (R3, R4, R5).
- `ledger` — sidecar append + `contig triage-stats` + docs + roadmap C9 re-baseline
  (R8, S1).
# Understanding — jev-calibrated-triage (C9 slice 1)

Phase 2 dig note. Source: `docs/planning/_card/issue.md` (contig-next handoff) + the
branch's C9 PRD (`docs/planning/_card/c9-prd-branch.md`) and roadmap section
(`c9-roadmap-branch.md`), taken from `origin/feat/jev-triage@888df6c`. Code map:
graphify query + two explore agents, file:line verified inline.

## What the work is really asking

Slice 1 of C9: an **injectable, off-by-default triage seam** that can pre-screen and
order (a) QC/anomaly deep-checks and (b) self-heal attempts using a cheap calibrated
external signal (Jev, BYOK via `CONTIG_JEV_KEY`), **shadow-mode default** (run
everything, log Jev alongside), **never verdict authority**, and a **calibration
ledger** folding into the C6 eval flywheel. The verdict identity invariant is the
PRD's core test: triage on vs off ⇒ identical verify verdicts on the checks that ran.

## Code areas (verified)

**Seam conventions to copy (agent 1):**
- Injectable kw-only Callable defaults: `Executor`/`IndexBuilder`/`Installer`/
  `Fetcher`/`Sleeper` (runner.py:718-744, threaded kw-only :1384-1398;
  self_heal.py:1186-1201; reproduce.py:855-862; fetch.py:313). A `Triage` seam
  should follow this, NOT the Detector registry (`get_detector` raises unkeyed,
  detect.py:741-748 — a Triage gate must degrade silently instead).
- Silent env gate: `extract_with_llm` → `_selected_provider()` → `None` ⇒ `[]`
  (claim_extraction.py:423-442; detect.py:532-558). BYOK env precedent:
  `CONTIG_SIGNING_KEY` (bundle.py:33). Same env-var name must never log a key.
- Network posture: single `_urlopen` patch point + `_FETCH_TIMEOUT = 30` + size
  bounds (paper_intake.py:236-306); opt-in flags `--allow-fetch`/`--allow-install`
  off by default with refusal messages (cli.py:1043-1071, 1130-1150); companion-flag
  refusal via `get_parameter_source` (`_validate_stall_flags`, cli.py:367-399).
- CI determinism: lazy SDK import + shape-asserted fake modules
  (tests/test_claim_extraction_llm.py:288-384), argv-shape-only asserts
  (test_reproduce_remote_intake.py:196-238), never-executed success path.
- Budget-knob house pattern: module `_UPPER_SNAKE` + CLI flag default
  (`_MAX_INSTALLS=2` reproduce.py:58, `_MAX_MATCH_BYTES`, stall 3600.0, ceilings).

**Triage targets (agent 2):**
- QC anomaly trigger: self_heal.py:1250-1254 (succeeded + qc_results + verdict
  fail), synthesized Diagnosis @confidence 1.0 :1261-1272, `qc_verdict_flagged`
  outcome :1276-1292, pending-corpus capture :1307-1319. QC itself: `_discover_qc`
  (runner.py:286-713), called at :1432; `overall_verdict` is order-agnostic
  (models.py:85-111); rule-pack `evaluate()` is a flat eager samples×checks loop
  (rule_pack.py:601-621) — **no ordering/priority/budget concept exists today**.
- Self-heal loop: `self_heal_run` (self_heal.py:1177-1678): detect :1335 →
  `propose` :1350 → `_safe_patch` :1351 → apply/gate :1371-1606; `max_attempts=3`
  :1190; **`propose_patches` returns one patch per class — there is no candidate
  ranking to reorder today** (repair.py:14-183; `_gated_candidates` :286-288).
- Verify-time deep checks: six mutually-exclusive `--concordance-*` flags, dispatch
  if/elif (cli.py:2188-2232), one evaluator per invocation (:2353-2380) — the
  "expensive deep check" surface.
- Ledger home: `runs/` sidecars are unsigned (pending_verify_corpus.jsonl,
  cli.py:2327-2350); `RunRecord.verification_inputs` is the value-based capture
  idiom (models.py:374-381); snapshots/guards: EvalSnapshot etc. (models.py:525+),
  snapshot_history.py:21-40, the four guards (cli.py:3554/3706/3893/4044).
- Signatures: v0.63.0 stored-record-text verification (signing.py:72-85, 170-182)
  ⇒ additive optional model fields no longer break old signatures, but a sidecar
  ledger avoids the model entirely — preferred for slice 1.

## Ambiguities / open questions for the interview

1. **Which triage point does slice 1 actually wire?** The PRD names two surfaces
   ("QC-anomaly deep checks" + "self-heal ordering") but `propose_patches` emits one
   patch per class, so "ordering" has nothing to reorder yet. Candidates: (a) the
   qc_anomaly verdict-trigger pre-screen (skip/schedule the deep QC re-run), (b)
   verify-time concordance check ordering, (c) a self-heal attempt pre-screen
   (don't spend an attempt when Jev says low yield). Need the owner's pick — the
   minimal honest slice is one real wrap site + seam + ledger.
2. **Budget knob semantics**: top-N vs confidence threshold vs both; where it lives
   (CLI flag vs env); does the knob bite in shadow mode (probably not — shadow logs).
3. **Ledger shape**: per-check rows (check id, run id, triage inputs, Jev confidence,
   actual QCResult status/verdict contribution) and per-attempt rows (Diagnosis
   inputs, Jev confidence, actual outcome family); command surface
   (`contig triage-stats`? fold into `repair-stats`/a new guard?); whether it is
   guarded as a fifth C6 guard (probably not — needs real-run accumulation).
4. **Jev API input/output contract**: unverified vendor. Slice 1 must define a
   Contig-owned typed request (whitelisted numeric QC metrics + metadata) and
   response (per-item confidence 0-1), and isolate the actual HTTP client behind the
   seam (manual live-call gate). Can the transport assume an OpenAI-compatible
   HTTP+JSON shape or a bespoke endpoint? (Owner's call — vendor docs not in repo.)
5. **Payload whitelist source**: derive from QCResult numeric values + metadata
   (never paths/read data). What exactly is "error signatures" — normalized
   failure-class + counts, not raw log text?
6. **Where the seam threads**: `self_heal_run` kwarg (precedent: `propose`/`sleeper`),
   `run_heal_scenario` (heal.py:229-246) for CI determinism, and the verify CLI. Does
   run_pipeline's `_discover_qc` also need it in slice 1?
7. **Key handling**: absent ⇒ no-op, no network, exit unchanged (PRD). Invalid/
   falsy key ⇒ same as absent? Key never logged, payload assertable.
8. **No new dependency** (pydantic/typer/cryptography only): Jev transport must be
   stdlib `urllib` (paper_intake precedent) unless a supplier SDK is explicitly
   accepted.

## Contradictions surfaced (not papered over)

- The C9 roadmap text on the branch claims "~100× cheaper than an LLM" and names
  TypeSafe's "System One" — **nothing in the repo verifies the vendor or its API**;
  every CI-observable property is ours (seam, whitelist, ledger, verdict identity).
  The branch is 76 commits behind master and its roadmap section/PRD must be
  re-baselined against the current text (e.g. C2/C6 sections moved since).
- "Ordering" of self-heal is the PRD's phrasing, but the loop has exactly one patch
  per class and `max_attempts=3` — the only orderable axis today is *whether* and
  *in which order* attempts get made across a multi-attempt run, and the QC-anomaly
  deep-check scheduling. The PRD interview must ground "ordering" in a real site.

## Guardrails check (CLAUDE.md)

Layer 2 (triage/router over run/verify machinery — never Layer 1) ✓. No raw-read
egress (numeric QC metrics/metadata whitelist only, asserted in a test) ✓. No
correctness over-claim (triage never sets/promotes a verdict; deprioritized check is
UNVERIFIED, never PASS) ✓. No clinical/wet-lab credentials ✓. Test-first, Jev stubbed,
no network in CI, live call manual-marked ✓. Not blocker-deferred, not re-shipped
(no C9 work exists on master — confirmed by grep and the CHANGELOG's empty
[Unreleased]) ✓.
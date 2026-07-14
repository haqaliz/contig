# Card: verdict-exit-code

- **Type:** feat
- **Id / slug:** verdict-exit-code
- **Branch:** feat/verdict-exit-code/aliz
- **Owner:** aliz
- **Source:** inline brief (from `contig-next` handoff — no GitHub issue)

## Brief

Wire Contig's verified **FAIL** verdict into the CLI exit code as an **opt-in**
policy. Add a flag (working name `--fail-on-verdict`, default off) to `contig run`
and `contig verify` so that when the reduced verdict is **FAIL**, the command exits
non-zero — making the moat's "verified verdict" enforceable in scripts and CI.

This is the explicit, repeatedly-deferred follow-on named in v0.35.0's changelog and
across the C3 slices. It's unblocked now that the germline plausibility FAIL bands
shipped (v0.35.0), and it needs **no real-cohort calibration** — a plumbing slice
with a crisp test-first shape.

### Grounding (verified in code before recommending)

- `src/contig/cli.py:619-620` — `contig run` exits non-zero **only** when the pipeline
  itself didn't succeed (`RunSummary.from_events(record.events).succeeded`). A FAIL
  verdict does not move the exit code.
- `src/contig/cli.py:957-971` — `contig verify` exits non-zero **only** on output
  drift or a signature mismatch. Concordance/QC verdict never changes the exit code.
- So today: Contig can render a scientific **FAIL** (structural missing/corrupt
  output, or the new v0.35.0 germline Ti/Tv / het-hom / empty-call-set bands) while the
  CLI still returns **0**. The headline moat — "the verified verdict"
  (`FEATURES.md:36-38`) — has no teeth in automation.

### The named-deferral trail

- `CHANGELOG.md:47-52` (v0.35.0): *"the `contig run`/`verify` exit code is unchanged —
  no QC verdict, including pre-existing FAIL packs like `mean_coverage`, moves the exit
  code today; wiring that is a deliberate, separately-scoped, cross-cutting follow-on."*
- `docs/technical/CAPABILITY_ROADMAP.md:469-472` — same "exit-code wiring deferred" note
  on the germline plausibility FAIL-severity slice.

## Why (moat framing, from contig-next)

- CLAUDE.md #2: "make every verdict harder to fool." A verdict the CLI ignores can't
  gate automation — the FAIL is cosmetic in a script/CI context.
- The verified verdict is Contig's headline differentiator (`FEATURES.md:36-38`); no
  incumbent issues an output-correctness verdict. Making FAIL enforceable is the
  natural next step after v0.35.0 gave germline plausibility its first FAIL bands.
- No real-cohort calibration required (unlike the other open C3/C4 FAIL-severity
  items) — this is pure plumbing, high-leverage, unblocked.

### Caveat — keep it opt-in and back-compatible

Cross-cutting and back-compat-sensitive:

- Existing users/CI rely on `contig run`/`verify` exiting 0 on a completed pipeline.
- Several **structural FAIL packs already exist** (`mean_coverage fail_below`,
  missing/corrupt output), so a non-opt-in change would suddenly start failing runs
  that pass today.
- Therefore: **opt-in flag, default off.** Default behavior and `--json` payloads must
  stay identical.
- Slice 1 maps **only FAIL → non-zero**; WARN and UNVERIFIED stay zero.

## Open questions for the dig / interview

1. Flag surface: a per-command flag on both `run` and `verify`, or a shared policy?
2. Does slice 1 cover both `run` and `verify`, or `verify` first?
3. Exit code value: `1`, or a distinct code (e.g. `2`) to disambiguate "FAIL verdict"
   from "pipeline crashed / bad args"?
4. Interaction with `--json` (payload unchanged; exit code still applies).
5. How is the "reduced verdict" obtained at the CLI layer for each command
   (`run` renders a report; `verify` re-hashes)? Where does FAIL come from on each path?

## Acceptance (test-first)

- A FAIL-verdict fixture run asserts **non-zero** exit under the flag.
- PASS / WARN / UNVERIFIED assert **zero** under the flag.
- Default (no flag) is **byte-identical** to today (exit + `--json` payload).

## Guardrails (CLAUDE.md)

- Layer 2 only (run/verify/reproduce). This is verification depth — on-thesis.
- No clinical/diagnostic claim: enforces the existing verdict, adds no new science.
- No new dependency expected. No raw-read egress.
- Test-first (repo standing discipline).

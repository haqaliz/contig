# Understanding — feat reproduce-paper-claims (Phase 2 dig)

## What the work is really asking

`contig reproduce` today needs the user to **hand-author a claims file** — a JSON list of
`{id, value, tolerance, <locator>}` objects. Slices 1–7 built the whole verify/locator/
bundle spine; the one manual input left is the claims list. This slice generates a **draft**
claims file from a paper's **plain-text/markdown** text, which the user reviews and completes
before running `contig reproduce`. It is claims-file **input generation** — it does not touch
the verdict, locator, or bundle contracts.

## The two contracts it must respect (from the dig)

### 1. `load_claims` schema (`src/contig/verification/reproduce.py:531-794`)
A claims file is a JSON **list**. Per claim: `id` (required, unique), `value` (required,
numeric non-bool), `tolerance` (optional, default 0.1, strictly > 0), and **at most one**
locator family (mutually exclusive):
- **locator-less** (flat): just `id`/`value`/`tolerance` — observed value looked up by `id`
  in the flat `--results` `{id: value}` map.
- JSON `{from, path}`, TSV/CSV `{from, column, row, header?, delimiter?}`, stdout/log
  `{pattern, from?}`, notebook `{from, cell, pattern}`.

**Key realization:** the paper text tells us the **claimed value** (e.g. "AUC of 0.91"), but
**not where that number lives in the repo's output**. So an extracted claim can honestly
carry `id` + `value` (+ default `tolerance`) but **cannot** invent a `from`/`path`/`column`
locator — that mapping is repo-specific and unknown from the paper. The natural, honest
output is a **locator-less draft** the user augments with locators during review. (This is
the crux to confirm in the interview.)

### 2. The optional-LLM seam precedent (`src/contig/detect.py:410-633`)
The template to copy exactly:
- Env-gated via `CONTIG_LLM_PROVIDER` + provider→key map (`ANTHROPIC_API_KEY`/`OPENAI_API_KEY`);
  `_selected_provider()` returns the provider only when configured, else `None`.
- The single network/SDK touch point is `_llm_complete(provider, prompt) -> str` — the ONLY
  place a provider SDK is lazily imported; tests monkeypatch this one function.
- `"llm"` is resolved **dynamically** in `get_detector` via `build_llm_detector()`; the static
  registry holds only the network-free detectors, so importing the module never pulls an SDK.
- A deterministic core (`rules`) always runs; the LLM is optional and additive.

## Affected areas / where it slots in

- **New module** `src/contig/verification/claim_extraction.py` (or similar): a pure,
  deterministic heuristic extractor (always runs, stdlib-only) + an optional `extract_with_llm`
  behind a `_llm_complete`-style seam reusing `detect.py`'s env-gating.
- **New CLI command** in `src/contig/cli.py` — a **separate** command (natural home right
  after `reproduce`, ends line 994), e.g. `contig extract-claims <paper.(txt|md)> --out
  <draft.json>`. It reads the paper text, runs the extractor, and writes a schema-valid draft
  claims file. It must **not** call `run_reproduction` or the verdict path. The default
  extractor is a module-level name in `cli.py` (like `default_command_executor`/
  `default_installer`/`default_fetcher`) so tests can monkeypatch it.
- **No `models.py` change** expected — output is a claims file (JSON), consumed by the
  unchanged `load_claims`.

## The honest scope (deferrals baked in)

- **Input = plain-text/markdown only.** No PDF parsing, no DOI resolution, no paper *fetching*
  (network + parsing — out of scope, deferred).
- **Draft for review, never auto-verify.** Output is a file the human edits; extraction is
  never silently bound and run.
- **Locator-less by default.** The paper gives values, not repo output locations; the user
  adds locators. (Confirm; alternatively a best-effort `pattern` guess — likely too weak.)
- **Figures / table-images hard-blocked** (no plot-hash, stdlib-only).
- **The verdict contract already contains extraction error**: any claim the user leaves
  unbindable/ambiguous degrades to `UNVERIFIED` at reproduce time — extraction can be
  imperfect without ever producing a false `REPRODUCED`.

## Open questions for the interview

1. **Command shape**: separate `contig extract-claims` command (recommended) vs. a flag on
   `reproduce`. Draft-for-review strongly implies a separate command that emits a file.
2. **Locator policy**: emit locator-less claims (recommended, honest) vs. best-effort `pattern`
   guesses. Does the user want a review **sidecar** (e.g. a `.review.md` mapping each claim id
   to the source sentence) so provenance is visible while the JSON stays clean?
3. **Deterministic-core reach**: which claim shapes does the heuristic core target? (e.g.
   "AUC of 0.91", "accuracy of 87%", "log2 fold change −2.3", "p < 0.001".) How to handle
   percentages (keep raw `87` vs `0.87`?) and inequalities (`p < 0.001` — numeric claim or
   dropped?). This is the feasibility crux; keep the first slice narrow.
4. **id generation**: auto-slug from surrounding context, guaranteed unique + human-editable.
5. **LLM assist in v1**: ship the deterministic core only first, or both core + optional
   env-gated LLM seam in this slice? (Card says both, seam off in CI.)
6. **Confidence / candidate marking**: should low-confidence extractions be marked (e.g. a
   sidecar "needs review" flag) so the human knows which to scrutinize?

## Guardrail check (CLAUDE.md)

This is **Layer 2** (verification input), not Layer-1 workflow authoring. The extractor
consumes an optional LLM as a replaceable dependency (never the product), and it "gets better
as base models improve" (`CLAUDE.md` #3). No wet-lab/clinical/proprietary-data precondition.
Clean.

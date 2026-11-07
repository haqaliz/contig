# Ask-Your-Run Assistant — M1 Implementation Plan

**Status:** implemented 2026-11-07 — Tasks 1–7; 31 assistant tests pass.

**Goal:** Add `contig ask` and `contig ask-eval`: deterministic, grounded answers
over a run bundle plus optional M1/M2 tables, with source citations and an
optional LLM paraphrase layer.

**Architecture:** A new `contig.assistant` package. A keyword router selects an
intent; pure answer builders read the run record/tables and produce an `Answer`
with `sources` and `actions`. An optional OpenAI-compatible client paraphrases
the grounded answer. `ask-eval` runs the deterministic router over a frozen
JSONL set. No new dependencies, no network in CI.

## Global Constraints

- **Grounded only.** Every answer cites a source path + SHA-256; unknown
  questions are refused, never guessed.
- **Research-use only.** No diagnosis, ACMG classification, or treatment advice.
- **LLM is paraphrase-only.** It receives the grounded answer + sources and is
  told not to add facts; missing config is a clear error.
- **No raw reads.** Only bundle metadata, QC, repairs, provenance, and tables.
- **No new dependencies.** Stdlib `urllib` for the optional client.

---

### Task 1: Models

**Files:**
- Create: `src/contig/assistant/__init__.py`
- Create: `src/contig/assistant/models.py`
- Create: `tests/test_assistant_models.py`

**Interfaces:**
- `Citation`: label, path, sha256, detail.
- `Answer`: intent, answer, citations, confidence (`high|none`), actions.
- `EvalCase`: question, expected_intent, expected_source_kind.
- `EvalReport`: total, passed, accuracy, misses.

**Tests:** JSON round-trip, defaults.

---

### Task 2: Context loading

**Files:**
- Create: `src/contig/assistant/context.py`
- Create: `tests/test_assistant_context.py`

**Interfaces:**
- `load_context(runs_dir, run_id, variants_path, readiness_path) -> Context`
  with record, bundle dir, variants, readiness, and input citations.

**Tests:** loads fixture run + tables; missing run/table errors; citations carry
hashes.

---

### Task 3: Deterministic router and answer builders

**Files:**
- Create: `src/contig/assistant/answer.py`
- Create: `tests/test_assistant_answer.py`

**Interfaces:**
- `answer_question(context, question) -> Answer`
- Intent builders: verdict, qc, repairs, provenance, methods, variants,
  readiness, report, help, unknown.
- Gene extraction from the question against attached data.
- Suggested actions per intent.

**Tests:** each intent; gene-specific variants/readiness; unknown refusal; no
fabricated citation; verdict/QC/repair content.

---

### Task 4: Optional LLM paraphrase

**Files:**
- Create: `src/contig/assistant/llm.py`
- Create: `tests/test_assistant_llm.py`

**Interfaces:**
- `ModelClient` protocol: `complete(prompt) -> str`.
- `HttpModelClient.from_env()` (OpenAI-compatible; no default provider).
- `paraphrase(answer, client) -> Answer` (keeps citations/actions; replaces text
  with the model output; refuses empty output).

**Tests:** fake client receives the grounded answer + citations; empty response
falls back; missing env raises a clear error.

---

### Task 5: Eval

**Files:**
- Create: `src/contig/assistant/evaluate.py`
- Create: `tests/test_assistant_evaluate.py`
- Create: `tests/fixtures/assistant/eval.jsonl`

**Interfaces:**
- `load_eval_cases(path) -> list[EvalCase]`
- `evaluate_cases(context, cases) -> EvalReport`
- `EvalReport.exit_ok(threshold)`.

**Tests:** all fixture cases pass; a deliberately wrong case fails; accuracy math.

---

### Task 6: CLI

**Files:**
- Modify: `src/contig/cli.py`
- Create: `tests/test_cli_ask.py`

**Interfaces:**
- `contig ask RUN_ID "question" [--runs-dir] [--variants] [--readiness] [--json] [--llm]`
- `contig ask-eval [--runs-dir] [--variants] [--readiness] [--cases] [--min-accuracy]`

**Tests:** help, verdict answer, JSON output, unknown refusal, eval pass, missing
run error, `--llm` without config error.

---

### Task 7: Docs and manual verification

**Files:**
- Modify: `docs/USAGE.md`
- Modify: `CHANGELOG.md`

**Manual checks:**
- Ask the fixture run about verdict/QC/repairs/provenance/BRCA1 readiness.
- Confirm every answer cites the right file/hash.
- Run `ask-eval`; confirm the accuracy report.
- With a configured OpenAI-compatible endpoint (optional/manual), confirm the
  paraphrase keeps the citations.

---

## Verification

```bash
uv run pytest tests/test_assistant_*.py tests/test_cli_ask.py -q
uv run contig ask --help
uv run contig ask-eval --help
```

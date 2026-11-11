# M5 live LLM paraphrase eval

**Run 2026-11-09.** Model: `qwen2.5:1.5b` via a local Ollama OpenAI-compatible
endpoint (`http://localhost:11434/v1/chat/completions`). Test data: the
`tests/fixtures/reporting` bundle (synthetic; no patient data) and the frozen
9-question set in `tests/fixtures/assistant/eval.jsonl`.

## What was tested

`contig ask --llm` must only rephrase the deterministic grounded answer. The
eval compares, per question:

- the intent (must not change);
- the citations (label/path/SHA-256 must not change);
- a refusal (if the deterministic answer refuses, the paraphrase must refuse);
- the verdict token (`PASS`/`WARN`/`FAIL`/`UNVERIFIED` must not appear or
  disappear);
- a minimum length ratio (0.5x) so a paraphrase cannot silently drop the
  evidence.

## Result

**Before the fidelity guard: 8/9 preserved.** Two real failures:

- *“what is the verdict?”* — the model shortened the answer to 0.31x and dropped
  the deciding-check/QC detail.
- *“what is the weather?”* — the model changed the deterministic refusal into a
  non-refusal.

**After the guard: 9/9 preserved.** The guard falls back to the deterministic
answer when the model changes a refusal, drops/adds a verdict token, or returns
less than half the grounded text. The guard is in
`src/contig/assistant/llm.py` (`_preserves_grounding`); it is a fidelity check,
not a semantic judge.

## Reproduce

```bash
# Local model (no data leaves the machine)
ollama pull qwen2.5:1.5b
export CONTIG_LLM_URL=http://localhost:11434/v1/chat/completions
export CONTIG_LLM_MODEL=qwen2.5:1.5b
python scripts/llm_eval.py \
  --runs-dir tests/fixtures/reporting/runs \
  --variants tests/fixtures/reporting/variants.json \
  --readiness tests/fixtures/reporting/readiness.json \
  --cases tests/fixtures/assistant/eval.jsonl \
  --out /tmp/m5_llm_eval.csv
```

Hosted small model (only redacted bundle text may leave the machine):

```bash
export CONTIG_LLM_URL=https://api.openai.com/v1/chat/completions
export CONTIG_LLM_MODEL=<current small/cheap model id>
export CONTIG_LLM_API_KEY=<key>
python scripts/llm_eval.py ... --out /tmp/m5_llm_eval_hosted.csv
```

## Decision and acceptance

**Decision 2026-11-11 — local-only default.** No hosted provider is bundled.
`--llm` is opt-in and requires an explicitly configured local
OpenAI-compatible endpoint; the deterministic router remains the product. This
closes M5-1 as a decision, not as a hosted-provider deployment.

Acceptance for the shipped local path:

1. 9/9 preserved on the frozen set (intent, citations, refusal, verdict).
2. A real redacted bundle from a partner passes the same checks.
3. The endpoint is explicitly configured; there is no default provider.
4. No clinical claim appears in a paraphrase that was not in the grounded answer.

Hosted use would need a new explicit provider/privacy decision and a redacted
bundle run; it is not part of the current defaults.

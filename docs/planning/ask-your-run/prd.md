# PRD — Ask-your-run assistant (M5)

Feature slug: `ask-your-run` · Type: feat · Owner: aliz
Branch: `feat/ask-your-run/aliz` · Capability: **M5 (ask-your-run)**
Status: drafted 2026-11-07

## Problem Statement

A run bundle contains the verdict, QC checks, repair chain, provenance, and
(optionally) the M1/M2 tables. Finding the answer to "why did this run warn?",
"what happened to the OOM?", or "is BRCA1 ready?" means reading JSON or
remembering which command to run.

M5 adds a **grounded ask-your-run assistant**: a CLI that answers questions from
the bundle and attached tables, cites the exact source and SHA-256, and suggests
the next command. The deterministic retrieval layer is the product; an optional
LLM only paraphrases the grounded answer, never invents facts.

This is research-use only. It does not diagnose, classify pathogenicity, or
recommend treatment.

## Goals & Success Metrics

- **G1 — Grounded answers.** Every answer names the source file and SHA-256 that
  supports it; an unknown question is refused, not guessed.
- **G2 — Useful intents.** Verdict, QC, repairs, provenance, methods, attached
  variants (including gene queries), attached readiness, and report next steps.
- **G3 — Suggested actions.** Each answer proposes concrete CLI commands
  (`contig show --explain`, `contig verify`, `contig report`, etc.) without
  executing them.
- **G4 — Optional LLM paraphrase.** `--llm` rewrites the deterministic answer
  using only the provided context and citations; no model is required for v1.
- **G5 — Eval.** A frozen question/citation set and `contig ask-eval` report
  intent accuracy; CI uses the deterministic router.

## Requirements

### Must-have (v1)

- `contig ask RUN_ID "question" [--runs-dir] [--variants] [--readiness] [--json]
  [--llm]`
- Deterministic router for: verdict, QC, repairs, provenance, methods, variants,
  readiness, report, help, unknown.
- Gene extraction from the question when the gene appears in the attached
  variants/readiness data; a gene-specific answer otherwise.
- Answer object: intent, answer text, sources (label/path/SHA-256), confidence,
  suggested actions.
- Refusal path: "I can answer about …; I won't guess." with no fabricated source.
- `--json` machine-readable output.
- Optional `--llm`: OpenAI-compatible endpoint via `CONTIG_LLM_URL`,
  `CONTIG_LLM_MODEL`, `CONTIG_LLM_API_KEY`; the prompt contains the grounded
  answer + sources; the model is told to paraphrase only and to keep citations.
  Missing config is a clear error, not a silent fallback.
- `contig ask-eval --cases <jsonl> [--min-accuracy]` runs the deterministic
  router over a frozen set and exits non-zero below the threshold.
- Tests: synthetic run bundle + M1/M2 JSON; fake model client; no network.

### Should-have (later slices)

- A dashboard chat panel.
- Follow-up questions with conversation state.
- **Shipped 2026-11-10:** Action execution behind the approval gate
  (`contig ask --execute N`, interactive `y/N` or `--approve-action`; argv-only
  and subcommand-allowlisted).
- Local model support/packaging.
- Retrieval over logs and repair evidence, not just structured fields.

### Nice-to-have / explicit non-goals

- A general bioinformatics chatbot.
- Clinical interpretation or diagnosis.
- Autonomous actions without approval.
- Training a model.

## Technical Considerations

- **Deterministic first.** The router and answer builders are pure functions of
  the bundle/tables. The LLM is a paraphrase layer over an already-grounded
  answer; it never retrieves or decides.
- **Citations.** Every answer carries the source path + SHA-256; the JSON output
  makes this machine-checkable.
- **No raw reads.** Only bundle metadata, QC, repairs, provenance, and attached
  table rows.
- **No new dependencies.** Stdlib `urllib` for the optional LLM; pydantic/typer
  existing.
- **Eval as a guard.** The frozen cases are synthetic and self-graded; they pin
  routing/citation behavior, not answer quality against a real model.

## Risks & Open Questions

- **R1 — hallucination via LLM.** Mitigation: deterministic answer + explicit
  "paraphrase only" prompt; the LLM is opt-in; eval covers the deterministic
  layer. Live model eval is a follow-up.
- **R2 — over-broad claims.** Mitigation: research-use banner, refusal path, and
  no clinical vocabulary.
- **R3 — stale context.** Mitigation: citations include SHA-256; report-check
  already covers freshness.
- **Open:** which hosted/local model and privacy mode? (v1: OpenAI-compatible
  endpoint, user-supplied; no default provider.)

## Out of Scope

- Clinical diagnosis, ACMG classification, treatment advice.
- Autonomous action execution, dashboard, conversation state (v1).
- Model training.

## Acceptance

- `contig ask r1 "what is the verdict?"` returns the verdict + deciding checks,
  citing `run_record.json`.
- `contig ask r1 "why did it repair?"` returns the repair chain.
- `contig ask r1 "is BRCA1 ready?"` with a readiness table returns the BRCA1
  state/reason, citing `readiness.json`.
- `contig ask r1 "what is the weather?"` refuses and does not invent a source.
- `contig ask-eval` passes the frozen cases at the configured threshold.

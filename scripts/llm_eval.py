#!/usr/bin/env python3
"""Live LLM paraphrase eval for `contig ask --llm`.

Compares the deterministic answer with the optional paraphrase on a frozen
JSONL question set. The model is allowed to rephrase only: intent, citations,
refusals, and the verdict token must survive. This is a manual validation gate,
not a CI test (no model runs in CI).

Example:
  CONTIG_LLM_URL=http://localhost:11434/v1/chat/completions \
  CONTIG_LLM_MODEL=qwen2.5:1.5b \
  python scripts/llm_eval.py --runs-dir tests/fixtures/reporting/runs \
    --variants tests/fixtures/reporting/variants.json \
    --readiness tests/fixtures/reporting/readiness.json \
    --cases tests/fixtures/assistant/eval.jsonl \
    --out /tmp/m5_llm_eval.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

VERDICTS = ("PASS", "WARN", "FAIL", "UNVERIFIED")


def run_ask(args: argparse.Namespace, question: str, *, llm: bool) -> dict:
    command = [
        *shlex.split(args.contig),
        "ask",
        args.run_id,
        question,
        "--runs-dir",
        args.runs_dir,
        "--json",
    ]
    if args.variants:
        command += ["--variants", args.variants]
    if args.readiness:
        command += ["--readiness", args.readiness]
    if llm:
        command.append("--llm")
    result = subprocess.run(command, capture_output=True, text=True, timeout=args.timeout)
    if result.returncode != 0:
        raise SystemExit(
            f"ask failed ({'llm' if llm else 'deterministic'}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return json.loads(result.stdout)


def citation_key(payload: dict) -> list[tuple[str, str, str]]:
    return [
        (item.get("label", ""), item.get("path", ""), item.get("sha256", ""))
        for item in payload.get("citations", [])
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default="r1")
    parser.add_argument("--runs-dir", required=True)
    parser.add_argument("--variants")
    parser.add_argument("--readiness")
    parser.add_argument("--cases", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--contig", default="uv run contig")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    if not os.environ.get("CONTIG_LLM_URL") or not os.environ.get("CONTIG_LLM_MODEL"):
        raise SystemExit("set CONTIG_LLM_URL and CONTIG_LLM_MODEL first")

    cases = [
        json.loads(line)
        for line in Path(args.cases).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows = []
    failures = 0
    for case in cases:
        question = case["question"]
        deterministic = run_ask(args, question, llm=False)
        paraphrased = run_ask(args, question, llm=True)
        same_intent = deterministic.get("intent") == paraphrased.get("intent")
        same_citations = citation_key(deterministic) == citation_key(paraphrased)
        det_refusal = "won't guess" in deterministic.get("answer", "").lower()
        llm_refusal = "won't guess" in paraphrased.get("answer", "").lower()
        refusal_ok = det_refusal == llm_refusal
        det_text = deterministic.get("answer", "")
        llm_text = paraphrased.get("answer", "")
        verdict_ok = all(
            (verdict in llm_text) == (verdict in det_text) for verdict in VERDICTS
        )
        ratio = len(llm_text) / len(det_text) if det_text else 1.0
        ok = same_intent and same_citations and refusal_ok and verdict_ok
        if not ok:
            failures += 1
        notes = []
        if not same_intent:
            notes.append("intent changed")
        if not same_citations:
            notes.append("citations changed")
        if not refusal_ok:
            notes.append("refusal changed")
        if not verdict_ok:
            notes.append("verdict token changed")
        if ratio < 0.6:
            notes.append(f"paraphrase much shorter ({ratio:.2f}x)")
        rows.append({
            "question": question,
            "expected_intent": case.get("expected_intent", ""),
            "det_intent": deterministic.get("intent", ""),
            "llm_intent": paraphrased.get("intent", ""),
            "citations_match": same_citations,
            "refusal_preserved": refusal_ok,
            "verdict_preserved": verdict_ok,
            "det_chars": len(det_text),
            "llm_chars": len(llm_text),
            "length_ratio": f"{ratio:.2f}",
            "ok": ok,
            "notes": "; ".join(notes),
        })

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(f"LLM paraphrase eval: {len(rows) - failures}/{len(rows)} preserved")
    for row in rows:
        if not row["ok"] or row["notes"]:
            print(f"- {row['question']}: {row['notes'] or 'ok'}")
    print(f"Wrote {out}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

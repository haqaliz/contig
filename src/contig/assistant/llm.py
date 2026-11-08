"""Optional LLM paraphrase layer over a grounded answer.

The deterministic answer is the product. The model is only allowed to rephrase
it; it must not add facts or citations. No default provider is configured.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from contig.assistant.models import Answer


class ModelClient(Protocol):
    def complete(self, prompt: str) -> str: ...


@dataclass
class HttpModelClient:
    url: str
    model: str
    api_key: str | None = None
    timeout: int = 60

    @classmethod
    def from_env(cls) -> "HttpModelClient":
        url = os.environ.get("CONTIG_LLM_URL", "").strip()
        model = os.environ.get("CONTIG_LLM_MODEL", "").strip()
        if not url or not model:
            raise ValueError(
                "no LLM configured: set CONTIG_LLM_URL and CONTIG_LLM_MODEL "
                "(and CONTIG_LLM_API_KEY if required)"
            )
        return cls(url=url, model=model, api_key=os.environ.get("CONTIG_LLM_API_KEY") or None)

    def complete(self, prompt: str) -> str:
        body = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a research-use assistant. Rephrase the grounded answer "
                        "you are given. Do not add facts, clinical claims, diagnoses, or "
                        "new citations. Keep the citation labels unchanged. If the "
                        "grounded answer is a refusal, keep it a refusal."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            self.url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - surface a clear domain error
            raise ValueError(f"LLM request failed: {exc}") from exc
        try:
            return str(payload["choices"][0]["message"]["content"]).strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("LLM response did not contain choices[0].message.content") from exc


VERDICT_TOKENS = ("PASS", "WARN", "FAIL", "UNVERIFIED")
REFUSAL_MARKER = "won't guess"
MIN_LENGTH_RATIO = 0.5


def _preserves_grounding(grounded: str, candidate: str) -> bool:
    """True iff the paraphrase keeps the refusal, verdict, and enough content.

    The model may rephrase only. A changed refusal, a dropped/added verdict
    token, or a heavily truncated answer falls back to the deterministic text.
    This is a fidelity guard, not a semantic judge.
    """
    if (REFUSAL_MARKER in grounded.lower()) != (REFUSAL_MARKER in candidate.lower()):
        return False
    for verdict in VERDICT_TOKENS:
        if (verdict in grounded) != (verdict in candidate):
            return False
    if len(candidate.strip()) < MIN_LENGTH_RATIO * len(grounded.strip()):
        return False
    return True


def paraphrase(answer: Answer, client: ModelClient, question: str) -> Answer:
    citations = "\n".join(
        f"- {citation.label}: {citation.path} (sha256 {citation.sha256})"
        for citation in answer.citations
    ) or "- none"
    prompt = (
        f"Question: {question}\n\n"
        f"Grounded answer:\n{answer.answer}\n\n"
        f"Citations:\n{citations}\n\n"
        "Rephrase the grounded answer only."
    )
    text = client.complete(prompt).strip()
    if not text or not _preserves_grounding(answer.answer, text):
        return answer
    return answer.model_copy(update={"answer": text})

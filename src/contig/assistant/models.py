"""Contracts for the grounded ask-your-run assistant (M5)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Citation(BaseModel):
    label: str
    path: str
    sha256: str
    detail: str = ""


class Answer(BaseModel):
    intent: str
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    confidence: str = "high"
    actions: list[str] = Field(default_factory=list)


class EvalCase(BaseModel):
    question: str
    expected_intent: str
    expected_source_kind: str = ""


class EvalReport(BaseModel):
    total: int
    passed: int
    accuracy: float
    misses: list[dict[str, str]] = Field(default_factory=list)

    def exit_ok(self, threshold: float) -> bool:
        return self.accuracy >= threshold

"""Grounded ask-your-run assistant (M5).

Deterministic answers over a run bundle plus optional M1/M2 tables, with
citations and suggested actions. The LLM is an optional paraphrase layer.
"""

from contig.assistant.models import Answer, Citation, EvalCase, EvalReport

__all__ = ["Answer", "Citation", "EvalCase", "EvalReport"]

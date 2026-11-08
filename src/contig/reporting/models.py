"""Contracts for the research report builder (M4)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Template = Literal["publication", "internal", "audit"]


class Reviewer(BaseModel):
    name: str
    role: str = ""
    reviewed_at: str = ""
    statement: str = "Reviewed for research use."


class ReportSpec(BaseModel):
    title: str | None = None
    subtitle: str | None = None
    author: str | None = None
    institution: str | None = None
    summary: str | None = None
    notes: str | None = None
    limitations: str | None = None
    template: Template = "publication"
    reviewer: Reviewer | None = None
    max_rows: int = 100

    @field_validator("max_rows")
    @classmethod
    def _bounded_rows(cls, value: int) -> int:
        if not 1 <= value <= 10000:
            raise ValueError("must be between 1 and 10000")
        return value


class ReportInput(BaseModel):
    kind: str
    path: str
    sha256: str
    note: str | None = None


class ReportMeta(BaseModel):
    run_id: str
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    contig_version: str = ""
    spec: ReportSpec = Field(default_factory=ReportSpec)
    inputs: list[ReportInput] = Field(default_factory=list)
    html_path: str = ""
    html_sha256: str = ""
    notes: list[str] = Field(default_factory=list)

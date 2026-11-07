"""Contracts for oncology biomarker verification (M7)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class BiomarkerEntry(BaseModel):
    name: str
    value: str = ""
    unit: str = ""
    status: str = "not_verified"
    detail: str = ""


class SourceProvenance(BaseModel):
    kind: str
    path: str
    sha256: str
    note: str | None = None


class BiomarkerMeta(BaseModel):
    sources: list[SourceProvenance] = Field(default_factory=list)
    definition: str = ""
    tolerance: float = 0.20
    msi_threshold: float | None = None
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    contig_version: str = ""
    notes: list[str] = Field(default_factory=list)


@dataclass
class BiomarkerReport:
    entries: list[BiomarkerEntry]
    meta: BiomarkerMeta

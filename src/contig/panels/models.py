"""Contracts for the panel builder and registry (M3)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class PanelSource(BaseModel):
    kind: str
    path: str
    sha256: str
    note: str | None = None


class PanelMeta(BaseModel):
    id: str
    name: str
    build: str
    source: str
    version: str = "1"
    genes: list[str] = Field(default_factory=list)
    transcripts: list[str] = Field(default_factory=list)
    method: str = ""
    checksum: str = ""
    sources: list[PanelSource] = Field(default_factory=list)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    contig_version: str = ""
    notes: list[str] = Field(default_factory=list)


@dataclass
class Panel:
    meta: PanelMeta
    bed_text: str

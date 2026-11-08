"""Contracts for the local cohort frequency layer (M8 v1)."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class CohortVariant(BaseModel):
    chrom: str
    pos: int
    ref: str
    alt: str
    seen_runs: int
    frequency: float
    genes: list[str] = Field(default_factory=list)
    consequences: list[str] = Field(default_factory=list)
    clinvar_significance: list[str] = Field(default_factory=list)
    run_labels: list[str] = Field(default_factory=list)


class GeneSummary(BaseModel):
    gene: str
    variant_count: int
    runs_with_gene: int


class CohortRun(BaseModel):
    label: str
    path: str = ""
    sha256: str


class CohortMeta(BaseModel):
    name: str
    runs: list[CohortRun] = Field(default_factory=list)
    total_runs: int = 0
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    contig_version: str = ""
    anonymized: bool = False
    traced: bool = False
    notes: list[str] = Field(default_factory=list)


class Cohort(BaseModel):
    meta: CohortMeta
    variants: list[CohortVariant] = Field(default_factory=list)
    genes: list[GeneSummary] = Field(default_factory=list)

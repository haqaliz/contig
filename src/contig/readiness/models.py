"""Contracts for the coverage and interpretation-readiness workbench (M2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator, model_validator

ReadinessState = str  # "ready" | "caution" | "not-interpretable"


@dataclass(frozen=True, order=True)
class Target:
    chrom: str
    start: int
    end: int
    name: str
    gene: str = ""
    transcript: str = ""
    exon: str = ""


@dataclass(frozen=True)
class CaveatRegion:
    chrom: str
    start: int
    end: int
    name: str
    reason: str = ""


@dataclass
class TargetMetrics:
    target: Target
    bases: int
    covered_bases: int
    mean_depth: float
    pct_20x: float
    pct_50x: float
    pct_100x: float
    zero_bases: int
    caveats: list[str] = field(default_factory=list)
    readiness: str = "not-interpretable"
    reason: str = ""


class ReadinessThresholds(BaseModel):
    depth_threshold: int = 20
    ready_fraction: float = 0.90
    caution_fraction: float = 0.50

    @field_validator("depth_threshold")
    @classmethod
    def _positive_depth(cls, value: int) -> int:
        if value < 1:
            raise ValueError("must be at least 1")
        return value

    @field_validator("ready_fraction", "caution_fraction")
    @classmethod
    def _unit_interval(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("must be between 0 and 1")
        return value

    @model_validator(mode="after")
    def _ordered_fractions(self) -> "ReadinessThresholds":
        if self.caution_fraction > self.ready_fraction:
            raise ValueError("caution_fraction must be <= ready_fraction")
        return self


class SourceProvenance(BaseModel):
    kind: str
    path: str
    sha256: str
    note: str | None = None


class SampleQC(BaseModel):
    inferred_sex: str
    x_het_ratio: float | None = None
    x_sites: int = 0
    y_variant_count: int = 0
    expected_sex: str | None = None
    sex_concordance: bool | None = None
    possible_swap: bool = False
    note: str = ""


class ReadinessMeta(BaseModel):
    sources: list[SourceProvenance] = Field(default_factory=list)
    thresholds: ReadinessThresholds = Field(default_factory=ReadinessThresholds)
    build: str | None = None
    caveats_checked: bool = False
    caveat_regions: int = 0
    sample_qc: SampleQC | None = None
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    contig_version: str = ""
    notes: list[str] = Field(default_factory=list)


@dataclass
class GeneMetrics:
    gene: str
    targets: int
    bases: int
    covered_bases: int
    mean_depth: float
    pct_20x: float
    pct_50x: float
    pct_100x: float
    zero_bases: int
    caveats: list[str]
    readiness: str
    reason: str


@dataclass
class ReadinessTable:
    rows: list[TargetMetrics]
    meta: ReadinessMeta
    genes: list[GeneMetrics] = field(default_factory=list)

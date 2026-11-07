"""Contracts for the research-use variant workbench (M1).

These are deliberately small, plain data objects. The table is a deterministic
function of the input VCF, the evidence sources, and the filter spec; the meta
object records exactly those inputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator

VALID_ZYGOSITY = {"het", "hom", "hemi"}


@dataclass(frozen=True, order=True)
class VariantKey:
    """A normalized variant site. Chromosomes are compared after normalization."""

    chrom: str
    pos: int
    ref: str
    alt: str


@dataclass
class VariantRecord:
    key: VariantKey
    rsid: str | None = None
    qual: float | None = None
    filter: str = "."
    genotype: str | None = None
    zygosity: str | None = None
    depth: int | None = None
    vaf: float | None = None
    consequence: str | None = None
    impact: str | None = None
    gene: str | None = None
    transcript: str | None = None
    hgvsc: str | None = None
    hgvsp: str | None = None
    clinvar_significance: str | None = None
    clinvar_review_status: str | None = None
    clinvar_condition: str | None = None
    clinvar_variant_type: str | None = None
    clinvar_hgvs: str | None = None
    gnomad_af: float | None = None
    gnomad_an: int | None = None
    iranome_af: float | None = None
    iranome_ac: int | None = None
    iranome_an: int | None = None


@dataclass
class ClinVarEvidence:
    significance: str | None = None
    review_status: str | None = None
    condition: str | None = None
    variant_type: str | None = None
    hgvs: str | None = None


@dataclass
class IranomeEvidence:
    af: float | None = None
    ac: int | None = None
    an: int | None = None


@dataclass
class FrequencyEvidence:
    af: float | None = None
    an: int | None = None


@dataclass
class VcfStats:
    total_records: int = 0
    emitted_rows: int = 0
    skipped_lines: int = 0
    notes: list[str] = field(default_factory=list)


class FilterSpec(BaseModel):
    """Deterministic filters. All populated fields combine with AND."""

    genes: list[str] = Field(default_factory=list)
    consequences: list[str] = Field(default_factory=list)
    max_af: float | None = None
    clinvar_significance: list[str] = Field(default_factory=list)
    pass_only: bool = False
    min_depth: int | None = None
    min_vaf: float | None = None
    zygosity: str | None = None
    region: str | None = None

    @field_validator("max_af", "min_vaf")
    @classmethod
    def _unit_interval(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("must be between 0 and 1")
        return value

    @field_validator("min_depth")
    @classmethod
    def _non_negative(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("must be non-negative")
        return value

    @field_validator("zygosity")
    @classmethod
    def _known_zygosity(cls, value: str | None) -> str | None:
        if value is not None and value not in VALID_ZYGOSITY:
            raise ValueError(f"must be one of {sorted(VALID_ZYGOSITY)}")
        return value

    def merged(self, other: "FilterSpec") -> "FilterSpec":
        """Return `other`'s explicit values over this spec (flags win over --spec)."""
        data = self.model_dump()
        for key, value in other.model_dump().items():
            if value is not None and value != [] and value is not False:
                data[key] = value
        return FilterSpec.model_validate(data)


class SourceProvenance(BaseModel):
    kind: str
    path: str
    sha256: str
    build: str | None = None
    version: str | None = None
    note: str | None = None


class TableMeta(BaseModel):
    sources: list[SourceProvenance] = Field(default_factory=list)
    filters: FilterSpec = Field(default_factory=FilterSpec)
    build: str | None = None
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    contig_version: str = ""
    notes: list[str] = Field(default_factory=list)


@dataclass
class VariantTable:
    rows: list[VariantRecord]
    meta: TableMeta

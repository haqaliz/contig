"""Contracts for the research-use family/trio analysis (M6)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from contig.variants.models import VariantKey


@dataclass(frozen=True)
class FamilyMember:
    sample_id: str
    father_id: str = "0"
    mother_id: str = "0"
    sex: str = "0"
    phenotype: str = "-9"


@dataclass
class Family:
    family_id: str
    members: dict[str, FamilyMember] = field(default_factory=dict)

    @property
    def samples(self) -> list[str]:
        return list(self.members)

    @property
    def children(self) -> list[FamilyMember]:
        return [
            member for member in self.members.values()
            if member.father_id not in ("0", "") and member.mother_id not in ("0", "")
        ]


@dataclass
class FamilyVariant:
    key: VariantKey
    gene: str | None = None
    consequence: str | None = None
    genotypes: dict[str, str | None] = field(default_factory=dict)


@dataclass
class FamilyRow:
    family_id: str
    child: str
    key: VariantKey
    gene: str | None
    consequence: str | None
    child_gt: str | None
    father_gt: str | None
    mother_gt: str | None
    inheritance: str
    mendelian_consistent: bool | None
    de_novo_candidate: bool


class SourceProvenance(BaseModel):
    kind: str
    path: str
    sha256: str
    note: str | None = None


class FamilyMeta(BaseModel):
    family_id: str
    samples: list[str] = Field(default_factory=list)
    sources: list[SourceProvenance] = Field(default_factory=list)
    summary: dict[str, object] = Field(default_factory=dict)
    concordance: list[dict[str, object]] = Field(default_factory=list)
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    contig_version: str = ""
    notes: list[str] = Field(default_factory=list)


@dataclass
class FamilyTable:
    rows: list[FamilyRow]
    meta: FamilyMeta

"""Minimal PED parser for the family/trio analysis."""

from __future__ import annotations

from pathlib import Path

from contig.family.models import Family, FamilyMember


def load_ped(path: str | Path) -> Family:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"PED not found: {path}")

    families: dict[str, Family] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split("\t") if "\t" in stripped else stripped.split()
        if len(fields) < 6:
            raise ValueError(f"PED line needs 6 columns: {stripped}")
        family_id, sample_id, father_id, mother_id, sex, phenotype = fields[:6]
        family = families.setdefault(family_id, Family(family_id=family_id))
        family.members[sample_id] = FamilyMember(
            sample_id=sample_id,
            father_id=father_id,
            mother_id=mother_id,
            sex=sex,
            phenotype=phenotype,
        )

    if not families:
        raise ValueError(f"no PED rows in {path}")
    if len(families) > 1:
        raise ValueError("one family per PED is supported in v1")

    family = next(iter(families.values()))
    if not family.children:
        raise ValueError("PED has no child with both parents")
    for member in family.members.values():
        for parent_id in (member.father_id, member.mother_id):
            if parent_id not in ("0", "") and parent_id not in family.members:
                raise ValueError(f"PED references missing parent {parent_id!r}")
    return family

"""Minimal PED parser for the family/trio analysis."""

from __future__ import annotations

from pathlib import Path

from contig.family.models import Family, FamilyMember


def _parse_families(path: Path) -> list[Family]:
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

    seen_samples: dict[str, str] = {}
    for family in families.values():
        if not family.children:
            raise ValueError(f"family {family.family_id} has no child with both parents")
        for member in family.members.values():
            if member.sample_id in seen_samples:
                raise ValueError(
                    f"sample {member.sample_id!r} appears in multiple families"
                )
            seen_samples[member.sample_id] = family.family_id
            for parent_id in (member.father_id, member.mother_id):
                if parent_id not in ("0", "") and parent_id not in family.members:
                    raise ValueError(
                        f"family {family.family_id} references missing parent "
                        f"{parent_id!r}"
                    )
    return [families[key] for key in sorted(families)]


def load_families(path: str | Path) -> list[Family]:
    """All families in a PED, each validated for children and parents."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"PED not found: {path}")
    return _parse_families(path)


def load_ped(path: str | Path) -> Family:
    """Back-compatible single-family loader.

    Use load_families for a PED with multiple families.
    """
    families = load_families(path)
    if len(families) > 1:
        raise ValueError(
            "load_ped supports one family; use load_families for multiple families"
        )
    return families[0]

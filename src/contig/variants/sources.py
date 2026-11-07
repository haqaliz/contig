"""Evidence-source joins for the variant workbench.

All joins are exact `(chrom, pos, ref, alt)` matches after chromosome-name
normalization. Nothing is inferred; a source that cannot be joined (wrong build,
missing file, zero matches) is recorded honestly in provenance.
"""

from __future__ import annotations

import csv
from pathlib import Path

from contig.models import sha256_file
from contig.variants.models import (
    ClinVarEvidence,
    FrequencyEvidence,
    IranomeEvidence,
    SourceProvenance,
    VariantKey,
)
from contig.variants.vcf import _open_text, _parse_info, normalize_chrom


def _build_from_header(path: str | Path) -> str | None:
    try:
        with _open_text(path) as handle:
            for line in handle:
                if line.startswith("#CHROM"):
                    break
                if not line.startswith("##"):
                    continue
                lowered = line.lower()
                for token, build in (
                    ("grch38", "GRCh38"), ("hg38", "GRCh38"),
                    ("grch37", "GRCh37"), ("hg19", "GRCh37"),
                    ("b37", "GRCh37"), ("g1k_v37", "GRCh37"),
                ):
                    if token in lowered:
                        return build
    except OSError:
        return None
    return None


def infer_build_from_vcf(path: str | Path) -> str | None:
    return _build_from_header(path)


def _header_version(path: str | Path) -> str | None:
    try:
        with _open_text(path) as handle:
            for line in handle:
                if line.startswith("#CHROM"):
                    break
                for prefix in ("##fileDate=", "##version=", "##date="):
                    if line.startswith(prefix):
                        return line.split("=", 1)[1].strip()
    except OSError:
        return None
    return None


def _provenance(kind: str, path: str | Path, build: str | None, note: str, version: str | None = None) -> SourceProvenance:
    return SourceProvenance(
        kind=kind,
        path=str(path),
        sha256=sha256_file(path),
        build=build,
        version=version,
        note=note,
    )


def _key(chrom: str, pos: str | int, ref: str, alt: str) -> VariantKey:
    return VariantKey(normalize_chrom(chrom), int(pos), ref, alt)


def load_clinvar(
    path: str | Path,
    sites: set[VariantKey],
    build: str | None = None,
) -> tuple[dict[VariantKey, ClinVarEvidence], SourceProvenance]:
    """Stream ClinVar and keep only the input sites. First meaningful record wins."""

    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"ClinVar source not found: {path}")
    build = build or infer_build_from_vcf(path)
    evidence: dict[VariantKey, ClinVarEvidence] = {}
    matched = 0

    with _open_text(path) as handle:
        for line in handle:
            if line.startswith("#") or not line.strip():
                continue
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 8:
                continue
            chrom, pos, _id, ref, alt_raw, _qual, _filter, info_raw = fields[:8]
            info = _parse_info(info_raw)
            for alt in alt_raw.split(","):
                key = _key(chrom, pos, ref, alt)
                if key not in sites:
                    continue
                candidate = ClinVarEvidence(
                    significance=info.get("CLNSIG"),
                    review_status=info.get("CLNREVSTAT"),
                    condition=info.get("CLNDN"),
                    variant_type=info.get("CLNVC"),
                    hgvs=info.get("CLNHGVS"),
                )
                existing = evidence.get(key)
                if existing is None or (existing.significance in (None, "not_provided") and candidate.significance not in (None, "not_provided")):
                    evidence[key] = candidate
                    matched += 1

    note = f"{matched} of {len(sites)} input sites matched"
    return evidence, _provenance("clinvar", path, build, note, _header_version(path))


def load_iranome(
    path: str | Path,
    sites: set[VariantKey],
    build: str | None = None,
) -> tuple[dict[VariantKey, IranomeEvidence], SourceProvenance]:
    """Join the Iranome GRCh37 panel. A different build is skipped, never guessed."""

    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Iranome source not found: {path}")
    if build != "GRCh37":
        note = f"skipped: Iranome is GRCh37, input build is {build or 'unknown'}"
        return {}, _provenance("iranome", path, build, note, "Iranome (Fattahi 2019)")

    evidence: dict[VariantKey, IranomeEvidence] = {}
    matched = 0
    with path.open("rt", newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for raw_row in reader:
            if not raw_row:
                continue
            row = {str(key).lower(): value for key, value in raw_row.items() if key}
            try:
                key = _key(row["chrom"], row["pos"], row["ref"], row["alt"])
            except (KeyError, ValueError):
                continue
            if key not in sites:
                continue
            evidence[key] = IranomeEvidence(
                af=_float(row.get("allele_freq")),
                ac=_int(row.get("allele_count")),
                an=_int(row.get("allele_num")),
            )
            matched += 1

    note = f"{matched} of {len(sites)} input sites matched"
    return evidence, _provenance("iranome", path, "GRCh37", note, "Iranome (Fattahi 2019)")


def load_frequencies(
    path: str | Path,
    sites: set[VariantKey],
) -> tuple[dict[VariantKey, FrequencyEvidence], SourceProvenance]:
    """Join a simple frequency TSV: CHROM, POS, REF, ALT, AF[, AN]."""

    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"frequency source not found: {path}")
    evidence: dict[VariantKey, FrequencyEvidence] = {}
    matched = 0
    with path.open("rt", newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise ValueError("frequency source needs a header: CHROM POS REF ALT AF [AN]")
        for raw_row in reader:
            row = {str(key).lower(): value for key, value in raw_row.items() if key}
            try:
                key = _key(row["chrom"], row["pos"], row["ref"], row["alt"])
            except (KeyError, ValueError):
                continue
            if key not in sites:
                continue
            evidence[key] = FrequencyEvidence(
                af=_float(row.get("af")),
                an=_int(row.get("an")),
            )
            matched += 1

    note = f"{matched} of {len(sites)} input sites matched"
    return evidence, _provenance("frequencies", path, None, note)


def _float(value: object) -> float | None:
    if value in (None, "", "."):
        return None
    try:
        result = float(str(value))
    except ValueError:
        return None
    return result if 0.0 <= result <= 1.0 else None


def _int(value: object) -> int | None:
    if value in (None, "", "."):
        return None
    try:
        return int(float(str(value)))
    except ValueError:
        return None

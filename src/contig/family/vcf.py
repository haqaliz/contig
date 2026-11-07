"""Multi-sample VCF reader for the family/trio analysis."""

from __future__ import annotations

from pathlib import Path

from contig.family.models import FamilyVariant
from contig.variants.models import VariantKey, VcfStats
from contig.variants.vcf import (
    DEFAULT_CSQ_FIELDS,
    _annotation,
    _csq_fields,
    _open_text,
    _parse_ann,
    _parse_csq,
    _parse_info,
    _sample_map,
    normalize_chrom,
)


def read_family_variants(path: str | Path, samples: list[str]) -> tuple[list[FamilyVariant], VcfStats]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"VCF not found: {path}")

    stats = VcfStats()
    headers: dict[str, int] = {}
    csq_fields = DEFAULT_CSQ_FIELDS
    variants: list[FamilyVariant] = []

    with _open_text(path) as handle:
        for line in handle:
            if line.startswith("##"):
                if line.startswith("##INFO=<ID=CSQ"):
                    csq_fields = _csq_fields(line)
                continue
            if line.startswith("#CHROM"):
                fields = line.rstrip("\n").split("\t")
                headers = {name: index for index, name in enumerate(fields)}
                missing = [sample for sample in samples if sample not in headers]
                if missing:
                    raise ValueError(f"VCF is missing sample(s): {', '.join(missing)}")
                continue
            if line.startswith("#") or not line.strip():
                continue

            stats.total_records += 1
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 8:
                stats.skipped_lines += 1
                continue
            chrom, pos_raw, _id, ref, alt_raw, _qual, _filter, info_raw = fields[:8]
            try:
                pos = int(pos_raw)
            except ValueError:
                stats.skipped_lines += 1
                continue

            info = _parse_info(info_raw)
            csq = _parse_csq(info.get("CSQ"), csq_fields)
            ann = _parse_ann(info.get("ANN"))
            fmt = fields[8] if len(fields) > 8 else None
            sample_values = {
                sample: _sample_map(fmt, fields[headers[sample]] if headers[sample] < len(fields) else None)
                for sample in samples
            }

            for alt in alt_raw.split(","):
                annotation = _annotation(csq, alt, "csq") or _annotation(ann, alt, "ann") or {}
                variants.append(FamilyVariant(
                    key=VariantKey(normalize_chrom(chrom), pos, ref, alt),
                    gene=annotation.get("gene"),
                    consequence=annotation.get("consequence"),
                    genotypes={sample: values.get("GT") for sample, values in sample_values.items()},
                ))
                stats.emitted_rows += 1

    return variants, stats

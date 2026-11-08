"""Small, stdlib-only VCF reader for the variant workbench.

It deliberately does not try to be a general VCF library: it reads the fields the
workbench needs (sites, genotypes, depth/VAF, VEP CSQ and SnpEff ANN) and leaves
everything else untouched.
"""

from __future__ import annotations

import gzip
import re
from collections.abc import Callable, Iterator
from pathlib import Path

from contig.variants.models import VariantKey, VariantRecord, VcfStats

# VEP Sequence Ontology terms, most severe first. Unknown terms sort last.
CONSEQUENCE_SEVERITY = (
    "transcript_ablation",
    "splice_acceptor_variant",
    "splice_donor_variant",
    "stop_gained",
    "frameshift_variant",
    "stop_lost",
    "start_lost",
    "transcript_amplification",
    "inframe_insertion",
    "inframe_deletion",
    "missense_variant",
    "protein_altering_variant",
    "splice_region_variant",
    "incomplete_terminal_codon_variant",
    "start_retained_variant",
    "stop_retained_variant",
    "synonymous_variant",
    "coding_sequence_variant",
    "mature_miRNA_variant",
    "5_prime_UTR_variant",
    "3_prime_UTR_variant",
    "non_coding_transcript_exon_variant",
    "intron_variant",
    "NMD_transcript_variant",
    "non_coding_transcript_variant",
    "upstream_gene_variant",
    "downstream_gene_variant",
    "TF_binding_site_variant",
    "regulatory_region_variant",
    "intergenic_variant",
)
_CONSEQUENCE_RANK = {term: index for index, term in enumerate(CONSEQUENCE_SEVERITY)}
_IMPACT_RANK = {"HIGH": 0, "MODERATE": 1, "LOW": 2, "MODIFIER": 3}

# Fallback if a VCF declares CSQ but omits the Format string.
DEFAULT_CSQ_FIELDS = [
    "Allele", "Consequence", "IMPACT", "SYMBOL", "Gene", "Feature_type",
    "Feature", "BIOTYPE", "EXON", "INTRON", "HGVSc", "HGVSp",
]
ANN_FIELDS = [
    "Allele", "Annotation", "Annotation_Impact", "Gene_Name", "Gene_ID",
    "Feature_Type", "Feature_ID", "Transcript_BioType", "Rank", "HGVS.c",
    "HGVS.p", "cDNA.pos / cDNA.length", "CDS.pos / CDS.length",
    "AA.pos / AA.length", "Distance", "ERRORS / WARNINGS / INFO",
]


def normalize_chrom(chrom: str) -> str:
    value = chrom.strip()
    if value.lower().startswith("chr"):
        value = value[3:]
    value = value.upper()
    if value in {"M", "MT"}:
        return "MT"
    return value


def _open_text(path: str | Path):
    path = Path(path)
    if path.suffix == ".gz":
        return gzip.open(path, "rt", errors="replace")
    return path.open("rt", errors="replace")


def _parse_info(raw: str) -> dict[str, str]:
    info: dict[str, str] = {}
    for item in raw.split(";"):
        if not item:
            continue
        key, _, value = item.partition("=")
        info.setdefault(key, value)
    return info


def _csq_fields(line: str) -> list[str]:
    match = re.search(r"Format:\s*([^\"]+)", line)
    if not match:
        return DEFAULT_CSQ_FIELDS
    return [name.strip() for name in match.group(1).split("|")]


def _parse_csq(value: str | None, fields: list[str]) -> list[dict[str, str]]:
    if not value:
        return []
    entries = []
    for raw in value.split(","):
        parts = raw.split("|")
        entries.append({name: (parts[i] if i < len(parts) else "") for i, name in enumerate(fields)})
    return entries


def _parse_ann(value: str | None) -> list[dict[str, str]]:
    if not value:
        return []
    entries = []
    for raw in value.split(","):
        parts = raw.split("|")
        entries.append({name: (parts[i] if i < len(parts) else "") for i, name in enumerate(ANN_FIELDS)})
    return entries


def _most_severe(terms: str) -> str | None:
    values = [term for term in terms.split("&") if term]
    if not values:
        return None
    return min(values, key=lambda term: _CONSEQUENCE_RANK.get(term, len(CONSEQUENCE_SEVERITY)))


def _annotation(entries: list[dict[str, str]], alt: str, kind: str) -> dict[str, str] | None:
    matches = [e for e in entries if e.get("Allele") in (alt, "-", "", None)]
    if not matches:
        return None

    def sort_key(entry: dict[str, str]):
        terms = entry.get("Consequence") if kind == "csq" else entry.get("Annotation")
        term = _most_severe(terms or "")
        return (_CONSEQUENCE_RANK.get(term, len(CONSEQUENCE_SEVERITY)), _IMPACT_RANK.get(entry.get("IMPACT") or entry.get("Annotation_Impact") or "", 9))

    entry = min(matches, key=sort_key)
    if kind == "csq":
        consequence = _most_severe(entry.get("Consequence", ""))
        return {
            "consequence": consequence,
            "impact": entry.get("IMPACT") or None,
            "gene": entry.get("SYMBOL") or None,
            "transcript": entry.get("Feature") or None,
            "hgvsc": entry.get("HGVSc") or None,
            "hgvsp": entry.get("HGVSp") or None,
        }
    consequence = _most_severe(entry.get("Annotation", ""))
    return {
        "consequence": consequence,
        "impact": entry.get("Annotation_Impact") or None,
        "gene": entry.get("Gene_Name") or None,
        "transcript": entry.get("Feature_ID") or None,
        "hgvsc": entry.get("HGVS.c") or None,
        "hgvsp": entry.get("HGVS.p") or None,
    }


def _sample_map(fmt: str | None, sample: str | None) -> dict[str, str]:
    if not fmt or sample is None:
        return {}
    keys = fmt.split(":")
    values = sample.split(":")
    return {key: (values[i] if i < len(values) else "") for i, key in enumerate(keys)}


def _zygosity(gt: str | None, chrom: str, alt_index: int) -> str | None:
    if not gt or gt in {".", "./.", ".|."}:
        return None
    alleles = re.split(r"[/|]", gt)
    if any(allele == "." for allele in alleles):
        return None
    if len(alleles) == 1:
        if normalize_chrom(chrom) in {"X", "Y", "MT"} and alleles[0] != "0":
            return "hemi"
        return None
    target = str(alt_index + 1)
    if target not in alleles:
        return None
    return "hom" if all(allele == target for allele in alleles) else "het"


def _int_or_none(value: str | None) -> int | None:
    if value in (None, "", "."):
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _float_value(value: str | None) -> float | None:
    if value in (None, "", "."):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _float_or_none(value: str | None) -> float | None:
    result = _float_value(value)
    return result if result is not None and 0.0 <= result <= 1.0 else None


def _format_value(values: str | None, alt_index: int, count: int) -> float | None:
    if not values or values == ".":
        return None
    parts = values.split(",")
    if len(parts) == count:
        return _float_or_none(parts[alt_index])
    if len(parts) == 1:
        return _float_or_none(parts[0])
    return None


def _depth(sample: dict[str, str], info: dict[str, str]) -> int | None:
    value = sample.get("DP")
    if value and "," in value:
        value = value.split(",")[0]
    return _int_or_none(value) if value else _int_or_none(info.get("DP"))


def _vaf(sample: dict[str, str], info: dict[str, str], alt_index: int, alt_count: int) -> float | None:
    if "AF" in sample:
        value = _format_value(sample.get("AF"), alt_index, alt_count)
        if value is not None:
            return value
    if "AD" in sample:
        parts = sample["AD"].split(",")
        if len(parts) > alt_index + 1:
            ref = _int_or_none(parts[0]) or 0
            alt = _int_or_none(parts[alt_index + 1]) or 0
            total = ref + alt
            if total > 0:
                return alt / total
    if "AF" in info:
        return _format_value(info.get("AF"), alt_index, alt_count)
    return None


def iter_variants(path: str | Path, stats: VcfStats | None = None) -> Iterator[VariantRecord]:
    """Yield one record per ALT allele. Missing annotations are kept, not dropped."""

    stats = stats if stats is not None else VcfStats()
    csq_fields = DEFAULT_CSQ_FIELDS
    sample_index: int | None = None

    with _open_text(path) as handle:
        for line in handle:
            if line.startswith("##"):
                if line.startswith("##INFO=<ID=CSQ"):
                    csq_fields = _csq_fields(line)
                continue
            if line.startswith("#CHROM"):
                header = line.rstrip("\n").split("\t")
                sample_index = 9 if len(header) > 9 else None
                continue
            if line.startswith("#") or not line.strip():
                continue

            stats.total_records += 1
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 8:
                stats.skipped_lines += 1
                continue
            chrom, pos_raw, rsid, ref, alt_raw, qual_raw, filter_raw, info_raw = fields[:8]
            try:
                pos = int(pos_raw)
            except ValueError:
                stats.skipped_lines += 1
                continue

            info = _parse_info(info_raw)
            csq = _parse_csq(info.get("CSQ"), csq_fields)
            ann = _parse_ann(info.get("ANN"))
            fmt = fields[8] if len(fields) > 8 else None
            sample = fields[sample_index] if sample_index is not None and sample_index < len(fields) else None
            sample_values = _sample_map(fmt, sample)
            alts = alt_raw.split(",")
            emitted = 0

            for alt_index, alt in enumerate(alts):
                annotation = _annotation(csq, alt, "csq") or _annotation(ann, alt, "ann")
                emitted += 1
                yield VariantRecord(
                    key=VariantKey(normalize_chrom(chrom), pos, ref, alt),
                    rsid=None if rsid in ("", ".") else rsid,
                    qual=_float_value(qual_raw),
                    filter=filter_raw or ".",
                    genotype=sample_values.get("GT") or None,
                    zygosity=_zygosity(sample_values.get("GT"), chrom, alt_index),
                    depth=_depth(sample_values, info),
                    vaf=_vaf(sample_values, info, alt_index, len(alts)),
                    consequence=(annotation or {}).get("consequence"),
                    impact=(annotation or {}).get("impact"),
                    gene=(annotation or {}).get("gene"),
                    transcript=(annotation or {}).get("transcript"),
                    hgvsc=(annotation or {}).get("hgvsc"),
                    hgvsp=(annotation or {}).get("hgvsp"),
                )
            stats.emitted_rows += emitted


class VariantCapExceeded(ValueError):
    """Raised when a read would keep more records than the explicit cap."""

    def __init__(self, cap: int):
        super().__init__(f"variant table exceeded the {cap:,}-record cap")
        self.cap = cap


def read_variants(
    path: str | Path,
    *,
    keep: Callable[[VariantRecord], bool] | None = None,
    max_records: int | None = None,
) -> tuple[list[VariantRecord], VcfStats]:
    """Read a VCF, optionally keeping only matching records up to a cap.

    ``keep`` is applied while streaming, so a region/gene query never holds the
    whole WGS call set in memory. The cap counts KEPT rows; exceeding it raises
    rather than returning a silently truncated table.
    """
    stats = VcfStats()
    rows: list[VariantRecord] = []
    for record in iter_variants(path, stats):
        if keep is not None and not keep(record):
            continue
        if max_records is not None and len(rows) >= max_records:
            raise VariantCapExceeded(max_records)
        rows.append(record)
    return rows, stats

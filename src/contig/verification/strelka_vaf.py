"""Strelka2 tier-count VAF parser (SNV AU/CU/GU/TU, indel TAR/TIR).

Strelka2 does not emit an ``AF`` or ``AD`` FORMAT field the way Mutect2 does.
Instead it reports per-base tier-1/tier-2 read counts for SNVs (``AU``, ``CU``,
``GU``, ``TU``, each a ``tier1,tier2`` pair) and ref/alt tier counts for indels
(``TAR``, ``TIR``, also ``tier1,tier2``). Strelka2's own documented tumor allele
fraction is a tier1-only ratio:

- SNV: ``VAF = tier1({ALT}U) / (tier1({REF}U) + tier1({ALT}U))``
- indel: ``VAF = tier1(TIR) / (tier1(TAR) + tier1(TIR))``

This module is a pure, stdlib, streaming parser of that ratio from the
``TUMOR`` sample column only (never a positional guess -- the column must be
literally named ``TUMOR`` on the ``#CHROM`` line, mirroring the "never guess"
discipline of somatic_plausibility._tumor_column_index, though that sibling
resolves by a ``##tumor_sample=`` header name rather than a literal column
name). It has no verdict/gate coupling; it only turns SNV+indel VCFs into a
pooled list of per-record tumor VAFs and a pooled median.
"""

from __future__ import annotations

import gzip
import os
import statistics
from pathlib import Path

from contig.models import QCResult
from contig.verification.rule_pack import SOMATIC_PLAUSIBILITY_PACK, evaluate

_ACGT = frozenset("ACGT")


def _open_text(path: str | os.PathLike):
    """Open a VCF for text reading, transparently gunzipping a `.gz` path."""
    p = Path(path)
    if p.name.endswith(".gz"):
        return gzip.open(p, "rt")
    return open(p)


def _tumor_column_index(header_lines: list[str]) -> int | None:
    """Find the column literally named ``TUMOR`` on the ``#CHROM`` line.

    Returns its index (>= 9) or None if the ``#CHROM`` line is absent or has no
    column literally named ``TUMOR``. Never a positional guess.
    """
    chrom_cols: list[str] | None = None
    for line in header_lines:
        if line.startswith("#CHROM"):
            chrom_cols = line.rstrip("\n").split("\t")
            break
    if chrom_cols is None:
        return None
    for idx in range(9, len(chrom_cols)):
        if chrom_cols[idx] == "TUMOR":
            return idx
    return None


def _tier1(field: str) -> int | None:
    """Parse the first comma-token of a tier-count field as int, or None."""
    raw = field.split(",")[0]
    try:
        return int(raw)
    except ValueError:
        return None


def _snv_vaf(
    fmt_keys: list[str], sample_fields: list[str], ref: str, alt: str
) -> float | None:
    """Derive a tumor VAF from an SNV record's base-count tier fields.

    Maps REF/ALT bases to their ``{base}U`` FORMAT key, reads each field's
    tier1 count, and returns altCount / (refCount + altCount). None when
    either key/field is absent, malformed, or the denominator is 0.
    """
    if ref not in _ACGT or alt not in _ACGT:
        return None
    keys = {k: i for i, k in enumerate(fmt_keys)}

    ref_idx = keys.get(f"{ref}U")
    alt_idx = keys.get(f"{alt}U")
    if ref_idx is None or alt_idx is None:
        return None
    if ref_idx >= len(sample_fields) or alt_idx >= len(sample_fields):
        return None

    ref_count = _tier1(sample_fields[ref_idx])
    alt_count = _tier1(sample_fields[alt_idx])
    if ref_count is None or alt_count is None:
        return None

    denom = ref_count + alt_count
    if denom <= 0:
        return None
    return alt_count / denom


def _indel_vaf(fmt_keys: list[str], sample_fields: list[str]) -> float | None:
    """Derive a tumor VAF from an indel record's TAR/TIR tier fields.

    Returns tier1(TIR) / (tier1(TAR) + tier1(TIR)), or None when either
    key/field is absent, malformed, or the denominator is 0.
    """
    keys = {k: i for i, k in enumerate(fmt_keys)}

    tar_idx = keys.get("TAR")
    tir_idx = keys.get("TIR")
    if tar_idx is None or tir_idx is None:
        return None
    if tar_idx >= len(sample_fields) or tir_idx >= len(sample_fields):
        return None

    tar_count = _tier1(sample_fields[tar_idx])
    tir_count = _tier1(sample_fields[tir_idx])
    if tar_count is None or tir_count is None:
        return None

    denom = tar_count + tir_count
    if denom <= 0:
        return None
    return tir_count / denom


def _read_one(vcf_path: str | os.PathLike, *, is_indel: bool) -> tuple[list[float], bool]:
    """Stream one Strelka2 VCF; return (tumor VAFs, whether TUMOR col found)."""
    header_lines: list[str] = []
    tumor_idx: int | None = None
    resolved = False
    vafs: list[float] = []

    with _open_text(vcf_path) as fh:
        for line in fh:
            if line.startswith("#"):
                header_lines.append(line)
                if line.startswith("#CHROM"):
                    tumor_idx = _tumor_column_index(header_lines)
                    resolved = True
                continue
            if not resolved:
                tumor_idx = _tumor_column_index(header_lines)
                resolved = True
            if tumor_idx is None:
                continue
            line = line.rstrip("\n")
            if not line:
                continue
            cols = line.split("\t")
            if len(cols) < 9 or tumor_idx >= len(cols):
                continue
            ref, alt = cols[3], cols[4]
            if "," in alt:
                continue
            fmt_keys = cols[8].split(":")
            sample_fields = cols[tumor_idx].split(":")
            if is_indel:
                vaf = _indel_vaf(fmt_keys, sample_fields)
            else:
                vaf = _snv_vaf(fmt_keys, sample_fields, ref, alt)
            if vaf is not None:
                vafs.append(vaf)

    return vafs, tumor_idx is not None


def read_strelka_vafs(
    snv_path: str | os.PathLike | None = None,
    indel_path: str | os.PathLike | None = None,
) -> tuple[list[float], bool]:
    """Stream the provided Strelka2 SNV/indel VCFs into a pooled tumor VAF list.

    Each provided file is read independently; a file whose ``TUMOR`` column is
    absent contributes no VAFs. Returns (pooled VAFs, whether a ``TUMOR``
    column was found in any read file).
    """
    vafs: list[float] = []
    tumor_found = False

    if snv_path is not None:
        snv_vafs, snv_tumor_found = _read_one(snv_path, is_indel=False)
        vafs.extend(snv_vafs)
        tumor_found = tumor_found or snv_tumor_found

    if indel_path is not None:
        indel_vafs, indel_tumor_found = _read_one(indel_path, is_indel=True)
        vafs.extend(indel_vafs)
        tumor_found = tumor_found or indel_tumor_found

    return vafs, tumor_found


def strelka_median_vaf(
    snv_path: str | os.PathLike | None = None,
    indel_path: str | os.PathLike | None = None,
) -> tuple[float | None, bool]:
    """Pooled median tumor VAF across the provided Strelka2 SNV/indel VCFs.

    None when no record yielded a VAF. Also returns the ``tumor_found`` flag
    from read_strelka_vafs().
    """
    vafs, tumor_found = read_strelka_vafs(snv_path=snv_path, indel_path=indel_path)
    median = statistics.median(vafs) if vafs else None
    return median, tumor_found


def evaluate_strelka_vaf_plausibility(
    snv_vcf: str | os.PathLike | None = None,
    indel_vcf: str | os.PathLike | None = None,
    sample: str | None = None,
) -> list[QCResult]:
    """Evaluate the Strelka2 tumor-VAF plausibility rule, capped at WARN.

    Computes the pooled ``strelka_median_vaf`` (see ``strelka_median_vaf``), then
    runs it through the shared ``rule_pack.evaluate()`` against
    ``SOMATIC_PLAUSIBILITY_PACK`` -- the same pack the Mutect2
    ``evaluate_somatic_plausibility`` uses -- so band logic and
    "<check>:<sample>" naming stay single-sourced across both callers.

    ``evaluate()`` skips any rule whose metric key is absent from the sample
    dict it is given (see rule_pack.evaluate), so the ``by_metric`` dict passed
    here contains ONLY ``strelka_median_vaf``. That means this call emits
    exactly the ``strelka_median_vaf`` rule and never re-emits Mutect2's
    ``median_vaf``/``somatic_variant_count`` rules, even though all three share
    ``SOMATIC_PLAUSIBILITY_PACK``.

    A ``None`` median (no derivable tumor VAF -- e.g. no literal ``TUMOR``
    column found, or no record yielded a usable tier-count ratio) is not
    silently skipped: it produces one explicit "unverified" QCResult (no
    severity, so it can never read as a pass), mirroring
    ``evaluate_somatic_plausibility``'s None-handling loop.

    Every emitted message names Strelka2 as the source caller (PRD S1), so the
    verdict surface can tell this metric apart from the Mutect2 ``median_vaf``
    metric even though both check tumor VAF plausibility.

    The sample label is ``sample`` if given, else the literal ``TUMOR`` column
    name when one was found in either VCF, else ``"sample"``.
    """
    median, tumor_found = strelka_median_vaf(snv_vcf, indel_vcf)
    label = sample or ("TUMOR" if tumor_found else None) or "sample"

    by_metric = {"strelka_median_vaf": median}
    computable = {
        metric: value for metric, value in by_metric.items() if value is not None
    }

    results = [
        result.model_copy(update={"message": f"Strelka2: {result.message}"})
        for result in evaluate({label: computable}, SOMATIC_PLAUSIBILITY_PACK)
    ]

    if median is None:
        results.append(
            QCResult(
                check=f"strelka_median_vaf:{label}",
                status="unverified",
                message=(
                    f"Strelka2: {label}: strelka_median_vaf could not be computed "
                    "(no derivable tumor VAF)"
                ),
                value=None,
                kind="metric",
            )
        )

    return results

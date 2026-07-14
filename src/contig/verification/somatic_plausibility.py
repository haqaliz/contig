"""Deterministic somatic VAF-distribution plausibility from a tumor-normal VCF.

Somatic (tumor-normal) variant calling ships structural-only verification today.
This module adds a biological-plausibility axis for the somatic verdict, mirroring
the germline C3 slice (variant_metrics.py): a pure function of the VCF bytes, a
WARN-capped rule pack, and an explicit UNVERIFIED branch whenever a metric cannot
be computed (never a false pass).

The tumor sample is identified honestly from Mutect2's ``##tumor_sample=<name>``
header, mapped to that name's column on the ``#CHROM`` line. If the tumor sample
cannot be identified, no VAFs are read (a guessed column is never used) and the
metric degrades to UNVERIFIED downstream.

Per-record tumor VAF is the FORMAT ``AF`` field (Mutect2 allele fraction, first
comma value) when present; else ``AD_alt / DP`` (the second AD value over DP,
guarding DP==0); else the record contributes no VAF. VAF is computed on biallelic
records only (a comma in ALT is excluded); indels are included (VAF is an
allele-fraction, not an SNV-only metric).

This module carries its own small VCF pass; it deliberately does not reuse
concordance.parse_vcf / _genotype_from_columns (those read only GT of the first
sample column and are load-bearing for the concordance feature).
"""

from __future__ import annotations

import gzip
import os
import statistics
from dataclasses import dataclass
from pathlib import Path

from contig.models import QCResult
from contig.verification.rule_pack import SOMATIC_PLAUSIBILITY_PACK, evaluate


@dataclass(frozen=True)
class SomaticMetrics:
    """The deterministic metrics computed from a somatic VCF's tumor column.

    - median_vaf: median tumor variant allele fraction over records that yielded a
      VAF, or None when none did (no AF, no usable AD/DP, or tumor unidentifiable).
      For an even count this is the mean of the two central values (stdlib median).
    - variant_count: number of considered (biallelic) variant records.
    """

    median_vaf: float | None
    variant_count: int


def _open_text(path: str | os.PathLike):
    """Open a VCF for text reading, transparently gunzipping a `.gz` path."""
    p = Path(path)
    if p.name.endswith(".gz"):
        return gzip.open(p, "rt")
    return open(p)


def _tumor_column_index(header_lines: list[str]) -> int | None:
    """Find the tumor sample's column index from the VCF header.

    Reads ``##tumor_sample=<name>`` then locates <name> among the sample columns
    of the ``#CHROM`` line (index >= 9). Returns None if either the header line or
    the name's column is absent (never guess a column).
    """
    tumor_name: str | None = None
    chrom_cols: list[str] | None = None
    for line in header_lines:
        if line.startswith("##tumor_sample="):
            tumor_name = line[len("##tumor_sample="):].strip()
        elif line.startswith("#CHROM"):
            chrom_cols = line.rstrip("\n").split("\t")
    if tumor_name is None or chrom_cols is None:
        return None
    for idx in range(9, len(chrom_cols)):
        if chrom_cols[idx] == tumor_name:
            return idx
    return None


def _normal_column_index(header_lines: list[str]) -> int | None:
    """Find the normal sample's column index from the VCF header.

    Reads ``##normal_sample=<name>`` then locates <name> among the sample
    columns of the ``#CHROM`` line (index >= 9). Returns None if either the
    header line or the name's column is absent (never guess a column).
    """
    normal_name: str | None = None
    chrom_cols: list[str] | None = None
    for line in header_lines:
        if line.startswith("##normal_sample="):
            normal_name = line[len("##normal_sample="):].strip()
        elif line.startswith("#CHROM"):
            chrom_cols = line.rstrip("\n").split("\t")
    if normal_name is None or chrom_cols is None:
        return None
    for idx in range(9, len(chrom_cols)):
        if chrom_cols[idx] == normal_name:
            return idx
    return None


def _biallelic(ref: str, alt: str) -> bool:
    """True for a biallelic record (no comma in ALT); indels allowed."""
    return "," not in alt


def _vaf_from_sample(fmt_keys: list[str], sample_fields: list[str]) -> float | None:
    """Derive a tumor VAF from one sample's FORMAT fields, or None.

    Prefers FORMAT ``AF`` (first comma-split value). Falls back to ``AD_alt / DP``
    (second AD value over DP) when DP > 0. Any missing/malformed field yields None
    (never crash).
    """
    keys = {k: i for i, k in enumerate(fmt_keys)}

    af_idx = keys.get("AF")
    if af_idx is not None and af_idx < len(sample_fields):
        raw = sample_fields[af_idx].split(",")[0]
        try:
            return float(raw)
        except ValueError:
            pass

    ad_idx = keys.get("AD")
    dp_idx = keys.get("DP")
    if (
        ad_idx is not None
        and dp_idx is not None
        and ad_idx < len(sample_fields)
        and dp_idx < len(sample_fields)
    ):
        try:
            ad_parts = sample_fields[ad_idx].split(",")
            alt_depth = float(ad_parts[1])
            dp = float(sample_fields[dp_idx])
        except (ValueError, IndexError):
            return None
        if dp > 0:
            return alt_depth / dp
    return None


def _read_somatic(vcf_path: str | os.PathLike) -> tuple[list[float], int, int | None]:
    """Stream a somatic VCF; return (tumor VAFs, considered count, tumor col index).

    Header lines are captured up to and including ``#CHROM`` to resolve the tumor
    column. Considered records are biallelic data records; each contributes a VAF
    when the tumor field yields one.
    """
    header_lines: list[str] = []
    tumor_idx: int | None = None
    resolved = False
    vafs: list[float] = []
    count = 0

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
            line = line.rstrip("\n")
            if not line:
                continue
            cols = line.split("\t")
            if len(cols) < 5:
                continue
            ref, alt = cols[3], cols[4]
            if not _biallelic(ref, alt):
                continue
            count += 1
            if tumor_idx is None or len(cols) < 9 or tumor_idx >= len(cols):
                continue
            fmt_keys = cols[8].split(":")
            sample_fields = cols[tumor_idx].split(":")
            vaf = _vaf_from_sample(fmt_keys, sample_fields)
            if vaf is not None:
                vafs.append(vaf)
    return vafs, count, tumor_idx


def _read_normal(vcf_path: str | os.PathLike) -> tuple[list[float], int, int | None]:
    """Stream a somatic VCF; return (normal VAFs, considered count, normal col index).

    Mirrors ``_read_somatic`` exactly, but resolves the NORMAL column via
    ``_normal_column_index`` (``##normal_sample=``) instead of the tumor's
    ``##tumor_sample=``. Kept as its own streaming pass -- rather than a
    shared helper -- so the shipped tumor path (``_read_somatic``) stays
    byte-identical.
    """
    header_lines: list[str] = []
    normal_idx: int | None = None
    resolved = False
    vafs: list[float] = []
    count = 0

    with _open_text(vcf_path) as fh:
        for line in fh:
            if line.startswith("#"):
                header_lines.append(line)
                if line.startswith("#CHROM"):
                    normal_idx = _normal_column_index(header_lines)
                    resolved = True
                continue
            if not resolved:
                normal_idx = _normal_column_index(header_lines)
                resolved = True
            line = line.rstrip("\n")
            if not line:
                continue
            cols = line.split("\t")
            if len(cols) < 5:
                continue
            ref, alt = cols[3], cols[4]
            if not _biallelic(ref, alt):
                continue
            count += 1
            if normal_idx is None or len(cols) < 9 or normal_idx >= len(cols):
                continue
            fmt_keys = cols[8].split(":")
            sample_fields = cols[normal_idx].split(":")
            vaf = _vaf_from_sample(fmt_keys, sample_fields)
            if vaf is not None:
                vafs.append(vaf)
    return vafs, count, normal_idx


def normal_median_vaf(
    vcf_path: str | os.PathLike,
) -> tuple[float | None, str | None]:
    """Median VAF over the normal column, and the resolved normal sample name.

    Uses the same biallelic record set and the same ``_vaf_from_sample``
    derivation (FORMAT ``AF``, else ``AD_alt / DP``) as the tumor
    ``somatic_metrics``, just read from the NORMAL column instead. median is
    None when no record yielded a normal VAF (including an unidentifiable
    normal column). The name is the ``##normal_sample=`` header value when
    the column resolved, else None (never a guessed label).
    """
    vafs, _count, normal_idx = _read_normal(vcf_path)
    median = statistics.median(vafs) if vafs else None
    header_lines = _header_lines(vcf_path)
    name = _normal_sample_name(header_lines) if normal_idx is not None else None
    return median, name


def somatic_metrics(vcf_path: str | os.PathLike) -> SomaticMetrics:
    """Compute median_vaf and variant_count from a somatic VCF's tumor column.

    Deterministic and side effect free beyond reading the file (gzip transparent).
    median_vaf is None when no record yielded a VAF (including an unidentifiable
    tumor column).
    """
    vafs, count, _tumor_idx = _read_somatic(vcf_path)
    median_vaf = statistics.median(vafs) if vafs else None
    return SomaticMetrics(median_vaf=median_vaf, variant_count=count)


def _header_lines(vcf_path: str | os.PathLike) -> list[str]:
    """Read the VCF header lines (up to and including ``#CHROM``)."""
    lines: list[str] = []
    with _open_text(vcf_path) as fh:
        for line in fh:
            if not line.startswith("#"):
                break
            lines.append(line)
            if line.startswith("#CHROM"):
                break
    return lines


def _tumor_sample_name(header_lines: list[str]) -> str | None:
    """Return the ``##tumor_sample=`` name, or None if the header is absent."""
    for line in header_lines:
        if line.startswith("##tumor_sample="):
            return line[len("##tumor_sample="):].strip()
    return None


def _normal_sample_name(header_lines: list[str]) -> str | None:
    """Return the ``##normal_sample=`` name, or None if the header is absent."""
    for line in header_lines:
        if line.startswith("##normal_sample="):
            return line[len("##normal_sample="):].strip()
    return None


def _pon_status(header_lines: list[str]) -> tuple[str, str]:
    """Panel-of-normals presence, decided from the GATK command header.

    Returns (status, message):
    - no line mentioning ``GATKCommandLine`` -> "unverified" (a stripped/re-headed
      VCF, or a non-Mutect2 file: we cannot tell, never a false pass);
    - a GATK command line present WITH ``--panel-of-normals`` / ``--pon`` -> "pass";
    - a GATK command line present WITHOUT either -> "warn".
    """
    gatk_lines = [line for line in header_lines if "GATKCommandLine" in line]
    if not gatk_lines:
        return (
            "unverified",
            "no Mutect2 (GATK) command header found to assess panel-of-normals use",
        )
    if any(
        "--panel-of-normals" in line or "--pon" in line for line in gatk_lines
    ):
        return ("pass", "panel-of-normals applied per the Mutect2 command header")
    return (
        "warn",
        "no panel-of-normals argument in the Mutect2 command header",
    )


def evaluate_somatic_plausibility(
    vcf_path: str | os.PathLike, sample: str | None = None
) -> list[QCResult]:
    """Evaluate the somatic plausibility rules over a VCF, capped at WARN.

    Computes median_vaf and somatic_variant_count from the tumor column, then runs
    the WARN-capped SOMATIC_PLAUSIBILITY_PACK over the COMPUTABLE metrics via the
    shared evaluate() (band logic and "<check>:<sample>" naming stay single-sourced).
    A None median_vaf is NOT silently skipped: it gets an explicit "unverified"
    QCResult (no severity, so it can never read as a pass). variant_count is always
    an int, so it is always computable. It also appends a ``pon_applied`` check
    decided from the Mutect2 (GATK) command header. Every result is kind "metric".

    The sample label is the resolved tumor sample name (from the header), or
    "sample" when the tumor cannot be identified.
    """
    metrics = somatic_metrics(vcf_path)
    header_lines = _header_lines(vcf_path)
    label = sample or _tumor_sample_name(header_lines) or "sample"

    by_metric = {
        "median_vaf": metrics.median_vaf,
        "somatic_variant_count": metrics.variant_count,
    }
    computable = {
        metric: value for metric, value in by_metric.items() if value is not None
    }

    results = evaluate({label: computable}, SOMATIC_PLAUSIBILITY_PACK)

    for rule in SOMATIC_PLAUSIBILITY_PACK:
        metric = rule["metric"]
        # SOMATIC_PLAUSIBILITY_PACK is shared with the Strelka2 evaluator
        # (strelka_vaf.evaluate_strelka_vaf_plausibility), whose
        # strelka_median_vaf rule this evaluator does not track in by_metric --
        # skip any rule this evaluator has no metric for, rather than KeyError
        # or (worse) emitting a spurious unverified check for a metric it never
        # attempted to compute.
        if metric not in by_metric:
            continue
        if by_metric[metric] is None:
            results.append(
                QCResult(
                    check=f"{rule['check']}:{label}",
                    status="unverified",
                    message=(
                        f"{label}: {metric} could not be computed "
                        "(no derivable tumor VAF)"
                    ),
                    value=None,
                    kind="metric",
                )
            )

    pon_status, pon_message = _pon_status(header_lines)
    results.append(
        QCResult(
            check="pon_applied",
            status=pon_status,
            message=pon_message,
            value=None,
            kind="metric",
        )
    )

    return results


def evaluate_swap_plausibility(
    vcf_path: str | os.PathLike, sample: str | None = None
) -> list[QCResult]:
    """Evaluate the normal-column swap plausibility rule, capped at WARN.

    Computes the ``normal_median_vaf`` (see ``normal_median_vaf``) over the
    NORMAL column of the Mutect2 somatic VCF, then runs it through the shared
    ``rule_pack.evaluate()`` against ``SOMATIC_PLAUSIBILITY_PACK`` -- the same
    pack the tumor ``evaluate_somatic_plausibility`` and Strelka2
    ``evaluate_strelka_vaf_plausibility`` use -- so band logic and
    "<check>:<sample>" naming stay single-sourced across all three callers.

    ``evaluate()`` skips any rule whose metric key is absent from the sample
    dict it is given (see rule_pack.evaluate), so the ``by_metric`` dict
    passed here contains ONLY ``normal_median_vaf``. That means this call
    emits exactly the ``normal_median_vaf`` rule and never re-emits
    ``median_vaf``/``somatic_variant_count``/``strelka_median_vaf``, even
    though all four share ``SOMATIC_PLAUSIBILITY_PACK``.

    A correctly-paired normal has ~0 VAF at somatic sites; an implausibly
    high normal VAF means the somatic signal is in the normal -- a
    tumor/normal swap, a mislabel, or heavy contamination. ``evaluate()``
    builds its own message from the pack's "check"/"metric"/"status" fields
    and ignores the pack's "message" field, so the swap/mislabel/
    contamination framing is added here by wrapping each returned result's
    message, mirroring ``evaluate_strelka_vaf_plausibility``'s "Strelka2: "
    prefix.

    A ``None`` median (no ``##normal_sample=`` header, the named sample not
    among the ``#CHROM`` columns, or no record yielding a usable normal
    FORMAT) is not silently skipped: it produces one explicit "unverified"
    QCResult (no severity, so it can never read as a pass), mirroring
    ``evaluate_somatic_plausibility``'s and
    ``evaluate_strelka_vaf_plausibility``'s None-handling.

    The sample label is ``sample`` if given, else the resolved
    ``##normal_sample=`` name, else ``"sample"``.
    """
    median, normal_name = normal_median_vaf(vcf_path)
    label = sample or normal_name or "sample"

    by_metric = {"normal_median_vaf": median}
    computable = {
        metric: value for metric, value in by_metric.items() if value is not None
    }

    results = [
        result.model_copy(
            update={
                "message": (
                    "normal-sample VAF (high => possible tumor/normal swap, "
                    f"mislabel, or contamination): {result.message}"
                )
            }
        )
        for result in evaluate({label: computable}, SOMATIC_PLAUSIBILITY_PACK)
    ]

    if median is None:
        results.append(
            QCResult(
                check=f"normal_median_vaf:{label}",
                status="unverified",
                message=(
                    f"{label}: normal_median_vaf could not be computed "
                    "(no normal column found, or no derivable normal VAF)"
                ),
                value=None,
                kind="metric",
            )
        )

    return results

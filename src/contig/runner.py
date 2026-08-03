"""Drives the workflow manager in the data plane (ARCHITECTURE §3, §4.2).

For the P0 spike this is just the command builder: it turns a job spec into the
exact Nextflow argv, wiring `-with-trace` so the run is machine-readable and
captured (feeds contig.events ingestion). Actual subprocess execution + RunRecord
assembly is layered on once the toolchain (Nextflow/Docker) is present.
"""

from __future__ import annotations

import json
import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import BinaryIO, Callable


logger = logging.getLogger(__name__)


def _contig_version() -> str | None:
    """Contig's installed version, or None in a non-installed (raw PYTHONPATH) setup."""
    try:
        return _pkg_version("contig")
    except PackageNotFoundError:
        return None

from contig.bundle import compute_input_checksums, write_bundle
from contig.events import parse_trace_file
from contig.models import ExecutionTarget, QCResult, RunRecord, TaskEvent
from contig.nfconfig import generate_nextflow_config
from contig.registry import VARIANT_ASSAYS
from contig.snakemake import build_snakemake_command, parse_snakemake_stats_file
from contig.stall import (
    Heartbeat,
    HeartbeatObserver,
    changed,
    evaluate_stall,
    observe_with_deadline,
    read_heartbeat,
    stall_message,
)
from contig.verification.ampliseq_metrics import parse_asv_table, parse_dada2_overall_summary
from contig.verification.annotation_concordance import (
    evaluate_annotation_concordance_from_run,
)
from contig.verification.mag_metrics import parse_checkm_summary, parse_quast_report
from contig.verification.methylseq_metrics import (
    parse_bismark_alignment_report,
    parse_bismark_conversion_report,
    parse_bismark_dedup_report,
)
from contig.verification.qc_ingest import parse_multiqc_general_stats_file
from contig.verification.rnaseq_metrics import parse_read_distribution
from contig.verification.rnaseq_plausibility import evaluate_rnaseq_plausibility
from contig.verification.rule_pack import (
    AMPLISEQ_RULE_PACK,
    MAG_RULE_PACK,
    METHYLSEQ_RULE_PACK,
    RNASEQ_COMPOSITION_PACK,
    SCRNASEQ_RULE_PACK,
    evaluate,
    rule_pack_for,
)
from contig.verification.scrnaseq_metrics import (
    parse_cellranger_metrics,
    parse_starsolo_summary,
)
from contig.verification.somatic_concordance import (
    evaluate_somatic_concordance_from_run,
    select_caller_vcfs,
)
from contig.verification.somatic_plausibility import (
    evaluate_somatic_plausibility,
    evaluate_swap_plausibility,
)
from contig.verification.strelka_vaf import evaluate_strelka_vaf_plausibility
from contig.verification.run_qc import evaluate_run_qc
from contig.verification.sex_plausibility import evaluate_sex_plausibility
from contig.verification.structural import evaluate_structural, manifest_for
from contig.verification.variant_metrics import evaluate_variant_plausibility


# Assays whose biological metrics come from a dedicated on-disk gate below, NOT
# from MultiQC general-stats. The generic pack path skips them so a metric can
# never be emitted twice if a future MultiQC ever carried a matching slug.
_DEDICATED_METRIC_ASSAYS = {"methylseq", "ampliseq", "mag"}

# STARsolo writes a Summary.csv under each metric subdir (Gene/, GeneFull/, ...);
# the enclosing dir named "<sample>.Solo.out" carries the sample id. These are the
# STARsolo internal dir names to skip when falling back to a plain ancestor name.
_STARSOLO_INTERNAL = {
    "Gene",
    "GeneFull",
    "GeneFull_Ex50pAS",
    "GeneFull_ExonOverIntron",
    "Velocyto",
    "Solo.out",
    "raw",
    "filtered",
}


def _sample_from_starsolo(path: Path) -> str:
    """Derive the sample id from a STARsolo Summary.csv path.

    Prefers the `<sample>.Solo.out` ancestor (strip the suffix); otherwise the
    nearest ancestor that is not a STARsolo internal directory.
    """
    for parent in path.parents:
        if parent.name.endswith(".Solo.out"):
            return parent.name[: -len(".Solo.out")]
    for parent in path.parents:
        if parent.name and parent.name not in _STARSOLO_INTERNAL:
            return parent.name
    return path.stem


def _sample_from_cellranger(path: Path) -> str:
    """Derive the sample id from a Cell Ranger metrics_summary.csv path.

    Cell Ranger writes `<sample>/outs/metrics_summary.csv`, so the sample is the
    directory above `outs`.
    """
    parent = path.parent
    if parent.name == "outs":
        return parent.parent.name
    return parent.name


def _locate_scrnaseq_qc(run_dir: Path) -> dict[str, dict[str, float]]:
    """Find single-cell cell-QC artifacts under a run dir → {sample: {slug: value}}.

    Cell Ranger takes deterministic precedence over STARsolo for the same sample
    (no merge of two aligners' numbers). A located-but-unparseable file maps the
    sample to an empty dict so the gate can emit an explicit UNVERIFIED. The
    default simpleaf/alevin-fry path has no machine-readable artifact, so it
    contributes nothing here (→ the sample is simply absent).
    """
    located: dict[str, dict[str, float]] = {}
    for path in sorted(run_dir.rglob("metrics_summary.csv")):
        located[_sample_from_cellranger(path)] = parse_cellranger_metrics(path)
    for path in sorted(run_dir.rglob("Summary.csv")):
        sample = _sample_from_starsolo(path)
        if sample in located:
            continue  # Cell Ranger already won this sample, or an earlier Summary.csv
        located[sample] = parse_starsolo_summary(path)
    return located


# Bismark report filename suffixes, most specific first. `_sample_from_bismark`
# strips the first pattern that matches so nf-core's fully-qualified aligner
# names (`_bismark_bt2_PE_report.txt`) and a plainer `_splitting_report.txt`
# both resolve to the same sample id.
_BISMARK_SUFFIX_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"_bismark_[^_]+_(?:PE|SE)_report\.txt$", re.IGNORECASE),
    re.compile(r"_bismark_[^_]+_(?:pe|se)\.deduplication_report\.txt$", re.IGNORECASE),
    re.compile(r"\.?deduplication_report\.txt$", re.IGNORECASE),
    re.compile(
        r"_bismark_[^_]+_(?:pe|se)\.deduplicated_splitting_report\.txt$",
        re.IGNORECASE,
    ),
    re.compile(r"_splitting_report\.txt$", re.IGNORECASE),
]


def _sample_from_bismark(path: Path) -> str:
    """Derive the sample id from a Bismark report path by stripping the
    recognized report-kind suffix off the filename (mirrors
    `_sample_from_starsolo`/`_sample_from_cellranger` above)."""
    name = path.name
    for pattern in _BISMARK_SUFFIX_PATTERNS:
        stripped = pattern.sub("", name)
        if stripped != name:
            return stripped
    return path.stem


def _locate_methylseq_qc(run_dir: Path) -> dict[str, dict[str, float]]:
    """Find Bismark bisulfite-QC report artifacts under a run dir ->
    {sample: {slug: value}}.

    Alignment, deduplication, and splitting/conversion reports for the SAME
    sample are MERGED into one metric dict (M3) rather than overwritten, so a
    sample with only a subset of report kinds keeps whatever parsed. A sample
    whose only located report(s) yield zero usable metrics still appears with
    an empty dict, so the gate can emit an explicit UNVERIFIED rather than
    silently dropping it.
    """
    located: dict[str, dict[str, float]] = {}
    report_globs = (
        ("*_PE_report.txt", parse_bismark_alignment_report),
        ("*_SE_report.txt", parse_bismark_alignment_report),
        ("*deduplication_report.txt", parse_bismark_dedup_report),
        ("*splitting_report.txt", parse_bismark_conversion_report),
    )
    for pattern, parser in report_globs:
        for path in sorted(run_dir.rglob(pattern)):
            sample = _sample_from_bismark(path)
            located.setdefault(sample, {}).update(parser(path))
    return located


def _locate_ampliseq_qc(run_dir: Path) -> dict[str, dict[str, float]]:
    """Find DADA2 stats artifacts under a run dir -> {sample: {slug: value}}.

    Structural difference from `_locate_methylseq_qc`: DADA2's
    `overall_summary.tsv` and ASV table are each a SINGLE multi-sample file
    (not one file per sample), so each parser already returns
    `{sample: {slug: value}}` directly, and this just MERGES the two dicts by
    sample key (`setdefault(sample, {}).update(...)`) rather than deriving a
    sample id from the filename. A sample present in only one of the two
    artifacts keeps whatever parsed; a sample whose only located artifact(s)
    yield zero usable metrics still appears with an empty dict, so the gate
    can emit an explicit UNVERIFIED rather than silently dropping it.
    """
    located: dict[str, dict[str, float]] = {}
    artifact_globs = (
        ("*overall_summary*.tsv", parse_dada2_overall_summary),
        ("*ASV_table*", parse_asv_table),
    )
    for pattern, parser in artifact_globs:
        for path in sorted(run_dir.rglob(pattern)):
            for sample, sample_metrics in parser(path).items():
                located.setdefault(sample, {}).update(sample_metrics)
    return located


def _locate_rnaseq_composition_qc(run_dir: Path) -> dict[str, dict[str, float]]:
    """RSeQC read_distribution.txt per sample -> {sample: {slug: value}}.

    One file per sample. When a sample resolves to multiple files (a run keeps
    both a published `results/` copy and an intermediate `work/` copy), prefer
    the published tree so the verdict never reads a pre-final `work/` write; a
    located-but-unparseable file still yields an empty dict so the gate can emit
    an explicit UNVERIFIED.
    """
    by_sample: dict[str, list[Path]] = {}
    for path in sorted(run_dir.rglob("*.read_distribution.txt")):
        sample = path.name[: -len(".read_distribution.txt")]
        by_sample.setdefault(sample, []).append(path)
    located: dict[str, dict[str, float]] = {}
    for sample, paths in by_sample.items():
        preferred = next(
            (p for p in paths if "results" in {q.lower() for q in p.relative_to(run_dir).parts}),
            paths[0],
        )
        located[sample] = parse_read_distribution(preferred)
    return located


def _locate_mag_qc(run_dir: Path) -> dict[str, dict[str, float]]:
    """Find QUAST + CheckM stats artifacts under a run dir -> {bin: {slug: value}}.

    Structural difference from `_locate_methylseq_qc`, same shape as
    `_locate_ampliseq_qc`: QUAST's `transposed_report.tsv` and CheckM's
    summary table are each a SINGLE multi-bin file (not one file per bin), so
    each parser already returns `{bin: {slug: value}}` directly, and this just
    MERGES the two dicts by bin id (`setdefault(bin, {}).update(...)`) rather
    than deriving a bin id from the filename. A bin present in only one of the
    two artifacts keeps whatever parsed; a bin whose only located artifact(s)
    yield zero usable metrics still appears with an empty dict, so the gate
    can emit an explicit UNVERIFIED rather than silently dropping it.
    """
    located: dict[str, dict[str, float]] = {}
    artifact_globs = (
        ("*transposed_report*.tsv", parse_quast_report),
        ("*checkm_summary*.tsv", parse_checkm_summary),
    )
    for pattern, parser in artifact_globs:
        for path in sorted(run_dir.rglob(pattern)):
            for bin_id, bin_metrics in parser(path).items():
                located.setdefault(bin_id, {}).update(bin_metrics)
    return located


def _discover_qc(run_dir: Path, assay: str = "rnaseq") -> list[QCResult]:
    """Verify a finished run: MultiQC metric checks (assay-specific rule pack) +
    structural checks on outputs + VCF plausibility checks (germline ts_tv/het_hom;
    somatic VAF/count/PON), each gated to its own assay."""
    results: list[QCResult] = []
    multiqc = next(run_dir.glob("**/multiqc_data.json"), None)
    if multiqc is not None:
        try:
            pack = rule_pack_for(assay)
        except ValueError:
            pack = None  # no rule pack for this assay -> skip metric QC (stay honest)
        if pack is not None and assay not in _DEDICATED_METRIC_ASSAYS:
            results.extend(
                evaluate_run_qc(multiqc, rule_pack=pack, cross_sample=(assay == "rnaseq"))
            )
    # Check that BAM outputs exist and are non-empty. We do NOT blanket-check for
    # indexes here: many BAMs are intermediates that are never indexed, and a
    # spurious index_present:fail would wrongly drag the verdict to "fail".
    bams = sorted(run_dir.glob("**/*.bam"))
    if bams:
        results.extend(evaluate_structural(bams))
    # Germline biological-plausibility checks (ts_tv, het_hom, sex_plausibility)
    # computed straight from the VCF. This path is INDEPENDENT of MultiQC: it
    # runs whether or not a report was found, so a germline run is never left
    # without these checks. We locate the primary VCF exactly as concordance
    # does (the variant_calling manifest's first required glob, rglob'd under
    # the run), and skip cleanly when there is none. Gated strictly to germline
    # so other assays are untouched.
    if assay == "variant_calling":
        pattern = manifest_for("variant_calling").required[0]  # "*.vcf.gz"
        vcfs = sorted(p for p in run_dir.rglob(pattern) if p.is_file())
        if vcfs:
            results.extend(evaluate_variant_plausibility(vcfs[0]))
            results.extend(evaluate_sex_plausibility(vcfs[0]))
    # Annotation structural + plausibility verification (capability C7; germline
    # structural shipped M1, somatic structural enabled M2, plausibility M3 — the
    # SAME located VCF feeds both verifiers, no duplicate scan). Gated to both
    # variant assays. We look for an annotated VCF (one carrying CSQ/ANN)
    # anywhere under the run: the structural checks prove the annotation step
    # ran; the plausibility checks (WARN-capped) assess what it found (real vs.
    # intergenic consequence distribution). Absent annotation is handled inside
    # evaluate_annotation_structural as UNVERIFIED, so a plain (un-annotated)
    # run is never dragged down — we simply don't find an annotated VCF and
    # skip both blocks silently (no duplicate UNVERIFIED). Research-use only: no
    # significance claim.
    if assay in VARIANT_ASSAYS:
        from contig.verification.annotation_plausibility import (
            evaluate_annotation_plausibility,
        )
        from contig.verification.annotation_structural import (
            annotation_metrics,
            evaluate_annotation_structural,
        )

        for vcf in sorted(run_dir.rglob("*.vcf.gz")):
            if annotation_metrics(vcf).info_key is not None:
                results.extend(evaluate_annotation_structural(vcf))
                results.extend(evaluate_annotation_plausibility(vcf))
                break
        # Cross-tool VEP-vs-SnpEff annotation concordance (capability C7 M4):
        # auto-discovers the annotation source(s) under the run (single-vcf-both
        # or two-file layout) and evaluates both the consequence and gene-symbol
        # metrics against each other. No CLI flag -- mirrors the somatic
        # cross-caller concordance auto-wiring below. Clean `[]` skip when no
        # annotated VCF is found at all; honest UNVERIFIED (never a false pass)
        # when only one annotator ran or the layout is ambiguous.
        results.extend(evaluate_annotation_concordance_from_run(run_dir))
    # Somatic biological-plausibility checks (capability C4 follow-on): VAF
    # distribution, somatic variant count, and panel-of-normals presence, all
    # computed from the tumor column of the Mutect2 VCF. Gated strictly to the
    # somatic assay. We glob the somatic manifest's required *.vcf.gz and pick the
    # Mutect2 candidate by path; if VCFs exist but none is Mutect2 we emit ONE
    # honest UNVERIFIED (never a silent pass), and if there is no VCF at all we
    # skip silently (structural QC already covers a missing required output).
    if assay == "somatic_variant_calling":
        pattern = manifest_for("somatic_variant_calling").required[0]  # "*.vcf.gz"
        vcfs = sorted(p for p in run_dir.rglob(pattern) if p.is_file())
        if vcfs:
            # Match "mutect2" as a path COMPONENT below the run dir (sarek writes the
            # VCF under a `mutect2/` directory), not as a substring of the absolute
            # path — otherwise a "mutect2" in an ancestor workspace/run-id name would
            # false-positively select a Strelka VCF and risk a pass on the wrong data.
            mutect2 = next(
                (
                    p
                    for p in vcfs
                    if "mutect2" in {part.lower() for part in p.relative_to(run_dir).parts}
                ),
                None,
            )
            if mutect2 is not None:
                results.extend(evaluate_somatic_plausibility(mutect2))
                # Tumor/normal swap smell test (swap-verdict, C4 follow-on):
                # reads the same Mutect2 VCF's NORMAL column (##normal_sample=)
                # for an implausibly high median VAF -- the somatic signal
                # sitting in the normal, which points at a swapped/mislabeled/
                # heavily contaminated pair. WARN-capped (no fail_*) and
                # UNVERIFIED-when-unresolvable, so it can never change the
                # exit code or silently drop.
                results.extend(evaluate_swap_plausibility(mutect2))
            else:
                results.append(
                    QCResult(
                        check="somatic_vaf_plausibility",
                        status="unverified",
                        message=(
                            "no Mutect2 somatic VCF found to assess VAF distribution"
                        ),
                        value=None,
                        kind="metric",
                    )
                )
            # Cross-tool PASS-site-overlap concordance (Strelka2 vs Mutect2):
            # appended after, and independent of, VAF plausibility above — it
            # reuses the same globbed VCF list but self-selects both callers'
            # files and skips cleanly (or reports UNVERIFIED) on its own terms.
            results.extend(evaluate_somatic_concordance_from_run(run_dir, vcfs))
            # Strelka2 tumor-VAF plausibility (capability C4 follow-on, PRD S1):
            # mirrors the Mutect2 median_vaf gate above, but sourced from
            # Strelka2's own tier-count VAF definition (AU/CU/GU/TU for SNVs,
            # TAR/TIR for indels), since Strelka2 emits no AF/AD FORMAT field.
            # Reuses select_caller_vcfs -- the same locator the concordance
            # wiring above uses -- so a "strelka" caller directory is resolved
            # once, the same way, everywhere. A uniquely-resolved pair yields
            # exactly the strelka file list (never mutect2's), split into its
            # SNV and indel halves by filename (sarek names them
            # `*.somatic_snvs*` / `*.somatic_indels*`). No strelka VCF at all
            # -> emit nothing (structural QC already owns a missing required
            # output). A strelka VCF present but the layout is non-unique or
            # mismatched with Mutect2's pair (the same condition
            # select_caller_vcfs flags for concordance) -> one honest
            # UNVERIFIED, never a silent pass and never an arbitrary pick.
            _, strelka, strelka_reason = select_caller_vcfs(run_dir, vcfs)
            if strelka:
                snv = next((p for p in strelka if "snv" in p.name.lower()), None)
                indel = next((p for p in strelka if "indel" in p.name.lower()), None)
                results.extend(evaluate_strelka_vaf_plausibility(snv, indel))
            elif strelka_reason is not None and any(
                "strelka" in {part.lower() for part in p.relative_to(run_dir).parts}
                for p in vcfs
            ):
                results.append(
                    QCResult(
                        check="strelka_median_vaf",
                        status="unverified",
                        message=(
                            "no unique Strelka2 tumor-normal pair found to assess "
                            f"VAF distribution: {strelka_reason}"
                        ),
                        value=None,
                        kind="metric",
                    )
                )
    # RNA-seq biological-plausibility checks (capability C3, RNA-seq slice, Phase 3).
    # Gated: only when the assay is rnaseq AND a MultiQC report was found. One extra
    # parse of the same JSON is intentional — mirrors the germline path independently
    # re-locating the VCF so the two gates stay self-contained.
    if assay == "rnaseq" and multiqc is not None:
        metrics = parse_multiqc_general_stats_file(multiqc)
        results.extend(evaluate_rnaseq_plausibility(metrics))
    # RNA-seq read-composition QC (capability C3, rnaseq slice, additive to the
    # MultiQC-driven gate above). RSeQC's exonic/intronic/unassigned fractions do
    # NOT reach Contig's MultiQC general-stats ingest (verified against a real
    # multiqc_data.json), so a dedicated gate parses the read_distribution.txt
    # artifact directly and drives RNASEQ_COMPOSITION_PACK -- mirrors the
    # methylseq/ampliseq gates below. rnaseq deliberately stays OUT of
    # _DEDICATED_METRIC_ASSAYS: the MultiQC pack above owns alignment and,
    # since its key/unit fix, duplication too; rRNA remains unscored (its
    # percent_rRNA slug is still an unverified guess, never confirmed against
    # a real report) — this gate only owns the composition fractions.
    # A located artifact with no usable metric yields one explicit UNVERIFIED
    # (never a silent no-op or a false pass); no artifact at all skips silently
    # (structural QC owns a genuinely missing output; read_distribution is NOT
    # part of the rnaseq structural manifest). Kept as a SEPARATE `if` block from
    # the gate above (not merged) -- mirrors the germline dual-gate precedent.
    if assay == "rnaseq":
        for sample, sample_metrics in _locate_rnaseq_composition_qc(run_dir).items():
            if sample_metrics:
                results.extend(evaluate({sample: sample_metrics}, RNASEQ_COMPOSITION_PACK))
            else:
                results.append(
                    QCResult(
                        check=f"rnaseq_composition_qc:{sample}",
                        status="unverified",
                        message=(
                            f"{sample}: RSeQC read_distribution found but no usable metric parsed"
                        ),
                        value=None,
                        kind="metric",
                    )
                )
    # Single-cell cell-QC (capability C3, scrnaseq slice). The base nf-core/scrnaseq
    # pipeline does NOT route cell-level metrics into MultiQC general-stats, so a
    # dedicated gate parses the aligner's own cell-QC artifact (STARsolo Summary.csv
    # / Cell Ranger metrics_summary.csv) and drives SCRNASEQ_RULE_PACK. A located file
    # with no usable metric yields one explicit UNVERIFIED (never a silent no-op or a
    # false pass); no artifact at all skips silently (structural QC owns a missing
    # output, mirroring the germline no-VCF path). Gated strictly to scrnaseq.
    if assay == "scrnaseq":
        for sample, sample_metrics in _locate_scrnaseq_qc(run_dir).items():
            if sample_metrics:
                results.extend(evaluate({sample: sample_metrics}, SCRNASEQ_RULE_PACK))
            else:
                results.append(
                    QCResult(
                        check=f"scrnaseq_cell_qc:{sample}",
                        status="unverified",
                        message=(
                            f"{sample}: cell-QC file found but no usable metric parsed"
                        ),
                        value=None,
                        kind="metric",
                    )
                )
    # Methylseq bisulfite QC (capability C3, methylseq slice). nf-core/methylseq
    # does not reliably route Bismark's per-sample metrics into MultiQC
    # general-stats under a stable slug, so a dedicated gate parses Bismark's own
    # on-disk report artifacts (alignment, deduplication, splitting/conversion)
    # and drives METHYLSEQ_RULE_PACK directly -- mirrors the scrnaseq gate above.
    # A located artifact with no usable metric yields one explicit UNVERIFIED
    # (never a silent no-op or a false pass); no artifact at all skips silently
    # (structural QC owns a missing output). A sample with only a partial report
    # set (e.g. alignment only) evaluates the checks it can and is NOT forced
    # into a whole-sample UNVERIFIED (M3/A4). Gated strictly to methylseq; the
    # generic MultiQC pack path above skips methylseq (_DEDICATED_METRIC_ASSAYS)
    # so this gate is the single authoritative source (M6).
    if assay == "methylseq":
        for sample, sample_metrics in _locate_methylseq_qc(run_dir).items():
            if sample_metrics:
                results.extend(evaluate({sample: sample_metrics}, METHYLSEQ_RULE_PACK))
            else:
                results.append(
                    QCResult(
                        check=f"methylseq_qc:{sample}",
                        status="unverified",
                        message=(
                            f"{sample}: Bismark report found but no usable metric parsed"
                        ),
                        value=None,
                        kind="metric",
                    )
                )
    # Ampliseq DADA2 QC (capability C3, ampliseq slice). nf-core/ampliseq does
    # not reliably route DADA2's per-sample metrics into MultiQC general-stats
    # under a stable slug, so a dedicated gate parses DADA2's own on-disk stats
    # artifacts (overall_summary.tsv, ASV table) and drives AMPLISEQ_RULE_PACK
    # directly -- mirrors the methylseq gate above. The one structural
    # difference: DADA2's artifacts are MULTI-sample files (one file, many
    # samples), so `_locate_ampliseq_qc` merges the parsers' own
    # `{sample: {...}}` dicts by sample key rather than deriving a sample id
    # from the filename. A located sample with no usable metric yields one
    # explicit UNVERIFIED (never a silent no-op or a false pass); no artifact
    # at all skips silently (structural QC owns a missing required output). A
    # sample with only a partial artifact set (e.g. overall_summary.tsv only,
    # no ASV table) evaluates the checks it can and is NOT forced into a
    # whole-sample UNVERIFIED (B4). Gated strictly to ampliseq; the generic
    # MultiQC pack path above skips ampliseq (_DEDICATED_METRIC_ASSAYS) so this
    # gate is the single authoritative source (M6).
    if assay == "ampliseq":
        for sample, sample_metrics in _locate_ampliseq_qc(run_dir).items():
            if sample_metrics:
                results.extend(evaluate({sample: sample_metrics}, AMPLISEQ_RULE_PACK))
            else:
                results.append(
                    QCResult(
                        check=f"ampliseq_qc:{sample}",
                        status="unverified",
                        message=(
                            f"{sample}: DADA2 stats found but no usable metric parsed"
                        ),
                        value=None,
                        kind="metric",
                    )
                )
    # Mag (shotgun metagenomics) assembly/bin QC (capability C3, mag slice).
    # nf-core/mag does not reliably route QUAST's/CheckM's per-bin metrics
    # into MultiQC general-stats under a stable slug, so a dedicated gate
    # parses QUAST's and CheckM's own on-disk stats artifacts
    # (transposed_report.tsv, CheckM summary) and drives MAG_RULE_PACK
    # directly -- mirrors the ampliseq gate above. The entity key is the BIN
    # (not the sample): `_locate_mag_qc` merges the two parsers' own
    # `{bin: {...}}` dicts by bin id rather than deriving a bin id from the
    # filename. A located bin with no usable metric yields one explicit
    # UNVERIFIED (never a silent no-op or a false pass); no artifact at all
    # skips silently (structural QC owns a missing required output). A bin
    # with only a partial artifact set (e.g. QUAST only, no CheckM) evaluates
    # the checks it can and is NOT forced into a whole-bin UNVERIFIED (C4).
    # Gated strictly to mag; the generic MultiQC pack path above skips mag
    # (_DEDICATED_METRIC_ASSAYS) so this gate is the single authoritative
    # source (M6).
    if assay == "mag":
        for bin_id, bin_metrics in _locate_mag_qc(run_dir).items():
            if bin_metrics:
                results.extend(evaluate({bin_id: bin_metrics}, MAG_RULE_PACK))
            else:
                results.append(
                    QCResult(
                        check=f"mag_qc:{bin_id}",
                        status="unverified",
                        message=(
                            f"{bin_id}: QUAST/CheckM stats found but no usable metric parsed"
                        ),
                        value=None,
                        kind="metric",
                    )
                )
    return results

# An executor runs the Nextflow argv and is responsible for the trace file
# existing at trace_path when it returns. The default shells out; tests inject a
# fake that writes a canned trace, so the parse/assemble/bundle path stays real.
Executor = Callable[[list[str], Path], int]

# An index builder runs an auxiliary build command (e.g. `samtools faidx ref`)
# in the given cwd and returns its exit code. The default shells out; tests
# inject a fake that creates the index file, so no real tool runs in CI.
IndexBuilder = Callable[[list[str], Path], int]

# An installer runs a dependency-install command (e.g. `python -m pip install
# numpy`) and returns its exit code. The default shells out; tests inject a
# fake so no real pip runs and no network is touched in CI (mirrors
# IndexBuilder / default_index_builder).
Installer = Callable[[list[str], Path], int]

# A fetcher runs a git argv (clone or rev-parse) in the given cwd. The default
# shells out; tests inject a fake so no real git and no network is touched in
# CI (mirrors Executor / IndexBuilder / Installer). Unlike those, it returns
# `(exit_code, stdout)` rather than a bare exit code: git's stderr is the only
# useful diagnostic for a failed clone, and `git rev-parse`'s stdout is how the
# resolved commit is read -- and that commit is the whole point of the slice.
Fetcher = Callable[[list[str], Path], tuple[int, str]]

# A sleeper pauses for the given number of seconds (e.g. a retry patch's
# `wait_seconds`). The default is the real `time.sleep`; tests inject a fake
# so no real time passes in CI (mirrors Executor / IndexBuilder / Installer /
# Fetcher). Direct precedent: `make_watchdog_executor`'s `sleeper` parameter
# below, which this alias names retroactively.
Sleeper = Callable[[float], None]


class PipelineExecutionError(RuntimeError):
    """Raised when the workflow manager exits nonzero (DETECT, ARCHITECTURE §5.1).

    Surfacing the return code cleanly is the entry point for diagnosis/self-heal;
    it must not be masked by a downstream missing-trace traceback.
    """

    def __init__(self, returncode: int, record: "RunRecord | None" = None):
        self.returncode = returncode
        self.record = record  # whatever was captured before/at failure, for diagnosis
        super().__init__(f"Nextflow exited with code {returncode}")


def default_executor(cmd: list[str], trace_path: Path) -> int:
    """Run Nextflow in the data plane, teeing stdout+stderr to run.log.

    The log is the detector's primary input (ARCHITECTURE §5.1): it carries the
    failing process, command, and stderr that classification keys off.
    """
    log_path = trace_path.parent / "run.log"
    with open(log_path, "wb") as log:
        proc = subprocess.run(
            cmd, cwd=trace_path.parent, stdout=log, stderr=subprocess.STDOUT, check=False
        )
    return proc.returncode


# How often the watchdog wakes to fingerprint the run's output surfaces. A
# constant, not a flag (D3): the poll rate is an implementation detail of the
# supervisor, not a knob a user has any basis to tune. Overridable by keyword
# for tests only, mirroring `self_heal`'s resource_ceiling precedent.
_STALL_POLL_INTERVAL_SEC = 30.0

# How long a stalled child gets between SIGTERM and SIGKILL (D5). Mirrors
# `lifecycle._terminate_process_group`'s ladder.
_STALL_GRACE_SEC = 5.0

# The granularity at which the poll wait is taken. The watchdog sleeps in slices
# this long so it can notice a child that exited early instead of charging the
# run a full poll interval of dead latency; 0.1s is far below any poll interval
# and far above the cost of a no-op wakeup.
_STALL_WAKE_SLICE_SEC = 0.1

# How long one heartbeat read may take before the watchdog gives up on it and
# keeps the previous fingerprint (D1). A read that blocks longer than this is a
# filesystem that cannot answer stat() -- which is itself "no progress".
_STALL_STAT_DEADLINE_SEC = 5.0


def make_watchdog_executor(
    *,
    stall_timeout_sec: float,
    observer: HeartbeatObserver = read_heartbeat,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
    poll_interval: float = _STALL_POLL_INTERVAL_SEC,
    grace_sec: float = _STALL_GRACE_SEC,
    stat_deadline_sec: float = _STALL_STAT_DEADLINE_SEC,
) -> Executor:
    """Build an `Executor` that supervises the child and kills a stalled run.

    Returns a closure of exactly the `Executor` shape `(cmd, trace_path) -> int`,
    so it drops into `run_pipeline`'s existing seam with no other plumbing. A
    non-positive `stall_timeout_sec` disables supervision entirely and delegates
    to `default_executor` -- the watchdog is opt-in, and "off" must be the plain
    executor byte for byte.
    """

    def _watchdog_executor(cmd: list[str], trace_path: Path) -> int:
        if stall_timeout_sec <= 0:
            return default_executor(cmd, trace_path)

        run_dir = trace_path.parent
        log_path = run_dir / "run.log"
        # Truncate first, exactly as default_executor's "wb" does, then hand the
        # child an O_APPEND handle instead. Two processes write this file: the
        # child (stdout+stderr) and us (the stall verdict). The inherited
        # descriptor shares its offset with ours, so an ordinary write would
        # usually land in the right place anyway -- O_APPEND is what makes that
        # a guarantee rather than a coincidence, holding even if the child
        # reopens or seeks its stdout, and keeping a dying Nextflow's last words
        # from landing on top of the verdict.
        log_path.write_bytes(b"")
        with open(log_path, "ab") as log:
            proc = subprocess.Popen(
                cmd,
                cwd=run_dir,
                stdout=log,
                stderr=subprocess.STDOUT,
                # D2: its own session, so killpg reaps the pipeline's whole tree
                # without reaping contig itself (today the child shares contig's
                # group, and killpg on our own group would kill the supervisor).
                start_new_session=True,
            )
            try:
                _publish_child_pgid(run_dir, proc.pid)

                previous: Heartbeat | None = None
                last_change_at = clock()
                while proc.poll() is None:
                    _pause_between_polls(proc, poll_interval, sleeper)
                    if proc.poll() is not None:
                        break
                    current = observe_with_deadline(
                        observer, run_dir, trace_path, previous, stat_deadline_sec
                    )
                    now = clock()
                    decision = evaluate_stall(
                        previous, current, last_change_at, now, stall_timeout_sec
                    )
                    if changed(previous, current):
                        last_change_at = now
                    previous = current
                    if not decision.stalled:
                        continue
                    # Write the verdict BEFORE killing: it is the detector's only
                    # evidence that the run was stalled rather than merely crashed,
                    # and losing it degrades the diagnosis to tool_crash. But the
                    # write is BOUNDED and its outcome ignored -- run.log sits in
                    # the run dir, which on the wedged-mount stall (D1) is the very
                    # filesystem that has stopped answering. Killing the run is the
                    # primary job; the message is evidence that improves it.
                    _write_stall_message(
                        log,
                        stall_message(
                            decision.idle_sec, stall_timeout_sec, decision.silent_surfaces
                        ),
                        stat_deadline_sec,
                    )
                    _terminate_child_group(proc, grace_sec)
                    break  # terminate at most once per invocation

                # Returned unchanged: a signalled child is -15/-9, which is non-zero,
                # so run_pipeline raises PipelineExecutionError and the existing
                # diagnosis path runs with no new plumbing.
                return proc.wait()
            except BaseException:
                # The one place BaseException is right: KeyboardInterrupt and
                # SystemExit are exactly the escapes that matter here. The child is
                # in its own session (D2), so the terminal's Ctrl-C never reaches
                # it -- without this, interrupting a supervised run would stop the
                # supervisor and leave Nextflow, its JVM and its containers burning
                # the user's compute. Kill first, then let the exception continue.
                _terminate_child_group(proc, grace_sec)
                raise
            finally:
                # Both exits from supervision leave a dead child behind: the
                # normal return has waited on it, and the interrupt path has just
                # killed it. Either way the published pgid stops naming anything
                # this run owns, so it is dropped here rather than left for the
                # next attempt to overwrite (see _clear_child_pgid).
                _clear_child_pgid(run_dir)

    return _watchdog_executor


def _pause_between_polls(
    proc: subprocess.Popen,
    poll_interval: float,
    sleeper: Callable[[float], None],
    slice_sec: float = _STALL_WAKE_SLICE_SEC,
) -> None:
    """Wait up to `poll_interval` before the next heartbeat, waking early on exit.

    Sleeping the whole interval blind would charge every run up to a full poll
    interval of dead latency after its child has already exited -- immaterial on a
    long run, but the self-heal loop's fast failures (bad argv, missing reference)
    would pay it on every attempt. So the wait is taken in short slices and
    abandoned as soon as the child is gone. Slicing rather than `proc.wait(timeout)`
    keeps the injected `sleeper` the real seam: a test that supplies its own
    sleeper still controls every pause this loop takes.
    """
    remaining = poll_interval
    while remaining > 0 and proc.poll() is None:
        step = min(slice_sec, remaining)
        sleeper(step)
        remaining -= step


def _write_stall_message(log: BinaryIO, message: str, deadline_sec: float) -> bool:
    """Append the watchdog's verdict to the open run.log, bounded by a deadline.

    Returns True if the write landed. The write happens in a **daemon** thread for
    the same reason the heartbeat read does (D1): run.log lives in the run dir, so
    on the wedged-mount stall it is the very filesystem that has stopped answering,
    and `write`/`flush` against a hard-mounted unresponsive NFS blocks
    uninterruptibly. A blocked write must never stop the kill -- the caller ignores
    the result and terminates regardless -- but on a healthy filesystem (the common
    case) this returns in microseconds, so the message still lands BEFORE the child
    is signalled, which is the ordering the detector depends on.
    """
    done = threading.Event()

    def _write() -> None:
        try:
            log.write((message + "\n").encode())
            log.flush()
        except Exception as exc:  # noqa: BLE001 -- evidence is never worth the run
            logger.warning("could not write the stall verdict to run.log: %s", exc)
        finally:
            done.set()

    threading.Thread(target=_write, daemon=True).start()
    if done.wait(deadline_sec):
        return True
    logger.warning(
        "stall verdict did not reach run.log within %ss (blocked write); "
        "terminating the run anyway",
        deadline_sec,
    )
    return False


def _publish_child_pgid(run_dir: Path, pid: int) -> None:
    """Merge the detached child's process-group id into status.json (D2).

    `contig cancel` reaps the group of the pid it finds in status.json, which is
    contig's OWN pid; that only worked because the child shared contig's group.
    Spawning into a new session removes it from that group, so the child's pgid
    has to be published for `cancel_run` to reap it too.
    """
    try:
        pgid = os.getpgid(pid)
    except OSError:
        # The child is already gone, so there is no live group to cancel and
        # nothing worth recording; a recycled pgid would be worse than none.
        return
    _write_child_pgid(run_dir, pgid)


def _clear_child_pgid(run_dir: Path) -> None:
    """Drop `child_pgid` from status.json now that no detached child is alive.

    The key means exactly one thing: there is a detached child running RIGHT NOW.
    `_publish_child_pgid` already refuses to record an already-dead child for the
    reason above; leaving the key behind once the child exits reintroduces the
    same hazard from the other end. Nothing else clears it in time: self_heal's
    retry branches fall through to the next attempt without rewriting
    status.json, so a dead pgid would survive until the next attempt republishes,
    and a `contig cancel` landing in that window on a host that has wrapped
    `pid_max` could signal an unrelated process group.
    """
    _write_child_pgid(run_dir, None)


def _write_child_pgid(run_dir: Path, pgid: int | None) -> None:
    """Merge `child_pgid` into status.json, or drop the key when `pgid` is None.

    Read-modify-write, never a fresh dict: status.json belongs to self_heal, and
    the run's own state/pid must survive either edit. Purely telemetry for another
    command: a missing, unreadable, or unwritable status.json is warned about and
    never allowed to fail the run.
    """
    path = run_dir / "status.json"
    try:
        existing = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        logger.warning("could not read %s to update child_pgid: %s", path, exc)
        return
    if not isinstance(existing, dict):
        logger.warning("%s is not a JSON object; not recording child_pgid", path)
        return
    if pgid is None:
        if "child_pgid" not in existing:
            return  # nothing to clear; leave the file (and its mtime) alone
        del existing["child_pgid"]
    else:
        existing["child_pgid"] = pgid
    try:
        path.write_text(json.dumps(existing))
    except OSError as exc:
        logger.warning("could not write %s to update child_pgid: %s", path, exc)


def _terminate_child_group(proc: subprocess.Popen, grace_sec: float) -> None:
    """SIGTERM the stalled child's group, then SIGKILL it if it outlives the grace.

    Mirrors `lifecycle._terminate_process_group` (D5). Signals the GROUP, not the
    pid: Nextflow's Java process and the tool children it spawned all have to go,
    or the "terminated" run keeps burning compute. A child that exits inside the
    grace window is never SIGKILLed, and a group that is already gone is fine --
    there is simply nothing left to reap.
    """
    # An already-reaped child has no group left to signal, and its pid is free to
    # be handed to an unrelated process the moment it is reaped -- so this must be
    # checked BEFORE naming any group. It is reachable: the BaseException handler
    # can run after `proc.wait()` has already returned.
    if proc.returncode is not None:
        return
    # `proc.pid` IS the group id: the child was spawned with start_new_session=True,
    # which makes it a session (and therefore process-group) leader, so pgid == pid
    # by construction. Looking it up with os.getpgid would buy nothing and would
    # add a second window in which the pid could have been recycled.
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=grace_sec)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def default_command_executor(cmd: list[str], cwd: Path) -> tuple[int, str]:
    """Run argv in cwd and return `(exit_code, combined_output)` (used by
    `contig reproduce`).

    Unlike `default_executor`, `cwd` IS the working directory to run in (not a
    trace-file path), and nothing is written into it. Tests inject a fake so no
    real process runs in CI.
    """
    proc = subprocess.run(
        cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    return proc.returncode, proc.stdout or ""


def default_index_builder(cmd: list[str], cwd: Path) -> int:
    """Run an auxiliary index-build command (e.g. ``samtools faidx ref``) in cwd.

    Tees combined stdout+stderr to run.log (appending), so the build output is
    captured alongside the pipeline log that default_executor wrote. Returns the
    process exit code. Tests inject a fake builder so no real tool runs in CI.
    """
    log_path = Path(cwd) / "run.log"
    with open(log_path, "ab") as log:
        proc = subprocess.run(cmd, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, check=False)
    return proc.returncode


def _pip_install_argv(module: str) -> list[str]:
    """Build the fixed pip-install argv for a single module (no shell, no interpolation)."""
    return [sys.executable, "-m", "pip", "install", module]


def default_installer(cmd: list[str], cwd: Path) -> int:
    """Run a dependency-install command (e.g. `python -m pip install numpy`) in cwd.

    Returns the process exit code. Tests inject a fake installer so no real pip
    runs and no network is touched in CI (mirrors default_index_builder).
    """
    proc = subprocess.run(cmd, cwd=cwd, check=False)
    return proc.returncode


def _git_clone_argv(url: str, dest: Path) -> list[str]:
    """Build the fixed argv for a shallow clone of `url` into `dest`.

    `--depth 1` is deliberate: much faster on the real published repos this
    targets, and HEAD still resolves to a full 40-char SHA so the commit pin
    is unaffected. The `--` terminator is required, not cosmetic: it is the
    second line of defence behind classify_repo_argument's leading-dash
    refusal, stopping any argument that survives classification from being
    read by git as an option.
    """
    return ["git", "clone", "--depth", "1", "--", url, str(dest)]


def _git_init_argv() -> list[str]:
    """Build the fixed argv that makes an existing empty directory a git repo.

    Run with the destination itself as cwd. This replaces `git clone`'s
    directory creation on the `--rev` path: a shallow clone cannot check out
    an arbitrary commit, so the revision is fetched into a repo initialised
    here instead.
    """
    return ["git", "init", "-q"]


def _git_remote_add_argv(url: str) -> list[str]:
    """Build the fixed argv that points a freshly-initialised repo at `url`.

    The `--` terminator serves the same purpose as in `_git_clone_argv`: the
    second line of defence behind classify_repo_argument's leading-dash
    refusal. `git remote add` accepts it (verified against real git).
    """
    return ["git", "remote", "add", "origin", "--", url]


def _git_fetch_argv(rev: str) -> list[str]:
    """Build the fixed argv that fetches exactly one revision, shallowly.

    `--depth 1` for the same reason as the clone: much faster on the real
    published repos this targets. Unlike `git clone --depth 1 --branch <ref>`
    -- which accepts a tag or branch but REJECTS a raw SHA -- a targeted fetch
    resolves a full SHA, a tag, or a branch, and a raw SHA is the input that
    matters most, since it is what `source_commit` contains.

    The `--` terminator is the second line of defence behind
    classify_rev_argument's leading-dash refusal (`git fetch` accepts it,
    verified against real git).

    Fetching a raw SHA depends on the server enabling
    `uploadpack.allowReachableSHA1InWant`. GitHub and GitLab do; a remote that
    does not is surfaced as an honest refusal by the caller, never a silent
    fallback to a full clone.
    """
    return ["git", "fetch", "--depth", "1", "origin", "--", rev]


def _git_checkout_argv() -> list[str]:
    """Build the fixed argv that checks out whatever `_git_fetch_argv` fetched.

    `--detach` is explicit so the detached-HEAD state is intentional rather
    than incidental; `git rev-parse HEAD` reads the same either way.
    """
    return ["git", "checkout", "--detach", "FETCH_HEAD"]


def _git_rev_parse_argv() -> list[str]:
    """Build the fixed argv that resolves HEAD to its full commit SHA."""
    return ["git", "rev-parse", "HEAD"]


def default_fetcher(cmd: list[str], cwd: Path) -> tuple[int, str]:
    """Run a git argv (clone or rev-parse) in cwd, returning `(exit_code, stdout)`.

    stderr is merged into stdout so a failed clone's diagnostic isn't lost;
    for `git rev-parse HEAD` the same stream carries the resolved commit.
    Tests inject a fake fetcher so no real git and no network is touched in
    CI (mirrors default_index_builder / default_installer).
    """
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False
        )
    except FileNotFoundError as exc:
        # subprocess.run raises when the binary is absent; every other seam
        # in this file converts failure into a return value rather than
        # raising, and the caller in a later task depends on that.
        return 127, f"git executable not found: {exc}"
    return proc.returncode, proc.stdout or ""


def read_run_log(run_dir: str | Path) -> str:
    """Return the captured run.log text for a run, or '' if none was written."""
    log_path = Path(run_dir) / "run.log"
    return log_path.read_text() if log_path.exists() else ""


def read_task_errors(run_dir: str | Path, max_tasks: int = 10, tail_lines: int = 40) -> str:
    """Collect the per-task `.command.err` output from the Nextflow work dirs.

    The main run.log only says which process failed; the real error (a tool's
    stderr, a container/platform warning) lives in the failing task's
    `.command.err`. The detector needs it (ARCHITECTURE §5.2).
    """
    work = Path(run_dir) / "work"
    if not work.is_dir():
        return ""
    chunks: list[str] = []
    for err in sorted(work.glob("**/.command.err"))[:max_tasks]:
        # Only failed/killed tasks: a successful task's stderr is noise that can
        # trigger the wrong diagnosis. exitcode "0" -> skip; non-zero or absent
        # (killed before writing one) -> include.
        exitcode = err.parent / ".exitcode"
        if exitcode.exists() and exitcode.read_text().strip() == "0":
            continue
        text = err.read_text(errors="replace").strip()
        if text:
            tail = "\n".join(text.splitlines()[-tail_lines:])
            chunks.append(f"# {err.parent.name}\n{tail}")
    return "\n".join(chunks)


def build_nextflow_command(
    pipeline: str,
    revision: str,
    profiles: list[str],
    trace_path: str,
    params: dict[str, object] | None = None,
    resume: bool = False,
    config_path: str | None = None,
) -> list[str]:
    """Construct the `nextflow run` argv for a pipeline, with trace capture wired in.

    `config_path`, when given, is injected as the `-c` launcher option (which must
    precede the `run` subcommand) so the generated ExecutionTarget profile selects
    the backend/runtime for this run.
    """
    cmd = ["nextflow"]
    if config_path:
        cmd += ["-c", config_path]
    cmd += [
        "run",
        pipeline,
        "-r",
        revision,
        "-profile",
        ",".join(profiles),
        "-with-trace",
        trace_path,
    ]
    if resume:
        cmd.append("-resume")
    for key, value in (params or {}).items():
        cmd += [f"--{key}", str(value)]
    return cmd


def _build_engine_run(
    target: ExecutionTarget,
    run_dir: Path,
    pipeline: str,
    revision: str,
    profiles: list[str],
    params: dict[str, object] | None,
    resume: bool,
) -> tuple[list[str], Path, Callable[[Path], list[TaskEvent]]]:
    """Build the command, artifact path, and events parser for the target's engine.

    This is the single point where Nextflow and Snakemake diverge. Nextflow gets a
    generated nextflow.config (the compute abstraction: local/cloud/HPC selected by
    the profile) and a trace TSV; Snakemake gets a typed `snakemake` command and a
    stats JSON. Both leave a machine-readable artifact the runner ingests into the
    same TaskEvent shape.
    """
    if target.engine == "snakemake":
        # `pipeline` carries the Snakefile path for the snakemake engine (there is
        # no nf-core pipeline ref). cores ride from the resource_limits cap, else 1.
        artifact_path = run_dir / "stats.json"
        cores = int(_lead_int(target.resource_limits.get("cpus"), 1))
        cmd = build_snakemake_command(
            snakefile=pipeline, cores=cores, run_dir=str(run_dir)
        )
        return cmd, artifact_path, parse_snakemake_stats_file

    # Default engine: Nextflow. Map the ExecutionTarget to a nextflow.config (the
    # compute abstraction: local/cloud/HPC selected by generating the profile, not
    # by branching here), then build the `nextflow run` argv with trace capture.
    artifact_path = run_dir / "trace.txt"
    config_path = run_dir / "nextflow.config"
    config_path.write_text(generate_nextflow_config(target))
    cmd = build_nextflow_command(
        pipeline, revision, profiles, str(artifact_path), params, resume, str(config_path)
    )
    return cmd, artifact_path, parse_trace_file


def _lead_int(value: object, default: int) -> int:
    """Leading integer of a resource literal ('4' or '4.GB' -> 4), else the default."""
    if value is None:
        return default
    text = str(value).strip()
    digits = ""
    for ch in text:
        if ch.isdigit():
            digits += ch
        else:
            break
    return int(digits) if digits else default


def run_pipeline(
    *,
    pipeline: str,
    revision: str,
    profiles: list[str],
    target: ExecutionTarget,
    input_paths: list[str | Path],
    runs_dir: str | Path,
    run_id: str,
    executor: Executor = default_executor,
    params: dict[str, object] | None = None,
    nextflow_version: str | None = None,
    resume: bool = False,
    assay: str = "rnaseq",
) -> RunRecord:
    """Run a pipeline and capture it into a reproducible, bundled RunRecord.

    Ties the spike together: build the command, execute it (writing a trace),
    ingest the trace into events, assemble the provenance record, and persist a
    portable reproduce-bundle. The result is a run we can prove and re-run.
    """
    run_dir = (Path(runs_dir) / run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    # The Engine seam: build the command for the selected engine and name the
    # machine-readable artifact it must leave behind (a Nextflow trace TSV, or a
    # Snakemake stats JSON). Everything downstream (capture, record, verify,
    # bundle) is engine-agnostic, so the engine is swapped only here.
    cmd, artifact_path, parse_events = _build_engine_run(
        target, run_dir, pipeline, revision, profiles, params, resume
    )
    returncode = executor(cmd, artifact_path)

    # Capture whatever the run produced (success OR failure). The failure data
    # (the detect/diagnose input, and the moat) must not be discarded just
    # because the run exited nonzero. Only when no artifact exists is there
    # nothing to record.
    record: RunRecord | None = None
    if artifact_path.exists():
        record = RunRecord(
            run_id=run_id,
            pipeline=pipeline,
            pipeline_revision=revision,
            target=target,
            input_checksums=compute_input_checksums(input_paths),
            parameters=params or {},
            events=parse_events(artifact_path),
            qc_results=_discover_qc(run_dir, assay),
            assay=assay,
            nextflow_version=nextflow_version,
            contig_version=_contig_version(),
        )
        write_bundle(record, run_dir)

    if returncode != 0:
        raise PipelineExecutionError(returncode, record)
    # A clean exit must have produced an artifact (hence a record); guard the
    # contract so a silent None can never escape as a "successful" run.
    assert record is not None, "successful run produced no artifact to capture"
    return record

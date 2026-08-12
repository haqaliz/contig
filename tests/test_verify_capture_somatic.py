"""Module-level capture out-params for the somatic verification evaluators (R4a).

Phase 1 (module-level half) of the eval-concordance-capture slice: the somatic
concordance + plausibility evaluators gain the germline `capture_metrics=`
out-param precedent (`variant_metrics.py:151-192`), so a later runner wiring can
store PRE-BAND verification inputs into `RunRecord.verification_inputs`. These
tests exercise the evaluators directly (never via `_discover_qc`), and pin that
the out-param is additive: every captured run returns byte-identical QCResults
to the same call without it.

Family/sample-key conventions pinned here (mirroring the aspect spec):
- concordance captures under the pair key `mutect2_vs_strelka2` with raw
  `value` (unrounded jaccard) and `n_shared` as float(union), on BOTH the
  normal and the too-few-sites paths;
- the plausibility evaluators capture under the same sample label their
  `<check>:<sample>` naming uses (resolved tumor/normal sample name);
- `pon_applied` is never captured (non-numeric).

Real files only, via pytest tmp_path; no mocks, no tool execution, no network.
"""

import gzip

import pytest

from contig.verification.somatic_concordance import (
    evaluate_somatic_concordance,
    evaluate_somatic_concordance_from_run,
)
from contig.verification.somatic_plausibility import (
    evaluate_somatic_plausibility,
    evaluate_swap_plausibility,
)
from contig.verification.strelka_vaf import evaluate_strelka_vaf_plausibility


def _dump(results) -> list[dict]:
    """The results as serialized dicts, for byte-identical comparisons."""
    return [r.model_dump() for r in results]


# --- concordance fixtures -----------------------------------------------------

_CONC_HEADER = "##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"


def _crec(chrom, pos, ref, alt, filt="PASS"):
    return f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t.\t{filt}\t.\n"


def _sites(n, chrom="chr1", start=100):
    """n distinct PASS-site tuples, deterministic and disjoint by `start`."""
    return [(chrom, start + i, "A", "G") for i in range(n)]


def _write_conc_vcf(path, records):
    body = "".join(_crec(*r) for r in records)
    path.write_text(_CONC_HEADER + body)
    return path


def _pair_dir(run_dir, caller, pair):
    d = run_dir / "results" / "variant_calling" / caller / pair
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sarek_tree(run_dir, pairs=("T_vs_N",), n=12):
    """A synthetic sarek-shaped run tree (Mutect2 VCF + Strelka snvs/indels
    per pair dir, identical PASS sites). Returns the sorted VCF list."""
    vcfs = []
    rows = _sites(n)
    for pair in pairs:
        m_dir = _pair_dir(run_dir, "mutect2", pair)
        vcfs.append(_write_conc_vcf(m_dir / f"{pair}.mutect2.somatic.vcf", rows))
        s_dir = _pair_dir(run_dir, "strelka", pair)
        vcfs.append(
            _write_conc_vcf(s_dir / f"{pair}.strelka.somatic_snvs.vcf", rows[:6])
        )
        vcfs.append(
            _write_conc_vcf(s_dir / f"{pair}.strelka.somatic_indels.vcf", rows[6:])
        )
    return sorted(vcfs)


# --- somatic plausibility fixtures (Mutect2 two-sample) -----------------------

_TUMOR = "TUMOR"
_NORMAL = "NORMAL"


def _pl_header(tumor=_TUMOR, normal=_NORMAL, normal_line=True):
    lines = ["##fileformat=VCFv4.2", f"##tumor_sample={tumor}"]
    if normal_line:
        lines.append(f"##normal_sample={normal}")
    # column order: NORMAL then TUMOR, to prove selection is by name, not position
    lines.append(
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\t"
        f"{normal}\t{tumor}"
    )
    return "\n".join(lines) + "\n"


def _prec(chrom, pos, ref, alt, tumor_fmt, normal_fmt="0/0:0.0:10,0:10", fmt="GT:AF:AD:DP"):
    # tumor_fmt like "0/1:0.30:14,6:20"; column order NORMAL then TUMOR
    return f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t.\tPASS\t.\t{fmt}\t{normal_fmt}\t{tumor_fmt}\n"


def _write_pl_vcf(path, header, recs):
    path.write_text(header + "".join(recs))
    return path


def _recs_with_af(af, n, start_pos=100):
    """n biallelic records, each tumor AF == af (deterministic median == af)."""
    return [
        _prec("chr1", start_pos + i, "A", "G", f"0/1:{af}:14,6:20")
        for i in range(n)
    ]


def _recs_with_normal_af(af, n, start_pos=100):
    """n biallelic records; normal AF == af, tumor AF fixed at 0.30."""
    return [
        _prec(
            "chr1", start_pos + i, "A", "G", "0/1:0.30:14,6:20",
            normal_fmt=f"0/0:{af}:10,0:10",
        )
        for i in range(n)
    ]


# --- Strelka2 fixtures ---------------------------------------------------------


def _snv_header(tumor=_TUMOR, normal=_NORMAL):
    return (
        "##fileformat=VCFv4.2\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\t"
        f"{normal}\t{tumor}\n"
    )


def _snv_rec(chrom, pos, ref, alt, tumor_fmt, normal_fmt="0,0:0,0:0,0:0,0"):
    fmt = "AU:CU:GU:TU"
    return f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t.\tPASS\t.\t{fmt}\t{normal_fmt}\t{tumor_fmt}\n"


def _indel_header(tumor=_TUMOR, normal=_NORMAL):
    return (
        "##fileformat=VCFv4.2\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\t"
        f"{normal}\t{tumor}\n"
    )


def _indel_rec(chrom, pos, ref, alt, tumor_fmt, normal_fmt="0,0:0,0"):
    fmt = "TAR:TIR"
    return f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t.\tPASS\t.\t{fmt}\t{normal_fmt}\t{tumor_fmt}\n"


def _write_strelka(path, header, recs):
    path.write_text(header + "".join(recs))
    return path


# --- capture tests -------------------------------------------------------------


def test_concordance_captures_raw_jaccard_and_union(tmp_path):
    # 12 shared + 3 Mutect2-only + 3 Strelka-only -> union 18, raw jaccard 12/18
    # (~0.6667, below the 0.90 warn band; raw, NOT the rounded 0.6667 of the
    # QCResult value). The QCResult list must be byte-identical with/without the
    # out-param.
    shared = _sites(12)
    a = _write_conc_vcf(tmp_path / "mutect2.vcf", shared + _sites(3, start=100_000))
    b = _write_conc_vcf(tmp_path / "strelka.vcf", shared + _sites(3, start=200_000))

    capture: dict[str, dict[str, float]] = {}
    with_capture = evaluate_somatic_concordance([a], [b], capture_metrics=capture)
    plain = evaluate_somatic_concordance([a], [b])

    assert capture["mutect2_vs_strelka2"] == {"value": 12 / 18, "n_shared": 18.0}
    assert with_capture[0].status == "warn"
    assert _dump(with_capture) == _dump(plain)


def test_concordance_too_few_sites_still_captured_raw(tmp_path):
    # union 3 < _MIN_SHARED_SITES -> UNVERIFIED, but the raw values are still
    # captured (spec AC4: a too-few-sites case is captured, never dropped).
    rows = _sites(3)
    a = _write_conc_vcf(tmp_path / "mutect2.vcf", rows)
    b = _write_conc_vcf(tmp_path / "strelka.vcf", rows)

    capture: dict[str, dict[str, float]] = {}
    with_capture = evaluate_somatic_concordance([a], [b], capture_metrics=capture)
    plain = evaluate_somatic_concordance([a], [b])

    assert capture["mutect2_vs_strelka2"] == {"value": 1.0, "n_shared": 3.0}
    assert with_capture[0].status == "unverified"
    assert with_capture[0].value is None
    assert _dump(with_capture) == _dump(plain)


def test_somatic_plausibility_captures_tumor_metrics(tmp_path):
    # median_vaf 0.30 and somatic_variant_count 12 over 12 biallelic AF records,
    # keyed by the resolved tumor sample name (the <check>:<sample> label), with
    # NO pon_applied (non-numeric, never captured).
    vcf = _write_pl_vcf(tmp_path / "mutect2.vcf", _pl_header(), _recs_with_af(0.30, 12))

    capture: dict[str, dict[str, float]] = {}
    with_capture = evaluate_somatic_plausibility(vcf, capture_metrics=capture)
    plain = evaluate_somatic_plausibility(vcf)

    assert capture == {"TUMOR": {"median_vaf": 0.30, "somatic_variant_count": 12}}
    assert "pon_applied" not in capture["TUMOR"]
    assert _dump(with_capture) == _dump(plain)


def test_swap_plausibility_captures_normal_median_vaf(tmp_path):
    # normal median VAF 0.0 keyed by the resolved ##normal_sample= name (NORMAL).
    vcf = _write_pl_vcf(tmp_path / "mutect2.vcf", _pl_header(), _recs_with_normal_af(0.0, 12))

    capture: dict[str, dict[str, float]] = {}
    with_capture = evaluate_swap_plausibility(vcf, capture_metrics=capture)
    plain = evaluate_swap_plausibility(vcf)

    assert capture == {"NORMAL": {"normal_median_vaf": 0.0}}
    assert _dump(with_capture) == _dump(plain)


def test_strelka_vaf_plausibility_captures_median(tmp_path):
    # SNV 6/(14+6)=0.30 and indel 6/(14+6)=0.30 -> pooled median 0.30 exactly,
    # keyed by the literal TUMOR column label.
    snv = _write_strelka(tmp_path / "snv.vcf", _snv_header(), [
        _snv_rec("chr1", 100, "C", "A", "6,7:14,15:0,0:0,0"),
    ])
    indel = _write_strelka(tmp_path / "indel.vcf", _indel_header(), [
        _indel_rec("chr1", 300, "AT", "A", "14,15:6,7"),
    ])

    capture: dict[str, dict[str, float]] = {}
    with_capture = evaluate_strelka_vaf_plausibility(
        snv_vcf=snv, indel_vcf=indel, capture_metrics=capture
    )
    plain = evaluate_strelka_vaf_plausibility(snv_vcf=snv, indel_vcf=indel)

    assert capture == {"TUMOR": {"strelka_median_vaf": 0.30}}
    assert _dump(with_capture) == _dump(plain)


def test_concordance_from_run_captures_both_present(tmp_path):
    # The run-level wrapper passes the out-param through: identical 12-site
    # callers -> raw jaccard 1.0, n_shared float(12).
    run_dir = tmp_path / "run"
    vcfs = _sarek_tree(run_dir)

    capture: dict[str, dict[str, float]] = {}
    with_capture = evaluate_somatic_concordance_from_run(run_dir, vcfs, capture_metrics=capture)
    plain = evaluate_somatic_concordance_from_run(run_dir, vcfs)

    assert capture["mutect2_vs_strelka2"] == {"value": 1.0, "n_shared": 12.0}
    assert _dump(with_capture) == _dump(plain)


def test_concordance_from_run_early_paths_write_nothing(tmp_path):
    # Ambiguous multi-pair layout (reason path) and one-caller-missing (clean
    # skip): the out-param stays untouched.
    run_dir = tmp_path / "run"
    vcfs = _sarek_tree(run_dir, pairs=("T1_vs_N", "T2_vs_N"))
    capture: dict[str, dict[str, float]] = {}
    results = evaluate_somatic_concordance_from_run(run_dir, vcfs, capture_metrics=capture)
    assert capture == {}
    assert results[0].status == "unverified"

    run_dir2 = tmp_path / "run2"
    m_dir = _pair_dir(run_dir2, "mutect2", "T_vs_N")
    vcfs2 = [_write_conc_vcf(m_dir / "T_vs_N.mutect2.somatic.vcf", _sites(12))]
    capture2: dict[str, dict[str, float]] = {}
    assert evaluate_somatic_concordance_from_run(run_dir2, vcfs2, capture_metrics=capture2) == []
    assert capture2 == {}

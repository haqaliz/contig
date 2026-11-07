"""Tests for MSI output parsing and the MSIsensor seam."""

from pathlib import Path

import pytest

from contig.biomarkers.msi import MsiResult, msi_status, parse_msi_output, run_msisensor
from contig.biomarkers.report import build_report

FIX = Path(__file__).parent / "fixtures" / "biomarkers"
VCF = FIX / "variants.vcf"
BED = FIX / "callable.bed"
MSI_OUTPUT = FIX / "msisensor.output"


def test_parse_msi_output_and_thresholds():
    result = parse_msi_output(MSI_OUTPUT, threshold=10.0)
    assert result.total_sites == 2
    assert result.somatic_sites == 2
    assert result.score == 100.0
    assert result.status == "MSI-H"
    assert parse_msi_output(MSI_OUTPUT, threshold=101.0).status == "MSS"


def test_msi_status_comparison():
    assert msi_status("MSI-H", "MSI") == "match"
    assert msi_status("MSI-H", "MSI-H") == "match"
    assert msi_status("MSI-H", "MSS") == "divergent"
    assert msi_status("MSS", "MSS") == "match"
    assert msi_status("MSS", "unknown") == "unverified"
    assert msi_status("MSS", None) == "computed"


def test_run_msisensor_with_a_fake_binary(tmp_path):
    fake = tmp_path / "msisensor"
    fake.write_text(
        "#!/bin/sh\n"
        "while [ $# -gt 0 ]; do\n"
        "  if [ \"$1\" = \"-o\" ]; then out=\"$2\"; shift 2; else shift; fi\n"
        "done\n"
        "printf 'Total_Number_of_Sites\\tNumber_of_Somatic_Sites\\t%%\\n2\\t2\\t100.00\\n' > \"$out\"\n"
    )
    fake.chmod(fake.stat().st_mode | 0o111)
    tumor = tmp_path / "tumor.bam"
    normal = tmp_path / "normal.bam"
    sites = tmp_path / "sites"
    bed = tmp_path / "targets.bed"
    for path in (tumor, normal, sites, bed):
        path.write_text("")
    result = run_msisensor(tumor, normal, sites, bed, output=tmp_path / "out.txt", msisensor_bin=str(fake))
    assert result.score == 100.0
    assert result.status == "MSI-H"
    assert result.tumor_bam == str(tumor)


def test_report_with_an_msi_result():
    result = MsiResult(
        total_sites=2,
        somatic_sites=2,
        score=100.0,
        status="MSI-H",
        threshold=10.0,
        output_path=str(MSI_OUTPUT),
        detail="2/2 somatic sites; threshold 10% => MSI-H",
    )
    report = build_report(VCF, BED, reported_msi="MSI", msi_result=result)
    msi = next(entry for entry in report.entries if entry.name == "MSI")
    assert msi.value == "100.00"
    assert msi.status == "match"
    assert report.meta.msi_threshold == 10.0
    assert any(source.kind == "msi_output" for source in report.meta.sources)


def test_missing_msi_output_is_an_honest_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        parse_msi_output(tmp_path / "missing.txt")

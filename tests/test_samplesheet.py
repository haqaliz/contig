import json

import pytest
from typer.testing import CliRunner

from contig.cli import app
from contig.models import RunRecord
from contig.samplesheet import (
    fastq_paths,
    parse_samplesheet,
    validate_samplesheet,
    validate_somatic_samplesheet,
)


def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text)
    return p


def test_parse_paired_end_two_rows(tmp_path):
    sheet = write(
        tmp_path,
        "samples.csv",
        "sample,fastq_1,fastq_2,strandedness\n"
        "s1,r1_1.fastq.gz,r1_2.fastq.gz,auto\n"
        "s2,r2_1.fastq.gz,r2_2.fastq.gz,forward\n",
    )
    rows = parse_samplesheet(sheet)
    assert len(rows) == 2
    assert rows[0].sample == "s1"
    assert rows[0].fastq_1 == "r1_1.fastq.gz"
    assert rows[0].fastq_2 == "r1_2.fastq.gz"
    assert rows[1].fastq_2 == "r2_2.fastq.gz"


def test_parse_single_end_empty_fastq2_is_none(tmp_path):
    sheet = write(
        tmp_path,
        "samples.csv",
        "sample,fastq_1,fastq_2,strandedness\n"
        "s1,r1_1.fastq.gz,,auto\n",
    )
    rows = parse_samplesheet(sheet)
    assert rows[0].fastq_2 is None


def test_parse_missing_strandedness_column_defaults_auto(tmp_path):
    sheet = write(
        tmp_path,
        "samples.csv",
        "sample,fastq_1,fastq_2\n"
        "s1,r1_1.fastq.gz,r1_2.fastq.gz\n",
    )
    rows = parse_samplesheet(sheet)
    assert rows[0].strandedness == "auto"


def test_parse_missing_fastq1_column_raises(tmp_path):
    sheet = write(
        tmp_path,
        "samples.csv",
        "sample,fastq_2,strandedness\n"
        "s1,r1_2.fastq.gz,auto\n",
    )
    with pytest.raises(ValueError):
        parse_samplesheet(sheet)


def test_validate_wellformed_existing_fastqs_returns_empty(tmp_path):
    write(tmp_path, "r1_1.fastq.gz", "")
    write(tmp_path, "r1_2.fastq.gz", "")
    sheet = write(
        tmp_path,
        "samples.csv",
        "sample,fastq_1,fastq_2,strandedness\n"
        "s1,r1_1.fastq.gz,r1_2.fastq.gz,auto\n",
    )
    assert validate_samplesheet(sheet) == []


def test_validate_missing_fastq_reports_filename(tmp_path):
    write(tmp_path, "r1_1.fastq.gz", "")
    sheet = write(
        tmp_path,
        "samples.csv",
        "sample,fastq_1,fastq_2,strandedness\n"
        "s1,r1_1.fastq.gz,nope_2.fastq.gz,auto\n",
    )
    issues = validate_samplesheet(sheet)
    assert any("nope_2.fastq.gz" in issue for issue in issues)


def test_validate_duplicate_sample_names_reports_duplicate(tmp_path):
    write(tmp_path, "a.fastq.gz", "")
    write(tmp_path, "b.fastq.gz", "")
    sheet = write(
        tmp_path,
        "samples.csv",
        "sample,fastq_1,fastq_2,strandedness\n"
        "dup,a.fastq.gz,,auto\n"
        "dup,b.fastq.gz,,auto\n",
    )
    issues = validate_samplesheet(sheet)
    assert any("dup" in issue and "duplicate" in issue.lower() for issue in issues)


def test_validate_empty_sample_name_reports_issue(tmp_path):
    write(tmp_path, "a.fastq.gz", "")
    sheet = write(
        tmp_path,
        "samples.csv",
        "sample,fastq_1,fastq_2,strandedness\n"
        ",a.fastq.gz,,auto\n",
    )
    issues = validate_samplesheet(sheet)
    assert any("sample" in issue.lower() for issue in issues)
    assert issues != []


def test_validate_empty_fastq1_reports_issue(tmp_path):
    sheet = write(
        tmp_path,
        "samples.csv",
        "sample,fastq_1,fastq_2,strandedness\n"
        "s1,,,auto\n",
    )
    issues = validate_samplesheet(sheet)
    assert any("empty" in issue.lower() and "fastq_1" in issue for issue in issues)


def test_validate_missing_required_column_returns_issue_not_raises(tmp_path):
    sheet = write(
        tmp_path,
        "samples.csv",
        "sample,fastq_2,strandedness\n"
        "s1,r1_2.fastq.gz,auto\n",
    )
    issues = validate_samplesheet(sheet)
    assert len(issues) == 1
    assert "fastq_1" in issues[0]


def test_fastq_paths_paired_end_resolved_against_sheet_dir(tmp_path):
    sheet = write(
        tmp_path,
        "samples.csv",
        "sample,fastq_1,fastq_2,strandedness\n"
        "s1,r1_1.fastq.gz,r1_2.fastq.gz,auto\n",
    )
    paths = fastq_paths(sheet)
    assert paths == [
        (tmp_path / "r1_1.fastq.gz").resolve(),
        (tmp_path / "r1_2.fastq.gz").resolve(),
    ]


# ---------------------------------------------------------------------------
# Phase 3 (M3): sarek tumor/normal somatic sample-sheet validation.
# Columns: patient, sample, status, lane, fastq_1, fastq_2 (status 0=normal,
# 1=tumor). A tumor/normal PAIR = same patient, distinct sample, both a
# status-0 and a status-1 row.
# ---------------------------------------------------------------------------


def _write_fastqs(tmp_path, *names):
    for name in names:
        write(tmp_path, name, "")


def test_somatic_valid_tumor_normal_pair_returns_empty(tmp_path):
    # (a) patient P1 with a normal (status 0) + tumor (status 1) → no issues.
    _write_fastqs(tmp_path, "n_1.fastq.gz", "n_2.fastq.gz", "t_1.fastq.gz", "t_2.fastq.gz")
    sheet = write(
        tmp_path,
        "somatic.csv",
        "patient,sample,status,lane,fastq_1,fastq_2\n"
        "P1,N,0,L1,n_1.fastq.gz,n_2.fastq.gz\n"
        "P1,T,1,L1,t_1.fastq.gz,t_2.fastq.gz\n",
    )
    assert validate_somatic_samplesheet(sheet) == []


def test_somatic_missing_status_column_refuses_with_specific_message(tmp_path):
    # (b) missing `status` column → the specific missing-column message.
    _write_fastqs(tmp_path, "n_1.fastq.gz", "n_2.fastq.gz")
    sheet = write(
        tmp_path,
        "somatic.csv",
        "patient,sample,lane,fastq_1,fastq_2\n"
        "P1,N,L1,n_1.fastq.gz,n_2.fastq.gz\n",
    )
    issues = validate_somatic_samplesheet(sheet)
    assert len(issues) == 1
    assert "status" in issues[0]


def test_somatic_status_not_in_zero_one_refuses_naming_row(tmp_path):
    # (c) status ∉ {0,1} → refuse naming the offending row.
    _write_fastqs(tmp_path, "n_1.fastq.gz", "n_2.fastq.gz", "t_1.fastq.gz", "t_2.fastq.gz")
    sheet = write(
        tmp_path,
        "somatic.csv",
        "patient,sample,status,lane,fastq_1,fastq_2\n"
        "P1,N,0,L1,n_1.fastq.gz,n_2.fastq.gz\n"
        "P1,T,2,L1,t_1.fastq.gz,t_2.fastq.gz\n",
    )
    issues = validate_somatic_samplesheet(sheet)
    assert any("status" in issue and ("row 2" in issue or "T" in issue) for issue in issues)


def test_somatic_unpaired_tumor_refuses_pointing_at_germline(tmp_path):
    # (d) a status:1 patient (P2) with no status:0 → refuse pointing at germline,
    # even though another patient (P1) is a valid pair.
    _write_fastqs(
        tmp_path,
        "n_1.fastq.gz", "n_2.fastq.gz",
        "t_1.fastq.gz", "t_2.fastq.gz",
        "t2_1.fastq.gz", "t2_2.fastq.gz",
    )
    sheet = write(
        tmp_path,
        "somatic.csv",
        "patient,sample,status,lane,fastq_1,fastq_2\n"
        "P1,N,0,L1,n_1.fastq.gz,n_2.fastq.gz\n"
        "P1,T,1,L1,t_1.fastq.gz,t_2.fastq.gz\n"
        "P2,T2,1,L1,t2_1.fastq.gz,t2_2.fastq.gz\n",
    )
    issues = validate_somatic_samplesheet(sheet)
    assert issues != []
    assert any("P2" in issue and "germline" in issue.lower() for issue in issues)


def test_somatic_multi_tumor_relapse_is_allowed(tmp_path):
    # (e) patient with a normal + two distinct tumor rows (relapse) → allowed.
    _write_fastqs(
        tmp_path,
        "n_1.fastq.gz", "n_2.fastq.gz",
        "t1_1.fastq.gz", "t1_2.fastq.gz",
        "t2_1.fastq.gz", "t2_2.fastq.gz",
    )
    sheet = write(
        tmp_path,
        "somatic.csv",
        "patient,sample,status,lane,fastq_1,fastq_2\n"
        "P1,N,0,L1,n_1.fastq.gz,n_2.fastq.gz\n"
        "P1,T1,1,L1,t1_1.fastq.gz,t1_2.fastq.gz\n"
        "P1,T2,1,L1,t2_1.fastq.gz,t2_2.fastq.gz\n",
    )
    assert validate_somatic_samplesheet(sheet) == []


def test_somatic_tumor_only_refuses_pointing_at_germline(tmp_path):
    # (f) no normal anywhere → refuse, message points at germline.
    _write_fastqs(tmp_path, "t_1.fastq.gz", "t_2.fastq.gz")
    sheet = write(
        tmp_path,
        "somatic.csv",
        "patient,sample,status,lane,fastq_1,fastq_2\n"
        "P1,T,1,L1,t_1.fastq.gz,t_2.fastq.gz\n",
    )
    issues = validate_somatic_samplesheet(sheet)
    assert issues != []
    assert any("germline" in issue.lower() for issue in issues)


# ---------------------------------------------------------------------------
# (g) somatic-gating at the CLI: a somatic run uses the somatic validator;
# a germline run still uses the generic validate_samplesheet unchanged.
# ---------------------------------------------------------------------------

_cli = CliRunner()


def _self_heal_spy(captured):
    def spy(**kwargs):
        captured.append(kwargs.get("assay"))
        return RunRecord(
            run_id=kwargs["run_id"],
            pipeline=kwargs["pipeline"],
            pipeline_revision=kwargs["revision"],
            target=kwargs["target"],
            input_checksums={},
        )

    return spy


def _tumor_only_sarek_sheet(tmp_path):
    """A sarek-shaped tumor-only sheet: the somatic validator REFUSES it
    (no matched normal), but the generic validator ACCEPTS it (it has a
    sample + fastq_1 and the FASTQs exist)."""
    _write_fastqs(tmp_path, "t_1.fastq.gz", "t_2.fastq.gz")
    return write(
        tmp_path,
        "sheet.csv",
        "patient,sample,status,lane,fastq_1,fastq_2\n"
        "P1,T,1,L1,t_1.fastq.gz,t_2.fastq.gz\n",
    )


def test_cli_somatic_run_uses_somatic_validator(tmp_path, monkeypatch):
    captured: list = []
    monkeypatch.setattr("contig.cli.self_heal_run", _self_heal_spy(captured))
    sheet = _tumor_only_sarek_sheet(tmp_path)
    result = _cli.invoke(
        app,
        ["run", "--run-id", "s", "--runs-dir", str(tmp_path / "runs"),
         "--pipeline", "nf-core/sarek", "--revision", "3.5.1",
         "--assay", "somatic_variant_calling",
         "--input", str(sheet), "--genome", "GRCh38"],
    )
    # Somatic validator refuses the unpaired/tumor-only sheet before launching.
    assert result.exit_code == 1, result.output
    assert "germline" in result.output.lower()
    assert captured == []  # self_heal_run never reached


def test_cli_germline_run_uses_generic_validator(tmp_path, monkeypatch):
    captured: list = []
    monkeypatch.setattr("contig.cli.self_heal_run", _self_heal_spy(captured))
    sheet = _tumor_only_sarek_sheet(tmp_path)
    # No --assay: sarek derives germline `variant_calling`, which keeps the
    # generic validator; the same tumor-only sarek sheet passes the sheet gate.
    result = _cli.invoke(
        app,
        ["run", "--run-id", "g", "--runs-dir", str(tmp_path / "runs"),
         "--pipeline", "nf-core/sarek", "--revision", "3.5.1",
         "--input", str(sheet), "--genome", "GRCh38"],
    )
    assert result.exit_code == 0, result.output
    assert "germline" not in result.output.lower()
    assert captured == ["variant_calling"]  # generic gate passed, run launched

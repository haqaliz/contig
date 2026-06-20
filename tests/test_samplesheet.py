import pytest

from contig.samplesheet import (
    fastq_paths,
    parse_samplesheet,
    validate_samplesheet,
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

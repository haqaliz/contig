"""Injectable second-quantifier seam (PRD rnaseq-concordance-autorun, Phase 1).

These tests cover the pure argv builder, the pure transcript->gene collapse (the
scientific substance, run for real in CI), and the error paths (missing binary,
missing reads, missing index). kallisto is NEVER executed here: the success
subprocess path is intentionally out of CI, behind a manual gate. Real files only,
via tmp_path.
"""

from pathlib import Path

import pytest

from contig.verification.count_quantifier import (
    SecondQuantifierError,
    collapse_to_gene,
    kallisto_command,
    run_kallisto_quantifier,
    tx2gene_path,
)


def test_kallisto_command_builds_expected_argv(tmp_path):
    r1 = tmp_path / "s1_R1.fastq.gz"
    r2 = tmp_path / "s1_R2.fastq.gz"
    index = tmp_path / "index"
    out_dir = tmp_path / "out"

    argv = kallisto_command([str(r1), str(r2)], str(index), str(out_dir))

    assert argv[0] == "kallisto"
    assert "quant" in argv
    i_idx = argv.index("-i")
    assert argv[i_idx + 1] == str(index)
    o_idx = argv.index("-o")
    assert argv[o_idx + 1] == str(out_dir)
    assert str(r1) in argv
    assert str(r2) in argv


def test_tx2gene_path_resolves_under_index():
    result = tx2gene_path("/some/index/dir")

    assert result == Path("/some/index/dir") / "t2g.txt"


def test_collapse_to_gene_sums_transcripts():
    rows = [
        ("tx1", 10.0),
        ("tx2", 5.0),
        ("tx3", 2.5),
    ]
    t2g = {"tx1": "geneA", "tx2": "geneA", "tx3": "geneB"}

    result = collapse_to_gene(rows, t2g)

    assert result == {"geneA": 15.0, "geneB": 2.5}


def test_collapse_to_gene_drops_unknown_transcript():
    rows = [
        ("tx1", 10.0),
        ("tx_unknown", 100.0),
    ]
    t2g = {"tx1": "geneA"}

    result = collapse_to_gene(rows, t2g)

    assert result == {"geneA": 10.0}
    assert "tx_unknown" not in result.values()


def test_collapse_to_gene_multi_gene_and_tie():
    rows = [
        ("tx1", 3.0),
        ("tx2", 3.0),
        ("tx3", 1.0),
        ("tx4", 1.0),
    ]
    t2g = {"tx1": "geneA", "tx2": "geneB", "tx3": "geneA", "tx4": "geneB"}

    result = collapse_to_gene(rows, t2g)

    assert result == {"geneA": 4.0, "geneB": 4.0}


def test_collapse_to_gene_empty_rows_returns_empty_dict():
    assert collapse_to_gene([], {}) == {}


def _write_samplesheet(tmp_path):
    r1 = tmp_path / "s1_R1.fastq.gz"
    r1.write_text("")
    sheet = tmp_path / "samplesheet.csv"
    sheet.write_text("sample,fastq_1,fastq_2,strandedness\nS1,s1_R1.fastq.gz,,auto\n")
    return sheet


def test_missing_binary_raises(tmp_path, monkeypatch):
    reads = _write_samplesheet(tmp_path)
    index = tmp_path / "index"
    index.mkdir()
    out_dir = tmp_path / "out"

    monkeypatch.setattr(
        "contig.verification.count_quantifier._KALLISTO",
        "kallisto-does-not-exist-xyz",
    )

    with pytest.raises(SecondQuantifierError) as excinfo:
        run_kallisto_quantifier(str(reads), str(index), str(out_dir))

    assert "kallisto" in str(excinfo.value).lower()


def test_missing_reads_raises(tmp_path):
    missing_reads = tmp_path / "nope.csv"
    index = tmp_path / "index"
    index.mkdir()
    out_dir = tmp_path / "out"

    with pytest.raises(SecondQuantifierError) as excinfo:
        run_kallisto_quantifier(str(missing_reads), str(index), str(out_dir))

    assert "reads" in str(excinfo.value).lower()


def test_missing_index_raises(tmp_path):
    reads = _write_samplesheet(tmp_path)
    missing_index = tmp_path / "no-index"
    out_dir = tmp_path / "out"

    with pytest.raises(SecondQuantifierError) as excinfo:
        run_kallisto_quantifier(str(reads), str(missing_index), str(out_dir))

    assert "index" in str(excinfo.value).lower()


def test_malformed_reads_sheet_raises_second_quantifier_error(tmp_path):
    # The sheet exists but is missing the required `fastq_1` column, so
    # `contig.samplesheet.fastq_paths` raises a bare ValueError when parsing it.
    # `run_kallisto_quantifier` must fold that into the one named
    # SecondQuantifierError, never leaking the bare ValueError.
    reads = tmp_path / "malformed.csv"
    reads.write_text("sample,strandedness\nS1,auto\n")
    index = tmp_path / "index"
    index.mkdir()
    out_dir = tmp_path / "out"

    with pytest.raises(SecondQuantifierError):
        run_kallisto_quantifier(str(reads), str(index), str(out_dir))

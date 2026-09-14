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
    _parse_t2g,
    build_kallisto_index,
    collapse_to_gene,
    kallisto_command,
    run_kallisto_quantifier,
    t2g_from_gtf,
    tx2gene_path,
    write_t2g,
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
    # the dropped transcript's count leaks into no gene (values are floats)
    assert 100.0 not in result.values()


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


def test_t2g_from_gtf_parses_gene_and_transcript_attributes(tmp_path):
    gtf = tmp_path / "annotation.gtf"
    gtf.write_text(
        "# a comment line\n"
        'chr1\tsrc\tgene\t100\t200\t.\t+\t.\tgene_id "ENSG1";\n'
        'chr1\tsrc\ttranscript\t100\t200\t.\t+\t.\tgene_id "ENSG1"; '
        'transcript_id "ENST1"; gene_name "TP53";\n'
        'chr1\tsrc\texon\t100\t150\t.\t+\t.\tgene_id "ENSG1"; transcript_id "ENST2";\n'
    )

    mapping, gene_names = t2g_from_gtf(gtf)

    assert mapping == {"ENST1": "ENSG1", "ENST2": "ENSG1"}
    assert gene_names == {"ENST1": "TP53"}


def test_t2g_from_gtf_skips_unmappable_lines(tmp_path):
    gtf = tmp_path / "annotation.gtf"
    gtf.write_text(
        'chr1\tsrc\ttranscript\t100\t200\t.\t+\t.\ttranscript_id "ENST9";\n'
        "chr1\tsrc\tgene\t100\t200\t.\t+\t.\tID=gene1;Parent=chr1\n"
    )

    mapping, gene_names = t2g_from_gtf(gtf)

    assert mapping == {}
    assert gene_names == {}

    empty = tmp_path / "empty.gtf"
    empty.write_text("")

    assert t2g_from_gtf(empty) == ({}, {})


def test_write_t2g_roundtrips_through_parse_t2g(tmp_path):
    index_dir = tmp_path / "index"
    index_dir.mkdir()
    mapping = {"ENST1": "ENSG1", "ENST2": "ENSG1"}
    gene_names = {"ENST1": "TP53"}

    out = write_t2g(index_dir, mapping, gene_names)

    assert out == index_dir / "t2g.txt"
    assert _parse_t2g(out) == mapping
    lines = out.read_text().splitlines()
    assert lines[0] == "ENST1\tENSG1\tTP53"
    assert "ENST2\tENSG1" in lines


def test_build_kallisto_index_argv_and_returns_dir(tmp_path):
    transcriptome = tmp_path / "transcripts.fa"
    transcriptome.write_text(">ENST1\nACGT\n")
    index_dir = tmp_path / "index"
    index_dir.mkdir()
    calls = []

    def fake_builder(argv):
        calls.append(argv)
        return 0

    result = build_kallisto_index(str(transcriptome), index_dir, builder=fake_builder)

    assert result == index_dir
    assert calls == [
        ["kallisto", "index", "-i", str(index_dir / "index.idx"), str(transcriptome)]
    ]


def test_build_kallisto_index_missing_transcriptome_raises(tmp_path):
    index_dir = tmp_path / "index"
    index_dir.mkdir()
    calls = []

    def fake_builder(argv):
        calls.append(argv)
        return 0

    with pytest.raises(SecondQuantifierError) as excinfo:
        build_kallisto_index(str(tmp_path / "missing.fa"), index_dir, builder=fake_builder)

    assert "transcriptome" in str(excinfo.value).lower()
    assert calls == []


def test_build_kallisto_index_nonzero_exit_raises(tmp_path):
    transcriptome = tmp_path / "transcripts.fa"
    transcriptome.write_text(">ENST1\nACGT\n")
    index_dir = tmp_path / "index"
    index_dir.mkdir()

    def fake_builder(argv):
        return 1

    with pytest.raises(SecondQuantifierError):
        build_kallisto_index(str(transcriptome), index_dir, builder=fake_builder)

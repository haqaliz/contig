"""Pre-flight reference-consistency check (FASTA vs GTF contig naming).

Real files only, via pytest tmp_path; no mocks, no tool execution, no network.
Covers AC1-AC5 of the detect-and-gate aspect.
"""

import gzip

from contig.reference_check import (
    check_reference_consistency,
    fasta_contigs,
    gtf_contigs,
)


def _write(path, text):
    path.write_text(text)
    return path


def _write_gz(path, text):
    with gzip.open(path, "wt") as fh:
        fh.write(text)
    return path


# --- fasta_contigs ----------------------------------------------------------


def test_fasta_contigs_first_token_only(tmp_path):
    fa = _write(
        tmp_path / "ref.fa",
        ">chr1 Homo sapiens chromosome 1\nACGT\n>chr2 description here\nTTTT\n",
    )
    assert fasta_contigs(fa) == {"chr1", "chr2"}


def test_fasta_contigs_ignores_non_header_lines(tmp_path):
    fa = _write(
        tmp_path / "ref.fa",
        ">chr1\nACGTACGT\nACGT\n>chr2\nTTTTGGGG\n",
    )
    assert fasta_contigs(fa) == {"chr1", "chr2"}


def test_fasta_contigs_plain_name_no_description(tmp_path):
    fa = _write(tmp_path / "ref.fa", ">1\nACGT\n>2\nTTTT\n")
    assert fasta_contigs(fa) == {"1", "2"}


# --- gtf_contigs ------------------------------------------------------------


def test_gtf_contigs_field0_with_dedupe(tmp_path):
    gtf = _write(
        tmp_path / "genes.gtf",
        "#!genome-build GRCh38\n"
        "1\tsource\tgene\t1\t100\t.\t+\t.\tgene_id \"a\"\n"
        "1\tsource\texon\t1\t50\t.\t+\t.\tgene_id \"a\"\n"
        "2\tsource\tgene\t1\t100\t.\t+\t.\tgene_id \"b\"\n",
    )
    assert gtf_contigs(gtf) == {"1", "2"}


def test_gtf_contigs_skips_comments_and_blanks(tmp_path):
    gtf = _write(
        tmp_path / "genes.gtf",
        "# a comment\n"
        "\n"
        "chr1\tsource\tgene\t1\t100\t.\t+\t.\tgene_id \"a\"\n"
        "\n"
        "#! pragma line\n"
        "chrX\tsource\tgene\t1\t100\t.\t+\t.\tgene_id \"c\"\n",
    )
    assert gtf_contigs(gtf) == {"chr1", "chrX"}


# --- gzip parity (AC4) ------------------------------------------------------


def test_fasta_gzip_parity(tmp_path):
    text = ">chr1 desc\nACGT\n>chr2\nTTTT\n"
    plain = _write(tmp_path / "ref.fa", text)
    gz = _write_gz(tmp_path / "ref.fa.gz", text)
    assert fasta_contigs(gz) == fasta_contigs(plain) == {"chr1", "chr2"}


def test_gtf_gzip_parity(tmp_path):
    text = (
        "1\tsource\tgene\t1\t100\t.\t+\t.\tgene_id \"a\"\n"
        "2\tsource\tgene\t1\t100\t.\t+\t.\tgene_id \"b\"\n"
    )
    plain = _write(tmp_path / "genes.gtf", text)
    gz = _write_gz(tmp_path / "genes.gtf.gz", text)
    assert gtf_contigs(gz) == gtf_contigs(plain) == {"1", "2"}


# --- check_reference_consistency: disjoint (AC1) ---------------------------


def test_disjoint_returns_one_problem_naming_both_sides(tmp_path):
    fa = _write(tmp_path / "ref.fa", ">chr1\nACGT\n>chr2\nTTTT\n")
    gtf = _write(
        tmp_path / "genes.gtf",
        "1\tsrc\tgene\t1\t9\t.\t+\t.\tg\n2\tsrc\tgene\t1\t9\t.\t+\t.\tg\n",
    )
    problems = check_reference_consistency(fa, gtf)
    assert len(problems) == 1
    msg = problems[0]
    # names both sides
    assert "chr1" in msg and "chr2" in msg
    assert "FASTA" in msg and "GTF" in msg
    # chr-prefix asymmetry phrase present
    assert "chr" in msg.lower() and "prefix" in msg.lower()


def test_disjoint_chr_prefix_asymmetry_phrase(tmp_path):
    fa = _write(tmp_path / "ref.fa", ">chr1\nACGT\n>chr2\nTTTT\n")
    gtf = _write(
        tmp_path / "genes.gtf",
        "1\tsrc\tgene\t1\t9\t.\t+\t.\tg\n2\tsrc\tgene\t1\t9\t.\t+\t.\tg\n",
    )
    msg = check_reference_consistency(fa, gtf)[0]
    assert "FASTA uses 'chr'-prefixed names but the GTF does not" in msg


def test_disjoint_chr_prefix_asymmetry_other_direction(tmp_path):
    fa = _write(tmp_path / "ref.fa", ">1\nACGT\n>2\nTTTT\n")
    gtf = _write(
        tmp_path / "genes.gtf",
        "chr1\tsrc\tgene\t1\t9\t.\t+\t.\tg\nchr2\tsrc\tgene\t1\t9\t.\t+\t.\tg\n",
    )
    msg = check_reference_consistency(fa, gtf)[0]
    assert "the GTF uses 'chr'-prefixed names but the FASTA does not" in msg


# --- check_reference_consistency: overlap / subset (AC2) -------------------


def test_overlap_returns_empty(tmp_path):
    fa = _write(tmp_path / "ref.fa", ">chr1\nACGT\n>chr2\nTTTT\n")
    gtf = _write(tmp_path / "genes.gtf", "chr1\tsrc\tgene\t1\t9\t.\t+\t.\tg\n")
    assert check_reference_consistency(fa, gtf) == []


def test_subset_partial_returns_empty(tmp_path):
    fa = _write(tmp_path / "ref.fa", ">chr1\nACGT\n>chr2\nTTTT\n>chrX\nGGGG\n")
    gtf = _write(
        tmp_path / "genes.gtf",
        "chr1\tsrc\tgene\t1\t9\t.\t+\t.\tg\nchr2\tsrc\tgene\t1\t9\t.\t+\t.\tg\n",
    )
    assert check_reference_consistency(fa, gtf) == []


# --- check_reference_consistency: empty/unparseable (AC3) ------------------


def test_empty_fasta_returns_empty(tmp_path):
    fa = _write(tmp_path / "ref.fa", "")
    gtf = _write(tmp_path / "genes.gtf", "1\tsrc\tgene\t1\t9\t.\t+\t.\tg\n")
    assert check_reference_consistency(fa, gtf) == []


def test_empty_gtf_returns_empty(tmp_path):
    fa = _write(tmp_path / "ref.fa", ">chr1\nACGT\n")
    gtf = _write(tmp_path / "genes.gtf", "# only a comment\n\n")
    assert check_reference_consistency(fa, gtf) == []


def test_unparseable_files_return_empty(tmp_path):
    fa = _write(tmp_path / "ref.fa", "no header here\njust sequence\n")
    gtf = _write(tmp_path / "genes.gtf", "#all\n#comments\n")
    assert check_reference_consistency(fa, gtf) == []


# --- message determinism (AC5) ---------------------------------------------


def test_message_is_byte_identical_for_same_inputs(tmp_path):
    fa = _write(tmp_path / "ref.fa", ">chr2\nA\n>chr1\nC\n>chr10\nG\n")
    gtf = _write(
        tmp_path / "genes.gtf",
        "3\tsrc\tgene\t1\t9\t.\t+\t.\tg\n1\tsrc\tgene\t1\t9\t.\t+\t.\tg\n",
    )
    first = check_reference_consistency(fa, gtf)
    second = check_reference_consistency(fa, gtf)
    assert first == second
    assert len(first) == 1


def test_message_uses_sorted_sample(tmp_path):
    fa = _write(tmp_path / "ref.fa", ">chr3\nA\n>chr1\nC\n>chr2\nG\n")
    gtf = _write(
        tmp_path / "genes.gtf",
        "9\tsrc\tgene\t1\t9\t.\t+\t.\tg\n7\tsrc\tgene\t1\t9\t.\t+\t.\tg\n8\tsrc\tgene\t1\t9\t.\t+\t.\tg\n",
    )
    msg = check_reference_consistency(fa, gtf)[0]
    assert "chr1, chr2, chr3" in msg
    assert "7, 8, 9" in msg

"""Tests for the reference-genome resolver.

nf-core/rnaseq needs a reference specified ONE of two mutually-exclusive ways:
an iGenomes ``--genome <key>`` (nf-core resolves/downloads it), or an explicit
local ``--fasta <path> --gtf <path>`` pair. These tests pin the resolver
against real files on disk via ``tmp_path``.
"""

import pytest

from contig.reference import ReferenceError, resolve_reference


def test_genome_mode_returns_genome_param():
    assert resolve_reference(genome="GRCh38") == {"genome": "GRCh38"}


def test_explicit_mode_returns_fasta_and_gtf_paths(tmp_path):
    fasta = tmp_path / "genome.fa"
    gtf = tmp_path / "genes.gtf"
    fasta.write_text(">chr1\nACGT\n")
    gtf.write_text("chr1\tsource\tgene\t1\t4\t.\t+\t.\n")

    assert resolve_reference(fasta=str(fasta), gtf=str(gtf)) == {
        "fasta": str(fasta),
        "gtf": str(gtf),
    }


def test_neither_genome_nor_fasta_raises():
    with pytest.raises(ReferenceError, match="reference is required"):
        resolve_reference()


def test_both_genome_and_fasta_raises():
    with pytest.raises(ReferenceError, match="not both"):
        resolve_reference(genome="GRCh38", fasta="genome.fa")


def test_fasta_without_gtf_raises(tmp_path):
    fasta = tmp_path / "genome.fa"
    fasta.write_text(">chr1\nACGT\n")

    with pytest.raises(ReferenceError, match="gtf"):
        resolve_reference(fasta=str(fasta))


def test_gtf_without_fasta_raises(tmp_path):
    gtf = tmp_path / "genes.gtf"
    gtf.write_text("chr1\tsource\tgene\t1\t4\t.\t+\t.\n")

    with pytest.raises(ReferenceError, match="fasta"):
        resolve_reference(gtf=str(gtf))


def test_nonexistent_fasta_raises_naming_the_missing_file(tmp_path):
    gtf = tmp_path / "genes.gtf"
    gtf.write_text("chr1\tsource\tgene\t1\t4\t.\t+\t.\n")
    missing_fasta = tmp_path / "absent.fa"

    with pytest.raises(ReferenceError, match="absent.fa"):
        resolve_reference(fasta=str(missing_fasta), gtf=str(gtf))

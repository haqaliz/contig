# tests/test_annotation_provenance.py
import gzip
from pathlib import Path

from contig.bundle import compute_annotation_identity
from contig.models import AnnotationProvenance


def _write_gz(path: Path, body: str) -> Path:
    with gzip.open(path, "wt") as fh:
        fh.write(body)
    return path


def test_vep_provenance_parsed(tmp_path):
    body = (
        "##fileformat=VCFv4.2\n"
        '##VEP="v110" time="2026-07-10" cache="/vep/homo_sapiens/110_GRCh38"\n'
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "chr1\t100\t.\tA\tG\t50\tPASS\tCSQ=G|missense_variant\n"
    )
    d = tmp_path / "results" / "annotation"
    d.mkdir(parents=True)
    _write_gz(d / "sample_VEP.ann.vcf.gz", body)
    prov = compute_annotation_identity(tmp_path)
    assert isinstance(prov, list)
    assert len(prov) == 1
    assert isinstance(prov[0], AnnotationProvenance)
    assert prov[0].tool == "VEP"
    assert prov[0].version == "v110"


def test_snpeff_provenance_parsed(tmp_path):
    body = (
        "##fileformat=VCFv4.2\n"
        '##SnpEffVersion="5.1d (build 2022-04-19)"\n'
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "chr1\t100\t.\tA\tG\t50\tPASS\tANN=G|missense_variant\n"
    )
    d = tmp_path / "results"
    d.mkdir(parents=True)
    _write_gz(d / "sample_snpEff.ann.vcf.gz", body)
    prov = compute_annotation_identity(tmp_path)
    assert len(prov) == 1
    assert prov[0].tool == "SnpEff"
    assert prov[0].version.startswith("5.1d")


def test_no_annotated_vcf_returns_none(tmp_path):
    body = (
        "##fileformat=VCFv4.2\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "chr1\t100\t.\tA\tG\t50\tPASS\tDP=30\n"
    )
    d = tmp_path / "results"
    d.mkdir(parents=True)
    _write_gz(d / "plain.vcf.gz", body)
    assert compute_annotation_identity(tmp_path) == []


def test_compute_annotation_identity_pair(tmp_path):
    """M4: a run dir with BOTH a VEP-annotated VCF and a SnpEff-annotated VCF
    must yield TWO provenance entries, deduped by tool, in deterministic order."""
    vep_body = (
        "##fileformat=VCFv4.2\n"
        '##VEP="v110" cache="/vep/homo_sapiens/110_GRCh38"\n'
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "chr1\t100\t.\tA\tG\t50\tPASS\tCSQ=G|missense_variant\n"
    )
    snpeff_body = (
        "##fileformat=VCFv4.2\n"
        '##SnpEffVersion="5.1d (build 2022-04-19)"\n'
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "chr1\t100\t.\tA\tG\t50\tPASS\tANN=G|missense_variant\n"
    )
    d = tmp_path / "results" / "annotation"
    d.mkdir(parents=True)
    _write_gz(d / "sample_VEP.ann.vcf.gz", vep_body)
    _write_gz(d / "sample_snpEff.ann.vcf.gz", snpeff_body)

    prov = compute_annotation_identity(tmp_path)
    assert len(prov) == 2
    tools = sorted(p.tool for p in prov)
    assert tools == ["SnpEff", "VEP"]
    # Deterministic order across repeated calls.
    assert compute_annotation_identity(tmp_path) == prov


def test_compute_annotation_identity_single(tmp_path):
    """VEP-only dir -> exactly one entry."""
    body = (
        "##fileformat=VCFv4.2\n"
        '##VEP="v110" cache="/vep/homo_sapiens/110_GRCh38"\n'
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "chr1\t100\t.\tA\tG\t50\tPASS\tCSQ=G|missense_variant\n"
    )
    d = tmp_path / "results" / "annotation"
    d.mkdir(parents=True)
    _write_gz(d / "sample_VEP.ann.vcf.gz", body)

    prov = compute_annotation_identity(tmp_path)
    assert len(prov) == 1
    assert prov[0].tool == "VEP"


def test_compute_annotation_identity_none(tmp_path):
    """No annotated VCF at all -> empty list, never a fabricated entry."""
    body = (
        "##fileformat=VCFv4.2\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "chr1\t100\t.\tA\tG\t50\tPASS\tDP=30\n"
    )
    d = tmp_path / "results"
    d.mkdir(parents=True)
    _write_gz(d / "plain.vcf.gz", body)
    assert compute_annotation_identity(tmp_path) == []

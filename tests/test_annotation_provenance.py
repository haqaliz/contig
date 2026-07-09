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
    assert isinstance(prov, AnnotationProvenance)
    assert prov.tool == "VEP"
    assert prov.version == "v110"


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
    assert prov.tool == "SnpEff"
    assert prov.version.startswith("5.1d")


def test_no_annotated_vcf_returns_none(tmp_path):
    body = (
        "##fileformat=VCFv4.2\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "chr1\t100\t.\tA\tG\t50\tPASS\tDP=30\n"
    )
    d = tmp_path / "results"
    d.mkdir(parents=True)
    _write_gz(d / "plain.vcf.gz", body)
    assert compute_annotation_identity(tmp_path) is None

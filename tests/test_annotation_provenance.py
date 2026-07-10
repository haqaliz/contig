# tests/test_annotation_provenance.py
import gzip
from pathlib import Path

from contig.bundle import compute_annotation_identity, load_bundle, write_bundle
from contig.models import AnnotationProvenance, ExecutionTarget, RunRecord


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
    # M5: the VEP cache token's basename is captured as the annotation cache/build id.
    assert prov[0].db_version == "110_GRCh38"


def test_vep_cache_token_trailing_slash_and_file_prefix(tmp_path):
    # A cache path with a trailing slash and a file:// prefix must still yield the
    # basename, never a fabricated or malformed value.
    body = (
        "##fileformat=VCFv4.2\n"
        '##VEP="v110" cache="file:///vep/homo_sapiens/110_GRCh38/"\n'
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "chr1\t100\t.\tA\tG\t50\tPASS\tCSQ=G|missense_variant\n"
    )
    d = tmp_path / "results" / "annotation"
    d.mkdir(parents=True)
    _write_gz(d / "sample_VEP.ann.vcf.gz", body)
    prov = compute_annotation_identity(tmp_path)
    assert prov[0].db_version == "110_GRCh38"


def test_vep_without_cache_token_db_version_none(tmp_path):
    # No cache token in the header -> db_version is None, never fabricated.
    body = (
        "##fileformat=VCFv4.2\n"
        '##VEP="v110" time="2026-07-10"\n'
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "chr1\t100\t.\tA\tG\t50\tPASS\tCSQ=G|missense_variant\n"
    )
    d = tmp_path / "results" / "annotation"
    d.mkdir(parents=True)
    _write_gz(d / "sample_VEP.ann.vcf.gz", body)
    prov = compute_annotation_identity(tmp_path)
    assert prov[0].tool == "VEP"
    assert prov[0].version == "v110"
    assert prov[0].db_version is None


def test_snpeff_provenance_parsed(tmp_path):
    body = (
        "##fileformat=VCFv4.2\n"
        '##SnpEffVersion="5.1d (build 2022-04-19)"\n'
        '##SnpEffCmd="SnpEff  GRCh38.105 input.vcf "\n'
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
    # M5: the genome DB token from ##SnpEffCmd is captured as the cache/build id.
    assert prov[0].db_version == "GRCh38.105"


def test_snpeff_genome_version_line_form(tmp_path):
    # The alternative ##SnpEffGenomeVersion= spelling is also supported; the genome
    # token can live on a different header line than ##SnpEffVersion=.
    body = (
        "##fileformat=VCFv4.2\n"
        "##SnpEffGenomeVersion=GRCh38.105\n"
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
    assert prov[0].db_version == "GRCh38.105"


def test_snpeff_without_genome_token_db_version_none(tmp_path):
    # SnpEff header with no genome DB token -> db_version None, never fabricated.
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
    assert prov[0].db_version is None


def test_db_version_round_trips_through_bundle(tmp_path):
    # M5/G4: db_version serializes into run_record.json and reloads unchanged, so
    # the annotation cache/build release is pinned in the reproduce bundle.
    record = RunRecord(
        run_id="run-m5",
        pipeline="nf-core/sarek",
        pipeline_revision="3.5.1",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="/tmp/run"),
        input_checksums={},
        annotation_identity=[
            AnnotationProvenance(tool="VEP", version="v110", db_version="110_GRCh38"),
            AnnotationProvenance(tool="SnpEff", version="5.1d", db_version="GRCh38.105"),
        ],
    )
    write_bundle(record, tmp_path)
    loaded = load_bundle(tmp_path)
    assert loaded.annotation_identity[0].db_version == "110_GRCh38"
    assert loaded.annotation_identity[1].db_version == "GRCh38.105"


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

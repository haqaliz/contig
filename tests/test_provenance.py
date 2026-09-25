"""Tests for the RO-Crate provenance export (PRD contract C).

`to_rocrate` projects a RunRecord into an RO-Crate ro-crate-metadata.json JSON-LD
subset: the run as a Dataset, the pipeline as a SoftwareApplication, inputs and
outputs as File entities carrying their checksums, and the verdict and QC as
properties. Deterministic and offline; nothing is fetched or hashed here.
"""

from contig.models import (
    ExecutionTarget,
    QCResult,
    ReferenceIdentity,
    RunRecord,
    TaskEvent,
)
from contig.provenance import to_rocrate


def _record(**overrides) -> RunRecord:
    base = dict(
        run_id="run-1",
        pipeline="nf-core/rnaseq",
        pipeline_revision="3.26.0",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="w"),
        input_checksums={"samplesheet.csv": "a" * 64, "s1_R1.fastq.gz": "b" * 64},
        output_checksums={"multiqc/multiqc_report.html": "c" * 64},
        parameters={"genome": "GRCh38"},
        container_digests={"star": "sha256:dead"},
        events=[TaskEvent(process="STAR", status="COMPLETED", exit=0)],
        qc_results=[QCResult(check="mapping_rate", status="pass", message="ok", value=92.0)],
    )
    base.update(overrides)
    return RunRecord(**base)


def _ref(**overrides) -> ReferenceIdentity:
    """Local factory for a ReferenceIdentity, defaulting to a minimal iGenomes
    reference. Not a shared fixture -- lives only in this test module.
    """
    base = dict(mode="igenomes", genome="GRCh38")
    base.update(overrides)
    return ReferenceIdentity(**base)


def _by_id(crate: dict, entity_id: str) -> dict:
    for node in crate["@graph"]:
        if node.get("@id") == entity_id:
            return node
    raise AssertionError(f"no entity {entity_id!r} in the crate graph")


def test_crate_declares_the_rocrate_context():
    crate = to_rocrate(_record())
    assert "https://w3id.org/ro/crate/1.1/context" in str(crate["@context"])


def test_crate_has_the_metadata_descriptor():
    crate = to_rocrate(_record())
    descriptor = _by_id(crate, "ro-crate-metadata.json")
    assert descriptor["@type"] == "CreativeWork"
    assert descriptor["about"]["@id"] == "./"


def test_root_dataset_is_the_run():
    crate = to_rocrate(_record())
    root = _by_id(crate, "./")
    assert root["@type"] == "Dataset"
    assert root["identifier"] == "run-1"


def test_pipeline_is_a_software_application_with_version():
    crate = to_rocrate(_record())
    app = _by_id(crate, "nf-core/rnaseq")
    assert app["@type"] == "SoftwareApplication"
    assert app["name"] == "nf-core/rnaseq"
    assert app["version"] == "3.26.0"


def test_inputs_are_file_entities_with_checksums():
    crate = to_rocrate(_record())
    sheet = _by_id(crate, "samplesheet.csv")
    assert sheet["@type"] == "File"
    assert sheet["sha256"] == "a" * 64


def test_outputs_are_file_entities_with_checksums():
    crate = to_rocrate(_record())
    out = _by_id(crate, "multiqc/multiqc_report.html")
    assert out["@type"] == "File"
    assert out["sha256"] == "c" * 64


def test_root_dataset_carries_the_verdict():
    crate = to_rocrate(_record())
    root = _by_id(crate, "./")
    assert root["verdict"] == "pass"


def test_root_dataset_carries_qc_results():
    crate = to_rocrate(_record())
    root = _by_id(crate, "./")
    checks = {qc["check"] for qc in root["qcResults"]}
    assert "mapping_rate" in checks


def test_root_references_the_pipeline_application():
    crate = to_rocrate(_record())
    root = _by_id(crate, "./")
    refs = root.get("hasPart", []) + [root.get("mainEntity", {})]
    ids = {r.get("@id") for r in refs if isinstance(r, dict)}
    assert "nf-core/rnaseq" in ids or root.get("mainEntity", {}).get("@id") == "nf-core/rnaseq"


def test_inputs_and_outputs_are_listed_as_parts():
    crate = to_rocrate(_record())
    root = _by_id(crate, "./")
    part_ids = {p["@id"] for p in root.get("hasPart", [])}
    assert "samplesheet.csv" in part_ids
    assert "multiqc/multiqc_report.html" in part_ids


def test_export_is_deterministic():
    record = _record()
    assert to_rocrate(record) == to_rocrate(record)


def test_unverified_run_reports_unverified_verdict():
    crate = to_rocrate(_record(qc_results=[]))
    root = _by_id(crate, "./")
    assert root["verdict"] == "unverified"


def test_context_maps_sha256_and_localpath():
    crate = to_rocrate(_record())
    assert crate["@context"] == [
        "https://w3id.org/ro/crate/1.1/context",
        {
            "sha256": "http://schema.org/sha256",
            "localPath": "https://w3id.org/ro/terms#localPath",
        },
    ]


def test_graph_unmoved_without_reference_or_annotation():
    """Characterization pin: today's graph, hand-written, for a record with no
    reference_identity and no annotation_identity. The root has no `mentions`
    key. This literal must never be built by calling `to_rocrate` -- it is the
    frozen snapshot that AC1's context change (and every later phase) must not
    disturb for this record shape.
    """
    record = _record()
    expected = [
        {
            "@id": "ro-crate-metadata.json",
            "@type": "CreativeWork",
            "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
            "about": {"@id": "./"},
        },
        {
            "@id": "./",
            "@type": "Dataset",
            "identifier": "run-1",
            "name": "Contig run run-1",
            "mainEntity": {"@id": "nf-core/rnaseq"},
            "hasPart": [
                {"@id": "s1_R1.fastq.gz"},
                {"@id": "samplesheet.csv"},
                {"@id": "multiqc/multiqc_report.html"},
            ],
            "verdict": "pass",
            "parameters": {"genome": "GRCh38"},
            "containerDigests": {"star": "sha256:dead"},
            "qcResults": [
                {
                    "check": "mapping_rate",
                    "status": "pass",
                    "message": "ok",
                    "value": 92.0,
                    "expected_range": None,
                }
            ],
        },
        {
            "@id": "nf-core/rnaseq",
            "@type": "SoftwareApplication",
            "name": "nf-core/rnaseq",
            "version": "3.26.0",
        },
        {"@id": "s1_R1.fastq.gz", "@type": "File", "sha256": "b" * 64},
        {"@id": "samplesheet.csv", "@type": "File", "sha256": "a" * 64},
        {"@id": "multiqc/multiqc_report.html", "@type": "File", "sha256": "c" * 64},
    ]
    crate = to_rocrate(record)
    assert crate["@graph"] == expected
    assert "mentions" not in _by_id(crate, "./")


# --- Reference identity: iGenomes mode -------------------------------------


def test_igenomes_reference_has_genome_key_and_no_fasta_or_gtf():
    record = _record(reference_identity=_ref(mode="igenomes", genome="GRCh38"))
    crate = to_rocrate(record)
    reference = _by_id(crate, "#reference")
    assert reference["identifier"] == {"@id": "#reference-genome-key"}
    assert reference["name"] == "iGenomes GRCh38 reference (downloaded by the pipeline)"
    key = _by_id(crate, "#reference-genome-key")
    assert key["@type"] == "PropertyValue"
    assert key["propertyID"] == "http://edamontology.org/data_2340"
    assert key["name"] == "genome"
    assert key["value"] == "GRCh38"
    ids = {n["@id"] for n in crate["@graph"]}
    assert "#reference-fasta" not in ids
    assert "#reference-gtf" not in ids


def test_igenomes_reference_carries_no_sha256_localpath_or_version():
    record = _record(reference_identity=_ref(mode="igenomes", genome="GRCh38"))
    crate = to_rocrate(record)
    for node in crate["@graph"]:
        if str(node["@id"]).startswith("#reference"):
            assert "sha256" not in node
            assert "localPath" not in node
            assert "version" not in node


def test_igenomes_reference_has_no_haspart_key_when_empty():
    record = _record(reference_identity=_ref(mode="igenomes", genome="GRCh38"))
    crate = to_rocrate(record)
    reference = _by_id(crate, "#reference")
    assert "hasPart" not in reference


def test_igenomes_reference_with_no_genome_omits_null_value_and_name_has_no_none():
    record = _record(reference_identity=_ref(mode="igenomes", genome=None))
    crate = to_rocrate(record)
    reference = _by_id(crate, "#reference")
    assert reference["name"] == "iGenomes reference (downloaded by the pipeline)"
    assert "None" not in reference["name"]
    key = _by_id(crate, "#reference-genome-key")
    assert "value" not in key
    for node in crate["@graph"]:
        if str(node["@id"]).startswith("#reference"):
            for value in node.values():
                assert value is not None


# --- Reference identity: explicit mode, hashes -----------------------------


def test_explicit_reference_fasta_and_gtf_with_hashes():
    ref = _ref(
        mode="explicit",
        genome=None,
        fasta="/data/genome.fa",
        gtf="/data/genes.gtf",
        fasta_sha256="f" * 64,
        gtf_sha256="g" * 64,
    )
    crate = to_rocrate(_record(reference_identity=ref))
    fasta = _by_id(crate, "#reference-fasta")
    assert fasta["@type"] == "File"
    assert fasta["name"] == "genome.fa"
    assert fasta["localPath"] == "/data/genome.fa"
    assert fasta["encodingFormat"] == "http://edamontology.org/format_1929"
    assert fasta["sha256"] == "f" * 64
    gtf = _by_id(crate, "#reference-gtf")
    assert gtf["@type"] == "File"
    assert gtf["name"] == "genes.gtf"
    assert gtf["localPath"] == "/data/genes.gtf"
    assert gtf["encodingFormat"] == "http://edamontology.org/format_2306"
    assert gtf["sha256"] == "g" * 64
    reference = _by_id(crate, "#reference")
    assert reference["name"] == "Explicit reference"
    assert reference["hasPart"] == [{"@id": "#reference-fasta"}, {"@id": "#reference-gtf"}]


def test_explicit_reference_missing_gtf_sha256_omits_the_key():
    ref = _ref(
        mode="explicit",
        genome=None,
        fasta="/data/genome.fa",
        gtf="/data/genes.gtf",
        fasta_sha256="f" * 64,
        gtf_sha256=None,
    )
    crate = to_rocrate(_record(reference_identity=ref))
    gtf = _by_id(crate, "#reference-gtf")
    assert "sha256" not in gtf


def test_explicit_reference_without_gtf_has_no_gtf_node():
    ref = _ref(mode="explicit", genome=None, fasta="/data/genome.fa", gtf=None)
    crate = to_rocrate(_record(reference_identity=ref))
    ids = {n["@id"] for n in crate["@graph"]}
    assert "#reference-gtf" not in ids
    reference = _by_id(crate, "#reference")
    assert reference["hasPart"] == [{"@id": "#reference-fasta"}]


def test_null_annotation_version_has_no_version_key_anywhere():
    ref = _ref(mode="explicit", genome=None, fasta="/data/genome.fa", gtf="/data/genes.gtf")
    crate = to_rocrate(_record(reference_identity=ref))
    for node in crate["@graph"]:
        if str(node["@id"]).startswith("#reference"):
            assert "version" not in node


def test_annotation_version_appears_only_on_gtf_node():
    ref = _ref(
        mode="explicit",
        genome=None,
        fasta="/data/genome.fa",
        gtf="/data/genes.gtf",
        annotation_version="GENCODE 44",
    )
    crate = to_rocrate(_record(reference_identity=ref))
    gtf = _by_id(crate, "#reference-gtf")
    assert gtf["version"] == "GENCODE 44"
    fasta = _by_id(crate, "#reference-fasta")
    assert "version" not in fasta
    reference = _by_id(crate, "#reference")
    assert "version" not in reference


# --- Reference identity: harmonization -------------------------------------


def test_harmonized_gtf_description_and_harmonization_property():
    ref = _ref(
        mode="explicit",
        genome=None,
        fasta="/data/genome.fa",
        gtf="/data/genes.gtf",
        harmonized=True,
        harmonized_direction="add_chr",
    )
    crate = to_rocrate(_record(reference_identity=ref))
    gtf = _by_id(crate, "#reference-gtf")
    assert "harmonized" in gtf["description"]
    assert "add_chr" in gtf["description"]
    reference = _by_id(crate, "#reference")
    assert reference["additionalProperty"] == {"@id": "#reference-harmonization"}
    harmonization = _by_id(crate, "#reference-harmonization")
    assert harmonization["@type"] == "PropertyValue"
    assert harmonization["name"] == "contig_harmonization"
    assert harmonization["value"] == "add_chr"


def test_harmonized_none_direction_omits_value_key():
    ref = _ref(
        mode="explicit",
        genome=None,
        fasta="/data/genome.fa",
        gtf="/data/genes.gtf",
        harmonized=True,
        harmonized_direction=None,
    )
    crate = to_rocrate(_record(reference_identity=ref))
    harmonization = _by_id(crate, "#reference-harmonization")
    assert "value" not in harmonization
    gtf = _by_id(crate, "#reference-gtf")
    assert "harmonized" in gtf["description"]


def test_not_harmonized_has_no_harmonization_node_or_gtf_description():
    ref = _ref(
        mode="explicit",
        genome=None,
        fasta="/data/genome.fa",
        gtf="/data/genes.gtf",
        harmonized=False,
    )
    crate = to_rocrate(_record(reference_identity=ref))
    ids = {n["@id"] for n in crate["@graph"]}
    assert "#reference-harmonization" not in ids
    gtf = _by_id(crate, "#reference-gtf")
    assert "description" not in gtf
    reference = _by_id(crate, "#reference")
    assert "additionalProperty" not in reference


# --- Root `mentions` link ---------------------------------------------------


def test_root_mentions_the_reference():
    crate = to_rocrate(_record(reference_identity=_ref()))
    root = _by_id(crate, "./")
    assert root["mentions"] == [{"@id": "#reference"}]


def test_mentions_key_comes_after_contig_version_in_insertion_order():
    record = _record(
        reference_identity=_ref(),
        nextflow_version="24.10.0",
        contig_version="0.61.0",
    )
    crate = to_rocrate(record)
    root = _by_id(crate, "./")
    assert list(root)[-1] == "mentions"


def test_no_reference_identity_means_no_mentions_key():
    crate = to_rocrate(_record())
    root = _by_id(crate, "./")
    assert "mentions" not in root

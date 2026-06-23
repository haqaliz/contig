"""Tests for the RO-Crate provenance export (PRD contract C).

`to_rocrate` projects a RunRecord into an RO-Crate ro-crate-metadata.json JSON-LD
subset: the run as a Dataset, the pipeline as a SoftwareApplication, inputs and
outputs as File entities carrying their checksums, and the verdict and QC as
properties. Deterministic and offline; nothing is fetched or hashed here.
"""

from contig.models import (
    ExecutionTarget,
    QCResult,
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

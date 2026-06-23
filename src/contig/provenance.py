"""RO-Crate provenance export (PRD contract C).

`to_rocrate` projects a RunRecord into the JSON-LD that an RO-Crate
ro-crate-metadata.json carries: a metadata descriptor, a root Dataset standing in
for the run, the pipeline as a SoftwareApplication, every input and output as a
File entity with its recorded checksum, and the verdict plus QC as properties on
the run. Deterministic and offline: it reads only the record already on disk and
never fetches or re-hashes anything.
"""

from __future__ import annotations

from contig.models import RunRecord

_RO_CRATE_CONTEXT = "https://w3id.org/ro/crate/1.1/context"


def _file_entity(entity_id: str, sha256: str) -> dict:
    """One File node in the crate graph, carrying its recorded sha256 checksum."""
    return {"@id": entity_id, "@type": "File", "sha256": sha256}


def to_rocrate(record: RunRecord) -> dict:
    """Build the RO-Crate ro-crate-metadata.json (JSON-LD) for a run.

    The graph is assembled in a fixed order (descriptor, root, pipeline, inputs,
    outputs) so the export is byte-stable for the same record.
    """
    input_files = [
        _file_entity(name, digest)
        for name, digest in sorted(record.input_checksums.items())
    ]
    output_files = [
        _file_entity(name, digest)
        for name, digest in sorted(record.output_checksums.items())
    ]

    parts = [{"@id": f["@id"]} for f in input_files + output_files]

    root = {
        "@id": "./",
        "@type": "Dataset",
        "identifier": record.run_id,
        "name": f"Contig run {record.run_id}",
        "mainEntity": {"@id": record.pipeline},
        "hasPart": parts,
        "verdict": record.verdict,
        "parameters": {k: str(v) for k, v in sorted(record.parameters.items())},
        "containerDigests": dict(sorted(record.container_digests.items())),
        "qcResults": [
            {
                "check": qc.check,
                "status": qc.status,
                "message": qc.message,
                "value": qc.value,
                "expected_range": qc.expected_range,
            }
            for qc in record.qc_results
        ],
    }
    if record.nextflow_version:
        root["nextflowVersion"] = record.nextflow_version
    if record.contig_version:
        root["contigVersion"] = record.contig_version

    pipeline_app = {
        "@id": record.pipeline,
        "@type": "SoftwareApplication",
        "name": record.pipeline,
        "version": record.pipeline_revision,
    }

    descriptor = {
        "@id": "ro-crate-metadata.json",
        "@type": "CreativeWork",
        "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
        "about": {"@id": "./"},
    }

    graph = [descriptor, root, pipeline_app, *input_files, *output_files]
    return {"@context": _RO_CRATE_CONTEXT, "@graph": graph}

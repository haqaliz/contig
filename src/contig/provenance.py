"""RO-Crate provenance export (PRD contract C).

`to_rocrate` projects a RunRecord into the JSON-LD that an RO-Crate
ro-crate-metadata.json carries: a metadata descriptor, a root Dataset standing in
for the run, the pipeline as a SoftwareApplication, every input and output as a
File entity with its recorded checksum, and the verdict plus QC as properties on
the run. Deterministic and offline: it reads only the record already on disk and
never fetches or re-hashes anything.
"""

from __future__ import annotations

import copy
from pathlib import Path

from contig.models import ReferenceIdentity, RunRecord

_RO_CRATE_CONTEXT = "https://w3id.org/ro/crate/1.1/context"
# The 1.1 context plus a term map for the two properties this module emits that
# aren't in the base RO-Crate vocabulary: `sha256` (a schema.org checksum
# property) and `localPath` (an RO-Crate term for a recorded filesystem path).
_CONTEXT = [
    _RO_CRATE_CONTEXT,
    {
        "sha256": "http://schema.org/sha256",
        "localPath": "https://w3id.org/ro/terms#localPath",
    },
]


def _file_entity(entity_id: str, sha256: str) -> dict:
    """One File node in the crate graph, carrying its recorded sha256 checksum."""
    return {"@id": entity_id, "@type": "File", "sha256": sha256}


# EDAM (bioontology.org/EDAM) format/data IRIs used to type the reference
# entities below. No standard RO-Crate reference-genome type exists, so this
# module builds its own vocabulary on top of schema.org and RO-Crate terms
# (`mentions`, `hasPart`, `identifier`, `PropertyValue`, `encodingFormat`),
# anchored to EDAM where a concept term exists.
_EDAM_GENOME_BUILD = "http://edamontology.org/data_2340"  # Genome build identifier
_EDAM_FASTA = "http://edamontology.org/format_1929"
_EDAM_GTF = "http://edamontology.org/format_2306"


def _drop_none(node: dict) -> dict:
    """Drop keys whose value is None, so no entity ever carries a fabricated null."""
    return {k: v for k, v in node.items() if v is not None}


def _harmonized_gtf_description(direction: str | None) -> str:
    clause = f" (contig names rewritten: {direction})" if direction else ""
    return (
        f"Contig-harmonized copy of the user's annotation{clause}; "
        "not the original file"
    )


def _reference_entities(ref: ReferenceIdentity) -> list[dict]:
    """The `#reference` Dataset and its parts: a genome-key PropertyValue for an
    iGenomes reference, or fasta/gtf File nodes for an explicit one, followed by
    a harmonization PropertyValue when the reference is harmonized.

    `#reference`'s `hasPart` lists only the File parts (fasta, then gtf) that
    exist, and the key is omitted entirely when there are none. Known-site ids
    are appended after the fasta/gtf ids by a later projection step.
    """
    reference = {"@id": "#reference", "@type": "Dataset"}
    parts: list[dict] = []
    file_part_ids: list[dict] = []

    if ref.mode == "igenomes":
        reference["name"] = (
            f"iGenomes {ref.genome} reference (downloaded by the pipeline)"
            if ref.genome is not None
            else "iGenomes reference (downloaded by the pipeline)"
        )
        reference["identifier"] = {"@id": "#reference-genome-key"}
        parts.append(
            _drop_none(
                {
                    "@id": "#reference-genome-key",
                    "@type": "PropertyValue",
                    "propertyID": _EDAM_GENOME_BUILD,
                    "name": "genome",
                    "value": ref.genome,
                }
            )
        )
    else:
        reference["name"] = "Explicit reference"
        if ref.fasta is not None:
            fasta = _drop_none(
                {
                    "@id": "#reference-fasta",
                    "@type": "File",
                    "name": Path(ref.fasta).name,
                    "localPath": ref.fasta,
                    "encodingFormat": _EDAM_FASTA,
                    "sha256": ref.fasta_sha256,
                }
            )
            parts.append(fasta)
            file_part_ids.append({"@id": fasta["@id"]})
        if ref.gtf is not None:
            gtf = {
                "@id": "#reference-gtf",
                "@type": "File",
                "name": Path(ref.gtf).name,
                "localPath": ref.gtf,
                "encodingFormat": _EDAM_GTF,
                "sha256": ref.gtf_sha256,
                "version": ref.annotation_version,
            }
            if ref.harmonized:
                gtf["description"] = _harmonized_gtf_description(
                    ref.harmonized_direction
                )
            gtf = _drop_none(gtf)
            parts.append(gtf)
            file_part_ids.append({"@id": gtf["@id"]})

    if file_part_ids:
        reference["hasPart"] = file_part_ids

    if ref.harmonized:
        reference["additionalProperty"] = {"@id": "#reference-harmonization"}
        parts.append(
            _drop_none(
                {
                    "@id": "#reference-harmonization",
                    "@type": "PropertyValue",
                    "name": "contig_harmonization",
                    "value": ref.harmonized_direction,
                }
            )
        )

    return [reference, *parts]


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

    reference_entities: list[dict] = []
    mentions: list[dict] = []
    if record.reference_identity is not None:
        reference_entities = _reference_entities(record.reference_identity)
        mentions.append({"@id": "#reference"})
    if mentions:
        root["mentions"] = mentions

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

    graph = [
        descriptor,
        root,
        pipeline_app,
        *input_files,
        *output_files,
        *reference_entities,
    ]
    # A fresh copy per call: callers may mutate the returned crate, and that
    # must never corrupt the shared _CONTEXT constant for later calls.
    return {"@context": copy.deepcopy(_CONTEXT), "@graph": graph}

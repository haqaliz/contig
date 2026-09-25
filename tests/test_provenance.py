"""Tests for the RO-Crate provenance export (PRD contract C).

`to_rocrate` projects a RunRecord into an RO-Crate ro-crate-metadata.json JSON-LD
subset: the run as a Dataset, the pipeline as a SoftwareApplication, inputs and
outputs as File entities carrying their checksums, and the verdict and QC as
properties. Deterministic and offline; nothing is fetched or hashed here.
"""

import json

from contig.models import (
    AnnotationProvenance,
    ExecutionTarget,
    KnownSiteIdentity,
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


def _annotation(**overrides) -> AnnotationProvenance:
    """Local factory for an AnnotationProvenance, defaulting to a minimal VEP
    entry. Not a shared fixture -- lives only in this test module.
    """
    base = dict(tool="VEP", version=None, db_version=None, raw_header=None)
    base.update(overrides)
    return AnnotationProvenance(**base)


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
    assert fasta["encodingFormat"] == {"@id": "http://edamontology.org/format_1929"}
    assert fasta["sha256"] == "f" * 64
    gtf = _by_id(crate, "#reference-gtf")
    assert gtf["@type"] == "File"
    assert gtf["name"] == "genes.gtf"
    assert gtf["localPath"] == "/data/genes.gtf"
    assert gtf["encodingFormat"] == {"@id": "http://edamontology.org/format_2306"}
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


# --- Reference identity: known sites -----------------------------------------


def _site(**overrides) -> KnownSiteIdentity:
    """Local factory for a KnownSiteIdentity, defaulting to a minimal explicit
    dbSNP entry. Not a shared fixture -- lives only in this test module.
    """
    base = dict(role="dbsnp", path="/data/dbsnp.vcf.gz", sha256=None, source="explicit")
    base.update(overrides)
    return KnownSiteIdentity(**base)


def test_known_site_explicit_relative_path_is_verbatim_localpath():
    site = _site(role="dbsnp", path="refs/dbsnp.vcf.gz", source="explicit", sha256="d" * 64)
    ref = _ref(mode="explicit", genome=None, fasta=None, gtf=None, known_sites=[site])
    crate = to_rocrate(_record(reference_identity=ref))
    node = _by_id(crate, "#known-sites-dbsnp")
    assert node["@type"] == "File"
    assert node["alternateName"] == "dbsnp"
    assert node["localPath"] == "refs/dbsnp.vcf.gz"
    assert "contentUrl" not in node
    assert node["name"] == "dbsnp.vcf.gz"
    assert node["encodingFormat"] == {"@id": "http://edamontology.org/format_3016"}
    assert node["sha256"] == "d" * 64


def test_known_site_igenomes_s3_path_goes_to_content_url():
    site = _site(
        role="known_snps",
        path=(
            "s3://ngi-igenomes/igenomes/Homo_sapiens/GATK/GRCh38/Annotation/"
            "GATKBundle/dbsnp_146.hg38.vcf.gz"
        ),
        source="igenomes",
    )
    ref = _ref(mode="igenomes", genome="GRCh38", known_sites=[site])
    crate = to_rocrate(_record(reference_identity=ref))
    node = _by_id(crate, "#known-sites-known_snps")
    assert node["contentUrl"] == site.path
    assert "localPath" not in node
    assert node["name"] == "dbsnp_146.hg38.vcf.gz"


def test_known_site_brace_pattern_gets_description_and_no_url_fields():
    pattern = (
        "s3://ngi-igenomes/igenomes/Homo_sapiens/GATK/GRCh38/Annotation/GATKBundle/"
        "{Mills_and_1000G_gold_standard.indels.hg38,"
        "beta/Homo_sapiens_assembly38.known_indels}.vcf.gz"
    )
    site = _site(role="known_indels", path=pattern, source="igenomes")
    ref = _ref(mode="igenomes", genome="GRCh38", known_sites=[site])
    crate = to_rocrate(_record(reference_identity=ref))
    node = _by_id(crate, "#known-sites-known_indels")
    assert "contentUrl" not in node
    assert "localPath" not in node
    assert node["description"] == (
        f"Path pattern as recorded: {pattern}. Expands to more than one file; "
        "not itself a single downloadable file."
    )
    # Basename rule: the text after the last "/" that precedes the opening
    # brace, so the "/" inside the pattern's alternatives is not mistaken for
    # a path separator.
    assert node["name"] == (
        "{Mills_and_1000G_gold_standard.indels.hg38,"
        "beta/Homo_sapiens_assembly38.known_indels}.vcf.gz"
    )


def test_known_site_brace_pattern_real_igenomes_path_no_internal_slash():
    # The exact path Contig records for GATK.GRCh38 known_indels
    # (bundle.py:156's _IGENOMES_KNOWN_SITES entry). Unlike the synthetic
    # `beta/` case above, the brace's alternatives contain no "/" at all --
    # this pins the common real-world form, not just the tricky one.
    pattern = (
        "s3://ngi-igenomes/igenomes/Homo_sapiens/GATK/GRCh38/Annotation/GATKBundle/"
        "{Mills_and_1000G_gold_standard.indels.hg38,"
        "Homo_sapiens_assembly38.known_indels}.vcf.gz"
    )
    site = _site(role="known_indels", path=pattern, source="igenomes")
    ref = _ref(mode="igenomes", genome="GRCh38", known_sites=[site])
    crate = to_rocrate(_record(reference_identity=ref))
    node = _by_id(crate, "#known-sites-known_indels")
    assert node["name"] == (
        "{Mills_and_1000G_gold_standard.indels.hg38,"
        "Homo_sapiens_assembly38.known_indels}.vcf.gz"
    )
    assert node["description"] == (
        f"Path pattern as recorded: {pattern}. Expands to more than one file; "
        "not itself a single downloadable file."
    )
    assert "contentUrl" not in node
    assert "localPath" not in node


def test_known_site_duplicate_role_gets_numeric_suffix():
    sites = [
        _site(role="known_indels", path="/data/a.vcf.gz"),
        _site(role="known_indels", path="/data/b.vcf.gz"),
        _site(role="known_indels", path="/data/c.vcf.gz"),
    ]
    ref = _ref(mode="explicit", genome=None, fasta=None, gtf=None, known_sites=sites)
    crate = to_rocrate(_record(reference_identity=ref))
    ids = {n["@id"] for n in crate["@graph"] if str(n["@id"]).startswith("#known-sites")}
    assert ids == {
        "#known-sites-known_indels",
        "#known-sites-known_indels-1",
        "#known-sites-known_indels-2",
    }


def test_known_site_null_path_has_only_core_keys():
    site = _site(role="dbsnp", path=None, sha256=None)
    ref = _ref(mode="explicit", genome=None, fasta=None, gtf=None, known_sites=[site])
    crate = to_rocrate(_record(reference_identity=ref))
    node = _by_id(crate, "#known-sites-dbsnp")
    assert set(node) == {"@id", "@type", "alternateName", "encodingFormat"}


def test_known_site_null_path_with_sha256_still_omits_it():
    site = _site(role="dbsnp", path=None, sha256="e" * 64)
    ref = _ref(mode="explicit", genome=None, fasta=None, gtf=None, known_sites=[site])
    crate = to_rocrate(_record(reference_identity=ref))
    node = _by_id(crate, "#known-sites-dbsnp")
    assert set(node) == {"@id", "@type", "alternateName", "encodingFormat"}


def test_known_site_ids_listed_in_reference_haspart_after_fasta_and_gtf():
    site = _site(role="dbsnp", path="/data/dbsnp.vcf.gz")
    ref = _ref(
        mode="explicit",
        genome=None,
        fasta="/data/genome.fa",
        gtf="/data/genes.gtf",
        known_sites=[site],
    )
    crate = to_rocrate(_record(reference_identity=ref))
    reference = _by_id(crate, "#reference")
    assert reference["hasPart"] == [
        {"@id": "#reference-fasta"},
        {"@id": "#reference-gtf"},
        {"@id": "#known-sites-dbsnp"},
    ]


def test_known_site_nodes_come_after_harmonization_in_graph_order():
    site = _site(role="dbsnp", path="/data/dbsnp.vcf.gz")
    ref = _ref(
        mode="explicit",
        genome=None,
        fasta="/data/genome.fa",
        gtf="/data/genes.gtf",
        harmonized=True,
        harmonized_direction="add_chr",
        known_sites=[site],
    )
    crate = to_rocrate(_record(reference_identity=ref))
    ids = [n["@id"] for n in crate["@graph"]]
    assert ids.index("#reference-harmonization") < ids.index("#known-sites-dbsnp")


def test_known_sites_in_igenomes_mode_populate_haspart():
    site = _site(role="dbsnp", path="s3://bucket/dbsnp.vcf.gz", source="igenomes")
    ref = _ref(mode="igenomes", genome="GRCh38", known_sites=[site])
    crate = to_rocrate(_record(reference_identity=ref))
    reference = _by_id(crate, "#reference")
    assert reference["hasPart"] == [{"@id": "#known-sites-dbsnp"}]


def test_empty_known_sites_list_gives_no_known_site_nodes():
    ref = _ref(mode="igenomes", genome="GRCh38", known_sites=[])
    crate = to_rocrate(_record(reference_identity=ref))
    ids = {n["@id"] for n in crate["@graph"]}
    assert not any(str(i).startswith("#known-sites") for i in ids)
    reference = _by_id(crate, "#reference")
    assert "hasPart" not in reference


def test_none_known_sites_gives_no_known_site_nodes():
    ref = _ref(mode="igenomes", genome="GRCh38", known_sites=None)
    crate = to_rocrate(_record(reference_identity=ref))
    ids = {n["@id"] for n in crate["@graph"]}
    assert not any(str(i).startswith("#known-sites") for i in ids)


# --- Format entities (RO-Crate 1.1 §27.1) -----------------------------------


def test_file_encoding_format_links_to_a_website_entity():
    ref = _ref(
        mode="explicit",
        genome=None,
        fasta="/data/genome.fa",
        gtf="/data/genes.gtf",
        known_sites=[_site(role="dbsnp", path="/data/dbsnp.vcf.gz")],
    )
    crate = to_rocrate(_record(reference_identity=ref))
    fasta_iri = "http://edamontology.org/format_1929"
    gtf_iri = "http://edamontology.org/format_2306"
    vcf_iri = "http://edamontology.org/format_3016"
    assert _by_id(crate, "#reference-fasta")["encodingFormat"] == {"@id": fasta_iri}
    assert _by_id(crate, "#reference-gtf")["encodingFormat"] == {"@id": gtf_iri}
    assert _by_id(crate, "#known-sites-dbsnp")["encodingFormat"] == {"@id": vcf_iri}
    fasta_entity = _by_id(crate, fasta_iri)
    assert fasta_entity["@type"] == "WebSite"
    assert fasta_entity["name"] == "FASTA"
    assert _by_id(crate, gtf_iri)["name"] == "GTF"
    assert _by_id(crate, vcf_iri)["name"] == "VCF"


def test_format_entities_are_deduplicated_in_first_use_order():
    sites = [
        _site(role="dbsnp", path="/data/dbsnp.vcf.gz"),
        _site(role="known_indels", path="/data/indels.vcf.gz"),
    ]
    ref = _ref(
        mode="explicit",
        genome=None,
        fasta="/data/genome.fa",
        gtf="/data/genes.gtf",
        known_sites=sites,
    )
    crate = to_rocrate(_record(reference_identity=ref))
    website_ids = [n["@id"] for n in crate["@graph"] if n.get("@type") == "WebSite"]
    assert website_ids == [
        "http://edamontology.org/format_1929",
        "http://edamontology.org/format_2306",
        "http://edamontology.org/format_3016",
    ]


def test_no_reference_means_no_format_entities():
    crate = to_rocrate(_record())
    assert not any(n.get("@type") == "WebSite" for n in crate["@graph"])


def test_null_path_known_site_still_counts_as_a_vcf_format_use():
    site = _site(role="dbsnp", path=None, sha256=None)
    ref = _ref(mode="explicit", genome=None, fasta=None, gtf=None, known_sites=[site])
    crate = to_rocrate(_record(reference_identity=ref))
    website_ids = {n["@id"] for n in crate["@graph"] if n.get("@type") == "WebSite"}
    assert website_ids == {"http://edamontology.org/format_3016"}


def test_igenomes_reference_alone_has_no_format_entities():
    ref = _ref(mode="igenomes", genome="GRCh38")
    crate = to_rocrate(_record(reference_identity=ref))
    assert not any(n.get("@type") == "WebSite" for n in crate["@graph"])


# --- Annotation provenance ---------------------------------------------------


def test_two_annotations_are_software_applications_mentioned_in_order():
    entries = [
        _annotation(tool="VEP", version="110", db_version="110_GRCh38"),
        _annotation(tool="SnpEff", version="5.1", db_version="GRCh38.105"),
    ]
    record = _record(reference_identity=_ref(), annotation_identity=entries)
    crate = to_rocrate(record)
    first = _by_id(crate, "#annotation-0")
    second = _by_id(crate, "#annotation-1")
    assert first["@type"] == "SoftwareApplication"
    assert first["name"] == "VEP"
    assert first["version"] == "110"
    assert second["name"] == "SnpEff"
    assert second["version"] == "5.1"
    root = _by_id(crate, "./")
    assert root["mentions"] == [
        {"@id": "#reference"},
        {"@id": "#annotation-0"},
        {"@id": "#annotation-1"},
    ]


def test_annotation_none_version_and_db_version_omit_keys():
    entry = _annotation(tool="VEP", version=None, db_version=None)
    record = _record(annotation_identity=[entry])
    crate = to_rocrate(record)
    node = _by_id(crate, "#annotation-0")
    assert "version" not in node
    assert "description" not in node
    assert node["name"] == "VEP"


def test_annotation_description_reads_cache_build():
    entry = _annotation(tool="VEP", db_version="110_GRCh38")
    record = _record(annotation_identity=[entry])
    crate = to_rocrate(record)
    node = _by_id(crate, "#annotation-0")
    assert node["description"] == "cache/build 110_GRCh38"


def test_raw_header_never_appears_in_the_crate():
    entry = _annotation(
        tool="VEP", version="110", db_version="110_GRCh38", raw_header="##VEP=raw stuff"
    )
    record = _record(annotation_identity=[entry])
    crate = to_rocrate(record)
    assert "raw_header" not in json.dumps(crate)
    assert "raw stuff" not in json.dumps(crate)


def test_annotations_without_reference_give_mentions_of_annotations_only():
    entries = [_annotation(tool="VEP"), _annotation(tool="SnpEff")]
    record = _record(annotation_identity=entries)
    crate = to_rocrate(record)
    root = _by_id(crate, "./")
    assert root["mentions"] == [{"@id": "#annotation-0"}, {"@id": "#annotation-1"}]


def test_graph_order():
    """The `@id` sequence of the graph, for a record with every branch
    populated (explicit reference, both hashes, harmonized, two known sites,
    two annotations), matches the documented order: descriptor, root,
    pipeline, inputs, outputs, reference and its parts, known sites,
    annotations, then the format WebSite entities in first-use order.
    """
    sites = [
        _site(role="dbsnp", path="/data/dbsnp.vcf.gz"),
        _site(role="known_indels", path="/data/indels.vcf.gz"),
    ]
    ref = _ref(
        mode="explicit",
        genome=None,
        fasta="/data/genome.fa",
        gtf="/data/genes.gtf",
        fasta_sha256="f" * 64,
        gtf_sha256="g" * 64,
        harmonized=True,
        harmonized_direction="add_chr",
        known_sites=sites,
    )
    annotations = [
        _annotation(tool="VEP", version="110", db_version="110_GRCh38"),
        _annotation(tool="SnpEff", version="5.1", db_version="GRCh38.105"),
    ]
    record = _record(reference_identity=ref, annotation_identity=annotations)
    crate = to_rocrate(record)
    ids = [n["@id"] for n in crate["@graph"]]
    assert ids == [
        "ro-crate-metadata.json",
        "./",
        "nf-core/rnaseq",
        "s1_R1.fastq.gz",
        "samplesheet.csv",
        "multiqc/multiqc_report.html",
        "#reference",
        "#reference-fasta",
        "#reference-gtf",
        "#reference-harmonization",
        "#known-sites-dbsnp",
        "#known-sites-known_indels",
        "#annotation-0",
        "#annotation-1",
        "http://edamontology.org/format_1929",
        "http://edamontology.org/format_2306",
        "http://edamontology.org/format_3016",
    ]


def test_serialization_is_byte_stable():
    record = _record(
        reference_identity=_ref(known_sites=[_site()]),
        annotation_identity=[_annotation(tool="VEP", version="110", db_version="110_GRCh38")],
    )
    first = json.dumps(to_rocrate(record), indent=2)
    second = json.dumps(to_rocrate(record), indent=2)
    assert first == second


def test_no_none_values_in_new_entities():
    """Walks only the entities this feature adds -- every `#reference*`,
    `#known-sites*` and `#annotation*` node, every format `WebSite` entity,
    plus the root `mentions` list -- for a None value anywhere. It
    deliberately does not walk the whole crate: the pre-existing
    `qcResults[].expected_range` field can be None (frozen by
    test_graph_unmoved_without_reference_or_annotation) and is out of scope
    for this sweep.
    """

    def _assert_no_none(value, path):
        if isinstance(value, dict):
            for key, sub in value.items():
                _assert_no_none(sub, f"{path}.{key}")
        elif isinstance(value, list):
            for i, sub in enumerate(value):
                _assert_no_none(sub, f"{path}[{i}]")
        else:
            assert value is not None, f"None at {path}"

    sites = [_site(role="dbsnp", path="/data/dbsnp.vcf.gz", sha256=None)]
    ref = _ref(
        mode="explicit",
        genome=None,
        fasta="/data/genome.fa",
        gtf=None,
        fasta_sha256=None,
        harmonized=True,
        harmonized_direction=None,
        known_sites=sites,
    )
    annotations = [_annotation(tool="VEP", version=None, db_version=None)]
    record = _record(reference_identity=ref, annotation_identity=annotations)
    crate = to_rocrate(record)
    root = _by_id(crate, "./")
    _assert_no_none(root["mentions"], "mentions")
    for node in crate["@graph"]:
        node_id = str(node.get("@id", ""))
        if (
            node_id.startswith("#reference")
            or node_id.startswith("#known-sites")
            or node_id.startswith("#annotation")
            or node.get("@type") == "WebSite"
        ):
            _assert_no_none(node, node_id)

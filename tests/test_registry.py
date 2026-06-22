"""Tests for the curated pipeline registry.

The registry maps an assay to an ALREADY-VALIDATED pipeline; `match_assay` is a
deterministic keyword matcher (a replaceable rule-based intent provider, not an
LLM and not the moat). These tests pin both the curated data and the rules.
"""

import pytest

from contig.models import PipelineEntry
from contig.registry import (
    REGISTRY,
    UnknownAssayError,
    assay_for_pipeline,
    match_assay,
    select_pipeline,
)


def test_registry_has_rnaseq_entry():
    rnaseq = [e for e in REGISTRY if e.assay == "rnaseq"]
    assert len(rnaseq) == 1
    assert isinstance(rnaseq[0], PipelineEntry)
    assert rnaseq[0].pipeline == "nf-core/rnaseq"


def test_registry_has_variant_calling_entry():
    variant = [e for e in REGISTRY if e.assay == "variant_calling"]
    assert len(variant) == 1
    assert isinstance(variant[0], PipelineEntry)
    assert variant[0].pipeline == "nf-core/sarek"


def test_select_pipeline_returns_sarek_for_variant_calling():
    entry = select_pipeline("variant_calling")
    assert entry.assay == "variant_calling"
    assert entry.pipeline == "nf-core/sarek"
    assert entry in REGISTRY


def test_select_pipeline_returns_entry_for_known_assay():
    entry = select_pipeline("rnaseq")
    assert entry.assay == "rnaseq"
    assert entry.pipeline == "nf-core/rnaseq"
    assert entry in REGISTRY


def test_select_pipeline_raises_for_unknown_assay():
    with pytest.raises(KeyError) as excinfo:
        select_pipeline("unknownassay")
    # The custom error is a KeyError subclass so callers can catch either.
    assert isinstance(excinfo.value, UnknownAssayError)
    assert "unknownassay" in str(excinfo.value)


def test_match_assay_matches_differential_expression_phrase():
    goal = "find differentially expressed genes between treated and control"
    assert match_assay(goal) == "rnaseq"


def test_match_assay_is_case_insensitive():
    assert match_assay("I have RNA-seq data") == "rnaseq"


def test_match_assay_matches_germline_variant_phrase():
    assert match_assay("call germline variants from my WGS") == "variant_calling"


def test_match_assay_matches_variant_calling_synonyms():
    assert match_assay("run a variant caller to find SNVs and indels") == "variant_calling"


def test_match_assay_rnaseq_still_matches_after_adding_variant_calling():
    # No regression: an RNA-seq goal must not get pulled into variant_calling.
    assert match_assay("I have RNA-seq data") == "rnaseq"


def test_match_assay_returns_none_for_unregistered_assay():
    # ChIP-seq has no curated pipeline in the registry, so a ChIP goal matches
    # nothing. (A metagenome goal now routes to the mag assay.)
    assert match_assay("call peaks from my ChIP-seq experiment") is None


def test_match_assay_returns_none_for_empty_goal():
    assert match_assay("") is None


def test_assay_for_pipeline_maps_sarek_to_variant_calling():
    assert assay_for_pipeline("nf-core/sarek") == "variant_calling"


def test_assay_for_pipeline_maps_rnaseq_to_rnaseq():
    assert assay_for_pipeline("nf-core/rnaseq") == "rnaseq"


def test_assay_for_pipeline_returns_none_for_unregistered_pipeline():
    assert assay_for_pipeline("nf-core/unknown") is None


# --- scRNA-seq assay (PRD contract D) ------------------------------------------


def test_registry_has_scrnaseq_entry():
    scrna = [e for e in REGISTRY if e.assay == "scrnaseq"]
    assert len(scrna) == 1
    assert isinstance(scrna[0], PipelineEntry)
    assert scrna[0].pipeline == "nf-core/scrnaseq"
    assert scrna[0].revision  # pinned to a real released tag


def test_select_pipeline_returns_scrnaseq_pipeline():
    entry = select_pipeline("scrnaseq")
    assert entry.assay == "scrnaseq"
    assert entry.pipeline == "nf-core/scrnaseq"


def test_assay_for_pipeline_maps_scrnaseq_pipeline_to_scrnaseq():
    assert assay_for_pipeline("nf-core/scrnaseq") == "scrnaseq"


def test_match_assay_matches_single_cell_phrase():
    assert match_assay("cluster cells from my single cell experiment") == "scrnaseq"


def test_match_assay_matches_scrnaseq_synonyms():
    assert match_assay("analyze scRNA-seq data") == "scrnaseq"


def test_match_assay_matches_tenx_phrase():
    assert match_assay("process my 10x Genomics run") == "scrnaseq"


def test_match_assay_rnaseq_not_pulled_into_scrnaseq():
    # bulk RNA-seq must stay rnaseq even though scrnaseq keywords contain "rna"
    assert match_assay("I have bulk RNA-seq data") == "rnaseq"


# --- methyl-seq assay (PRD contract D) -----------------------------------------


def test_registry_has_methylseq_entry():
    methyl = [e for e in REGISTRY if e.assay == "methylseq"]
    assert len(methyl) == 1
    assert isinstance(methyl[0], PipelineEntry)
    assert methyl[0].pipeline == "nf-core/methylseq"
    assert methyl[0].revision  # pinned to a real released tag


def test_select_pipeline_returns_methylseq_pipeline():
    entry = select_pipeline("methylseq")
    assert entry.assay == "methylseq"
    assert entry.pipeline == "nf-core/methylseq"


def test_assay_for_pipeline_maps_methylseq_pipeline_to_methylseq():
    assert assay_for_pipeline("nf-core/methylseq") == "methylseq"


def test_match_assay_matches_methylation_phrase():
    assert match_assay("measure DNA methylation in my samples") == "methylseq"


def test_match_assay_matches_bisulfite_synonym():
    assert match_assay("process bisulfite sequencing reads") == "methylseq"


def test_match_assay_matches_wgbs_synonym():
    assert match_assay("analyze my WGBS run") == "methylseq"


# --- 16S amplicon assay (PRD contract D) ---------------------------------------


def test_registry_has_ampliseq_entry():
    ampli = [e for e in REGISTRY if e.assay == "ampliseq"]
    assert len(ampli) == 1
    assert isinstance(ampli[0], PipelineEntry)
    assert ampli[0].pipeline == "nf-core/ampliseq"
    assert ampli[0].revision  # pinned to a real released tag


def test_select_pipeline_returns_ampliseq_pipeline():
    entry = select_pipeline("ampliseq")
    assert entry.assay == "ampliseq"
    assert entry.pipeline == "nf-core/ampliseq"


def test_assay_for_pipeline_maps_ampliseq_pipeline_to_ampliseq():
    assert assay_for_pipeline("nf-core/ampliseq") == "ampliseq"


def test_match_assay_matches_16s_phrase():
    assert match_assay("profile the 16S rRNA community") == "ampliseq"


def test_match_assay_matches_amplicon_synonym():
    assert match_assay("run amplicon sequencing analysis") == "ampliseq"


def test_match_assay_matches_microbiome_synonym():
    assert match_assay("characterize the gut microbiome") == "ampliseq"


def test_match_assay_matches_dada2_synonym():
    assert match_assay("denoise reads with DADA2") == "ampliseq"


# --- shotgun metagenomics assay (PRD contract D) -------------------------------


def test_registry_has_mag_entry():
    mag = [e for e in REGISTRY if e.assay == "mag"]
    assert len(mag) == 1
    assert isinstance(mag[0], PipelineEntry)
    assert mag[0].pipeline == "nf-core/mag"
    assert mag[0].revision  # pinned to a real released tag


def test_select_pipeline_returns_mag_pipeline():
    entry = select_pipeline("mag")
    assert entry.assay == "mag"
    assert entry.pipeline == "nf-core/mag"


def test_assay_for_pipeline_maps_mag_pipeline_to_mag():
    assert assay_for_pipeline("nf-core/mag") == "mag"


def test_match_assay_matches_metagenome_phrase():
    assert match_assay("assemble a de novo metagenome") == "mag"


def test_match_assay_matches_metagenomics_synonym():
    assert match_assay("run shotgun metagenomics on this sample") == "mag"


def test_match_assay_matches_mag_synonym():
    assert match_assay("recover MAGs from the assembly") == "mag"


# --- keyword routing does not collide across the new assays ---------------------


def test_metagenome_goal_does_not_misroute_to_ampliseq():
    # "metagenome" must route to mag, not get pulled into the microbiome keyword
    assert match_assay("shotgun metagenome assembly") == "mag"


def test_amplicon_microbiome_goal_routes_to_ampliseq_not_mag():
    # a microbiome amplicon study is ampliseq even though both touch communities
    assert match_assay("16S amplicon microbiome survey") == "ampliseq"

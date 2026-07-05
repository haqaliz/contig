"""Tests for the contig alias equivalence table (mito + GRCh38 scaffolds).

Phase 1 of contig-alias-harmonization: a data-driven lookup that widens
pre-flight FASTA/GTF harmonization beyond the simple `chr`-prefix case to
per-contig aliases (mito chrM<->MT, plus scaffold spellings). This phase only
builds the lookup; no consumer wiring yet.
"""

from contig.contig_aliases import alias_group


def test_mito_mt_group_includes_both_spellings():
    group = alias_group("MT")
    assert {"MT", "M"} <= group


def test_mito_m_group_includes_both_spellings():
    group = alias_group("M")
    assert {"MT", "M"} <= group


def test_seeded_scaffold_ensembl_to_ucsc():
    group = alias_group("GL000191.1")
    assert {"GL000191.1", "chrUn_GL000191v1"} <= group


def test_seeded_scaffold_ucsc_to_ensembl():
    group = alias_group("chrUn_GL000191v1")
    assert {"GL000191.1", "chrUn_GL000191v1"} <= group


def test_unknown_name_maps_to_itself_only():
    assert alias_group("chr7") == frozenset({"chr7"})


def test_alias_group_always_includes_queried_name():
    for name in ("MT", "M", "GL000191.1", "chrUn_GL000191v1", "chr7", "randomXYZ"):
        assert name in alias_group(name)


def test_loader_tolerates_blank_and_comment_lines_and_has_known_pair():
    # Loading the module already parses the bundled TSV; if it crashed on
    # blank/comment lines, importing/using alias_group above would have
    # failed already. This test asserts a known seeded pair is present as
    # positive evidence the loader actually parsed data rows (not just
    # survived comments).
    group = alias_group("KI270711.1")
    assert {"KI270711.1", "chr1_KI270711v1"} <= group

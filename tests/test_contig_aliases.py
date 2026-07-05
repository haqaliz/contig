"""Tests for the contig alias equivalence table (mito + GRCh38 scaffolds).

Phase 1 of contig-alias-harmonization: a data-driven lookup that widens
pre-flight FASTA/GTF harmonization beyond the simple `chr`-prefix case to
per-contig aliases (mito chrM<->MT, plus scaffold spellings). This phase only
builds the lookup; no consumer wiring yet.
"""

import pytest

from contig.contig_aliases import _build_alias_map, alias_group


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


def test_seeded_scaffold_second_pair():
    # Minor coverage: exercise the second seeded scaffold pair too, not just
    # the first one used by the other tests above.
    group = alias_group("GL000192.1")
    assert {"GL000192.1", "chrUn_GL000192v1"} <= group
    assert alias_group("chrUn_GL000192v1") == group


def test_build_alias_map_raises_on_row_without_tab():
    with pytest.raises(ValueError, match="no_tab_here"):
        _build_alias_map(["no_tab_here"])


def test_build_alias_map_raises_on_row_with_empty_field():
    # Trailing tab with nothing after it: two fields, but the second is empty.
    with pytest.raises(ValueError, match="malformed"):
        _build_alias_map(["A\t"])


def test_build_alias_map_raises_on_conflicting_duplicate_name():
    # "A" first pairs with "B", then a later row claims "A" pairs with "C" --
    # a genuine conflict (not a repeat of the same pair), which must be a
    # hard, loud error rather than silently letting "C" win.
    lines = ["A\tB", "A\tC"]
    with pytest.raises(ValueError, match="A"):
        _build_alias_map(lines)


def test_build_alias_map_tolerates_exact_duplicate_pair():
    # An identical row repeated verbatim is harmless (e.g. a future append
    # that accidentally re-adds a row already present) -- dedupe silently
    # rather than erroring, since it doesn't create any conflicting group.
    lines = ["A\tB", "A\tB"]
    alias_map = _build_alias_map(lines)
    assert alias_map["A"] == frozenset({"A", "B"})
    assert alias_map["B"] == frozenset({"A", "B"})


def test_build_alias_map_handles_comments_and_blanks_and_is_symmetric():
    lines = [
        "# a comment",
        "",
        "   ",
        "X\tY",
        "# another comment in the middle",
        "P\tQ",
        "",
    ]
    alias_map = _build_alias_map(lines)

    assert alias_map["X"] == frozenset({"X", "Y"})
    assert alias_map["P"] == frozenset({"P", "Q"})

    # Groups must be symmetric: a name is in another name's group iff the
    # reverse also holds.
    for a, b in (("X", "Y"), ("P", "Q")):
        assert a in alias_map[b]
        assert b in alias_map[a]

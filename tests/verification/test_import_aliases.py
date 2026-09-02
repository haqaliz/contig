"""Tests for the import-name -> PyPI-package alias table.

Phase 1 of reproduce-env-alias-map: a curated lookup (cv2 -> opencv-python,
sklearn -> scikit-learn, ...) so `--allow-install` repairs install the right
PyPI package instead of the verbatim module token. This phase only builds the
data table + pure resolver; no consumer wiring yet.
"""

import pytest

from contig.verification.import_aliases import (
    _build_import_alias_map,
    package_for_import,
)


def test_package_for_import_resolves_common_mismatches():
    assert package_for_import("cv2") == "opencv-python"
    assert package_for_import("sklearn") == "scikit-learn"
    assert package_for_import("PIL") == "pillow"
    assert package_for_import("yaml") == "pyyaml"
    assert package_for_import("Bio") == "biopython"


def test_package_for_import_lookup_is_case_insensitive():
    # The detector is case-preserving ("CV2" arrives as-is); lookup
    # normalizes to lowercase, the resolver never mutates the input elsewhere.
    assert package_for_import("CV2") == "opencv-python"
    assert package_for_import("Cv2") == "opencv-python"
    assert package_for_import("Sklearn") == "scikit-learn"


def test_package_for_import_unknown_name_maps_to_itself():
    # Names the table does not cover keep the honest verbatim default, so
    # install behavior is byte-identical to today for unknown imports.
    assert package_for_import("numpy") == "numpy"
    assert package_for_import("pysam") == "pysam"
    assert package_for_import("totally_unknown_pkg") == "totally_unknown_pkg"


def test_build_import_alias_map_raises_on_row_without_tab():
    with pytest.raises(ValueError, match="malformed"):
        _build_import_alias_map(["no_tab_here"])


def test_build_import_alias_map_raises_on_row_with_empty_field():
    # Trailing tab with nothing after it: two fields, but the second is empty.
    with pytest.raises(ValueError, match="malformed"):
        _build_import_alias_map(["A\t"])


def test_build_import_alias_map_raises_on_row_with_extra_fields():
    with pytest.raises(ValueError, match="malformed"):
        _build_import_alias_map(["A\tB\tC"])


def test_build_import_alias_map_raises_on_conflicting_duplicate():
    # "A" first maps to "B", then a later row claims "A" maps to "C" -- a
    # genuine conflict (not a repeat of the same row), which must be a hard,
    # loud error rather than silently letting "C" win.
    lines = ["A\tB", "A\tC"]
    with pytest.raises(ValueError, match="conflict"):
        _build_import_alias_map(lines)


def test_build_import_alias_map_tolerates_exact_duplicate_row():
    # An identical row repeated verbatim is harmless (e.g. a future append
    # that accidentally re-adds a row already present) -- dedupe silently
    # rather than erroring, since it doesn't create any conflict.
    alias_map = _build_import_alias_map(["A\tB", "A\tB"])
    assert alias_map == {"a": "B"}


def test_build_import_alias_map_skips_blank_and_comment_lines():
    lines = [
        "# import<TAB>package, keys lowercase",
        "",
        "   ",
        "X\tY",
        "# another comment in the middle",
        "P\tQ",
        "",
    ]
    alias_map = _build_import_alias_map(lines)
    assert alias_map == {"x": "Y", "p": "Q"}
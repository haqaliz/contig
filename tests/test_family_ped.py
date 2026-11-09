"""Tests for the PED parser."""

from pathlib import Path

import pytest

from contig.family.ped import load_families, load_ped

FIX = Path(__file__).parent / "fixtures" / "family"
PED = FIX / "trio.ped"


def test_loads_one_family_and_children():
    family = load_ped(PED)
    assert family.family_id == "FAM1"
    assert family.samples == ["CHILD", "FATHER", "MOTHER"]
    assert [child.sample_id for child in family.children] == ["CHILD"]
    assert family.children[0].father_id == "FATHER"
    assert family.children[0].mother_id == "MOTHER"


def test_missing_parent_is_refused(tmp_path):
    path = tmp_path / "bad.ped"
    path.write_text("FAM1 CHILD UNKNOWN MOTHER 1 -9\nFAM1 MOTHER 0 0 2 -9\n")
    with pytest.raises(ValueError, match="missing parent"):
        load_ped(path)


def test_multiple_families_are_refused(tmp_path):
    path = tmp_path / "two.ped"
    path.write_text(
        "FAM1 CHILD FATHER MOTHER 1 -9\nFAM1 FATHER 0 0 1 -9\nFAM1 MOTHER 0 0 2 -9\n"
        "FAM2 C2 F2 M2 1 -9\nFAM2 F2 0 0 1 -9\nFAM2 M2 0 0 2 -9\n"
    )
    with pytest.raises(ValueError, match="one family"):
        load_ped(path)


def test_no_child_is_refused(tmp_path):
    path = tmp_path / "nochild.ped"
    path.write_text("FAM1 A 0 0 1 -9\nFAM1 B 0 0 2 -9\n")
    with pytest.raises(ValueError, match="no child"):
        load_ped(path)


def test_missing_ped_is_an_honest_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_ped(tmp_path / "missing.ped")


def test_load_families_accepts_multiple(tmp_path):
    path = tmp_path / "two.ped"
    path.write_text(
        "FAM1 CHILD FATHER MOTHER 1 -9\nFAM1 FATHER 0 0 1 -9\nFAM1 MOTHER 0 0 2 -9\n"
        "FAM2 C2 F2 M2 1 -9\nFAM2 F2 0 0 1 -9\nFAM2 M2 0 0 2 -9\n"
    )
    families = load_families(path)
    assert [family.family_id for family in families] == ["FAM1", "FAM2"]
    assert [child.sample_id for family in families for child in family.children] == [
        "CHILD", "C2"
    ]

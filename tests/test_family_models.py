"""Tests for family contracts."""

from contig.family.models import Family, FamilyMember


def test_children_are_members_with_both_parents():
    family = Family("F", {
        "CHILD": FamilyMember("CHILD", "FATHER", "MOTHER"),
        "FATHER": FamilyMember("FATHER"),
        "MOTHER": FamilyMember("MOTHER"),
    })
    assert family.samples == ["CHILD", "FATHER", "MOTHER"]
    assert [child.sample_id for child in family.children] == ["CHILD"]


def test_member_defaults():
    member = FamilyMember("S")
    assert member.father_id == "0"
    assert member.mother_id == "0"
    assert member.sex == "0"

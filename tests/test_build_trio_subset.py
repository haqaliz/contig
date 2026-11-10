"""Tests for the GIAB trio-subset genotype remapping."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "build_trio_subset.py"


def _module():
    spec = importlib.util.spec_from_file_location("build_trio_subset", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_multiallelic_gt_is_split_into_two_valid_biallelic_gts():
    remap = _module()._remap_gt
    assert remap("1/2", 1) == "1/0"
    assert remap("1/2", 2) == "0/1"


def test_homozygous_multiallelic_gt_is_remapped_per_alt():
    remap = _module()._remap_gt
    assert remap("2/2", 1) == "0/0"
    assert remap("2/2", 2) == "1/1"


def test_phased_and_missing_genotypes_keep_their_shape():
    remap = _module()._remap_gt
    assert remap("1|2", 2) == "0|1"
    assert remap("./.", 1) == "./."
    assert remap(".|.", 2) == ".|."


def test_haploid_genotype_is_remapped_without_a_separator():
    remap = _module()._remap_gt
    assert remap("2", 1) == "0"
    assert remap("2", 2) == "1"

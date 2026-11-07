"""Tests for run/table loaders and input hashing."""

import json
from pathlib import Path

import pytest

from contig.reporting.inputs import (
    input_record,
    load_readiness_json,
    load_run_bundle,
    load_variants_json,
)
from contig.workspace import RunNotFoundError

FIX = Path(__file__).parent / "fixtures" / "reporting"
RUNS = FIX / "runs"
VARIANTS = FIX / "variants.json"
READINESS = FIX / "readiness.json"


def test_loads_the_run_bundle():
    record = load_run_bundle(RUNS, "r1")
    assert record.run_id == "r1"
    assert record.pipeline == "nf-core/rnaseq"


def test_missing_run_is_a_domain_error(tmp_path):
    with pytest.raises(RunNotFoundError):
        load_run_bundle(tmp_path, "missing")


def test_loads_variants_and_readiness():
    variants = load_variants_json(VARIANTS)
    readiness = load_readiness_json(READINESS)
    assert len(variants["variants"]) == 3
    assert len(readiness["targets"]) == 3


def test_variants_requires_meta_and_variants(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"variants": []}))
    with pytest.raises(ValueError, match="meta"):
        load_variants_json(path)


def test_readiness_requires_targets(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"meta": {}}))
    with pytest.raises(ValueError, match="targets"):
        load_readiness_json(path)


def test_input_record_hashes_the_file():
    record = input_record("variants", VARIANTS, "test")
    assert record.kind == "variants"
    assert len(record.sha256) == 64
    assert record.note == "test"

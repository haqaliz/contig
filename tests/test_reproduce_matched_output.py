"""C8-8: `ClaimResult.matched_output` -- the exact fragment a locator bound.

Strict TDD: written before the field exists. The value is the matched
text/cell/value itself (JSON value, table cell, regex capture), truncated to
`_MAX_MATCHED_OUTPUT_CHARS` with a trailing marker, and never the whole file.
Unlocated and unverified claims carry `None`.

This batch is the one deliberate signature break: adding a field changes the
signed canonical payload, so a signature made before the field existed no
longer verifies against the re-serialized record. Old bundle JSON still LOADS.
"""

from __future__ import annotations

import json
import os

import pytest

from contig.models import ClaimResult, ReproduceRecord
from contig.signing import signing_available
from contig.verification import reproduce as reproduce_module
from contig.verification.reproduce import (
    Claim,
    Locator,
    NotebookLocator,
    PatternLocator,
    TableLocator,
    run_reproduction,
)

_RUN_START = 1_000_000.0


def _run(tmp_path, claims, executor):
    return run_reproduction(
        repo=str(tmp_path),
        run_command="echo run",
        claims=claims,
        executor=executor,
        claims_sha256="a" * 64,
        created_at="2026-07-18T00:00:00Z",
        reproduce_id="rp_1",
        run_started_at=_RUN_START,
    )


def _noop_executor(output: str = ""):
    def executor(argv, repo):
        return 0, output

    return executor


def _write(tmp_path, rel: str, text: str, mtime: float | None = None) -> None:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    if mtime is not None:
        os.utime(p, (mtime, mtime))


# --- model shape + back-compat --------------------------------------------------


def test_matched_output_defaults_to_none():
    claim = ClaimResult(
        id="c1",
        status="unverified",
        claimed=0.9,
        tolerance=0.02,
        message="x",
    )
    assert claim.matched_output is None


def test_claim_result_json_without_matched_output_still_loads():
    legacy = {
        "id": "c1",
        "status": "reproduced",
        "claimed": 0.9,
        "observed": 0.9,
        "tolerance": 0.02,
        "delta": 0.0,
        "message": "ok",
    }
    loaded = ClaimResult.model_validate_json(json.dumps(legacy))
    assert loaded.matched_output is None


# --- every located surface populates it ----------------------------------------


def test_json_locator_matched_output_is_the_extracted_value(tmp_path):
    _write(tmp_path, "out/summary.json", json.dumps({"model": {"auc": 0.9}}), _RUN_START)
    claims = [
        Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "model.auc"))
    ]

    result = _run(tmp_path, claims, _noop_executor()).claim_results[0]

    assert result.status == "reproduced"
    assert result.matched_output == "0.9"


def test_table_locator_matched_output_is_the_cell_text(tmp_path):
    _write(
        tmp_path,
        "out/de.tsv",
        "gene_id\tlog2FoldChange\nENSG1\t-2.31\n",
        _RUN_START,
    )
    claims = [
        Claim(
            id="log2fc",
            value=-2.31,
            tolerance=0.05,
            locator=TableLocator("out/de.tsv", "log2FoldChange", 0, "\t", True),
        )
    ]

    result = _run(tmp_path, claims, _noop_executor()).claim_results[0]

    assert result.status == "reproduced"
    assert result.matched_output == "-2.31"


def test_file_pattern_locator_matched_output_is_the_capture(tmp_path):
    _write(tmp_path, "out/run.log", "Final AUC: 0.91\n", _RUN_START)
    claims = [
        Claim(
            id="auc",
            value=0.91,
            tolerance=0.05,
            locator=PatternLocator("out/run.log", r"AUC: ([0-9.]+)"),
        )
    ]

    result = _run(tmp_path, claims, _noop_executor()).claim_results[0]

    assert result.status == "reproduced"
    assert result.matched_output == "0.91"


def test_stdout_pattern_locator_matched_output_is_the_capture(tmp_path):
    claims = [
        Claim(
            id="auc",
            value=0.91,
            tolerance=0.05,
            locator=PatternLocator(None, r"AUC: ([0-9.]+)"),
        )
    ]

    result = _run(
        tmp_path, claims, _noop_executor("Final AUC: 0.91\n")
    ).claim_results[0]

    assert result.status == "reproduced"
    assert result.matched_output == "0.91"


def test_notebook_locator_matched_output_is_the_capture(tmp_path):
    doc = {
        "cells": [
            {
                "cell_type": "code",
                "source": ["print(auc)\n"],
                "outputs": [
                    {"output_type": "stream", "name": "stdout", "text": ["AUC: 0.91\n"]}
                ],
            }
        ]
    }
    _write(tmp_path, "out.ipynb", json.dumps(doc), _RUN_START)
    claims = [
        Claim(
            id="auc",
            value=0.91,
            tolerance=0.05,
            locator=NotebookLocator("out.ipynb", 0, r"AUC: ([0-9.]+)"),
        )
    ]

    result = _run(tmp_path, claims, _noop_executor()).claim_results[0]

    assert result.status == "reproduced"
    assert result.matched_output == "0.91"


# --- None where nothing was located ---------------------------------------------


def test_unlocated_claim_matched_output_is_none_even_when_reproduced(tmp_path):
    def executor(argv, repo):
        (repo / "results.json").write_text(json.dumps({"auc": 0.9}))
        return 0, ""

    result = _run(tmp_path, [Claim(id="auc", value=0.9, tolerance=0.05)], executor).claim_results[0]

    assert result.status == "reproduced"
    assert result.matched_output is None


def test_unverified_located_claim_matched_output_is_none(tmp_path):
    # No file at all: nothing was extracted, so nothing is fabricated.
    claims = [
        Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/missing.json", "auc"))
    ]

    result = _run(tmp_path, claims, _noop_executor()).claim_results[0]

    assert result.status == "unverified"
    assert result.matched_output is None


# --- truncation -----------------------------------------------------------------


def test_long_capture_is_truncated_with_a_trailing_marker(tmp_path):
    capture = "0." + "1" * 600
    _write(tmp_path, "out/run.log", f"metric: {capture}\n", _RUN_START)
    claims = [
        Claim(
            id="metric",
            value=0.11,
            tolerance=0.5,
            locator=PatternLocator("out/run.log", r"metric: ([0-9.]+)"),
        )
    ]

    result = _run(tmp_path, claims, _noop_executor()).claim_results[0]

    cap = reproduce_module._MAX_MATCHED_OUTPUT_CHARS
    marker = reproduce_module._MATCHED_OUTPUT_TRUNCATED
    assert result.matched_output is not None
    assert result.matched_output.startswith("0.1111")
    assert result.matched_output.endswith("[truncated]")
    assert len(result.matched_output) < len(capture)
    assert len(result.matched_output) <= cap + len(marker)


# --- the disclosed signature break ----------------------------------------------
#
# Adding a field changes the signed canonical payload. A pre-batch bundle still
# LOADS, but a signature made over the pre-batch payload no longer verifies
# once the record is re-serialized by this model. Verification of the stored
# file's own bytes (verify_signature_in_dir) is unchanged -- we deliberately do
# not touch the signer.

requires_signing = pytest.mark.skipif(
    not signing_available(), reason="cryptography not installed"
)


@requires_signing
def test_pre_batch_signed_record_loads_but_no_longer_verifies():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from contig.signing import (
        canonical_bytes_from_raw,
        generate_keypair,
        verify_raw,
        verify_signature,
    )

    private_key, public_key = generate_keypair()
    pre_batch = {
        "reproduce_id": "rp_old",
        "repo": "https://github.com/example/paper",
        "run_command": "python train.py",
        "claims_sha256": "a" * 64,
        "claim_results": [
            {
                "id": "auc",
                "status": "reproduced",
                "claimed": 0.9,
                "observed": 0.9,
                "tolerance": 0.02,
                "delta": 0.0,
                "message": "ok",
            }
        ],
        "exit_code": 0,
        "created_at": "2026-07-18T00:00:00Z",
        "interpreter": "cpython-3.12",
        "tool": "contig",
        "source_url": None,
        "source_commit": None,
        "source_tree_sha256": None,
    }
    old_text = json.dumps(pre_batch, indent=2)
    old_signature = (
        Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key))
        .sign(canonical_bytes_from_raw(old_text))
        .hex()
    )

    # Old JSON still loads (additive defaults).
    loaded = ReproduceRecord.model_validate_json(old_text)
    assert loaded.claim_results[0].matched_output is None

    # But the signature covers the old payload, and the re-serialized record no
    # longer hashes to it: this is the accepted, disclosed break.
    assert verify_raw(old_text, old_signature, public_key) is True
    assert verify_raw(loaded.model_dump_json(indent=2), old_signature, public_key) is False
    assert verify_signature(loaded, old_signature, public_key) is False

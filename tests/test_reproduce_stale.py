"""C8-12: `ClaimResult.stale` -- structured UNVERIFIED-because-stale.

Strict TDD: written before the field exists. A consumer must be able to tell
"the artifact existed but this run did not rewrite it" from "the artifact is
missing/unreadable" without parsing the prose in `message`. The reason itself
stays in `message`; the field is one boolean.

Part of the same deliberate signature-break batch: the field is additive and
defaulted, so old bundle JSON still loads.
"""

from __future__ import annotations

import json
import os

from contig.models import ClaimResult
from contig.verification.reproduce import (
    Claim,
    Locator,
    NotebookLocator,
    PatternLocator,
    TableLocator,
    run_reproduction,
)

_RUN_START = 1_000_000.0


def _run(tmp_path, claims, executor, *, run_started_at=_RUN_START):
    return run_reproduction(
        repo=str(tmp_path),
        run_command="echo run",
        claims=claims,
        executor=executor,
        claims_sha256="a" * 64,
        created_at="2026-07-18T00:00:00Z",
        reproduce_id="rp_1",
        run_started_at=run_started_at,
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


def test_stale_defaults_to_false():
    claim = ClaimResult(
        id="c1",
        status="unverified",
        claimed=0.9,
        tolerance=0.02,
        message="x",
    )
    assert claim.stale is False


def test_claim_result_json_without_stale_still_loads():
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
    assert loaded.stale is False


# --- stale is True exactly when the freshness guard fired -----------------------


def test_stale_json_locator_is_marked_stale(tmp_path):
    _write(tmp_path, "out/summary.json", json.dumps({"auc": 0.9}), _RUN_START - 10)
    claims = [
        Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/summary.json", "auc"))
    ]

    result = _run(tmp_path, claims, _noop_executor()).claim_results[0]

    assert result.status == "unverified"
    assert result.stale is True
    assert "rewritten" in result.message


def test_missing_json_locator_is_not_marked_stale(tmp_path):
    claims = [
        Claim(id="auc", value=0.9, tolerance=0.05, locator=Locator("out/missing.json", "auc"))
    ]

    result = _run(tmp_path, claims, _noop_executor()).claim_results[0]

    assert result.status == "unverified"
    assert result.stale is False


def test_stale_table_locator_is_marked_stale(tmp_path):
    _write(tmp_path, "out/de.tsv", "gene\tlog2fc\nENSG1\t-2.31\n", _RUN_START - 10)
    claims = [
        Claim(
            id="log2fc",
            value=-2.31,
            tolerance=0.05,
            locator=TableLocator("out/de.tsv", "log2fc", 0, "\t", True),
        )
    ]

    result = _run(tmp_path, claims, _noop_executor()).claim_results[0]

    assert result.stale is True


def test_stale_file_pattern_locator_is_marked_stale(tmp_path):
    _write(tmp_path, "out/run.log", "Final AUC: 0.91\n", _RUN_START - 10)
    claims = [
        Claim(
            id="auc",
            value=0.91,
            tolerance=0.05,
            locator=PatternLocator("out/run.log", r"AUC: ([0-9.]+)"),
        )
    ]

    result = _run(tmp_path, claims, _noop_executor()).claim_results[0]

    assert result.stale is True


def test_stdout_pattern_is_never_stale(tmp_path):
    claims = [
        Claim(
            id="auc",
            value=0.91,
            tolerance=0.05,
            locator=PatternLocator(None, r"AUC: ([0-9.]+)"),
        )
    ]

    result = _run(tmp_path, claims, _noop_executor("AUC: 0.91\n")).claim_results[0]

    assert result.status == "reproduced"
    assert result.stale is False


def test_stale_notebook_locator_is_marked_stale(tmp_path):
    doc = {"cells": [{"outputs": [{"output_type": "stream", "name": "stdout", "text": ["AUC: 0.91\n"]}]}]}
    _write(tmp_path, "out.ipynb", json.dumps(doc), _RUN_START - 10)
    claims = [
        Claim(
            id="auc",
            value=0.91,
            tolerance=0.05,
            locator=NotebookLocator("out.ipynb", 0, r"AUC: ([0-9.]+)"),
        )
    ]

    result = _run(tmp_path, claims, _noop_executor()).claim_results[0]

    assert result.stale is True


def test_stale_results_file_marks_unlocated_claims_stale(tmp_path):
    _write(tmp_path, "results.json", json.dumps({"auc": 0.9}), _RUN_START - 10)

    result = _run(tmp_path, [Claim(id="auc", value=0.9, tolerance=0.05)], _noop_executor()).claim_results[0]

    assert result.status == "unverified"
    assert result.stale is True
    assert "rewritten" in result.message


def test_missing_results_file_is_not_marked_stale(tmp_path):
    result = _run(tmp_path, [Claim(id="auc", value=0.9, tolerance=0.05)], _noop_executor()).claim_results[0]

    assert result.status == "unverified"
    assert result.stale is False


def test_nonzero_exit_is_not_marked_stale(tmp_path):
    def executor(argv, repo):
        return 1, "boom"

    result = _run(tmp_path, [Claim(id="auc", value=0.9, tolerance=0.05)], executor).claim_results[0]

    assert result.status == "unverified"
    assert result.stale is False

"""Tests for `contig infer-locators` (reproduce-locator-inference aspect
`cli-command`): the command that sweeps a local repo, matches a draft
claims file's values against the candidates, and writes an updated claims
file (bound claims gain locator keys) plus a review sidecar -- the
matcher's evidence-gated proposals surfaced at the CLI.

Mirrors tests/test_cli_extract_claims.py conventions: no conftest, tmp_path,
CliRunner. The command reads no network and spawns nothing, so no executor
seams are needed. Phase 1 pins the command surface, every pre-flight guard,
and the nothing-written guarantee; matching behavior is pinned in Phase 2.
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from contig.cli import app
from contig.verification.reproduce import load_claims

runner = CliRunner()

# A fixture repo with one numeric leaf ("auc": 0.91) under out/results.json --
# enough for a real sweep + match once the guards pass.
_FIXTURE_CLAIM = {"id": "auc", "value": 0.91}


def _repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "out").mkdir(parents=True)
    (repo / "out" / "results.json").write_text('{"auc": 0.91}\n', encoding="utf-8")
    return repo


def _draft(tmp_path, name="draft.json"):
    path = tmp_path / name
    path.write_text(json.dumps([_FIXTURE_CLAIM]), encoding="utf-8")
    return path


def _metrics(tmp_path, text, name="metrics.json"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# --- Repo-argument guards ----------------------------------------------------


def test_infer_locators_leading_dash_repo_refused(tmp_path):
    draft = _draft(tmp_path)
    out = tmp_path / "updated.json"
    result = runner.invoke(
        app, ["infer-locators", "--out", str(out), "--", "--upload-pack=evil", str(draft)]
    )
    assert result.exit_code == 1
    assert "looks like a command-line option" in result.output
    assert not out.exists()


def test_infer_locators_https_url_repo_refused(tmp_path):
    draft = _draft(tmp_path)
    out = tmp_path / "updated.json"
    result = runner.invoke(
        app,
        ["infer-locators", "https://github.com/org/repo.git", str(draft), "--out", str(out)],
    )
    assert result.exit_code == 1
    assert not out.exists()


def test_infer_locators_doi_repo_refused(tmp_path):
    draft = _draft(tmp_path)
    out = tmp_path / "updated.json"
    result = runner.invoke(
        app, ["infer-locators", "10.1234/abc", str(draft), "--out", str(out)]
    )
    assert result.exit_code == 1
    assert "DOI" in result.output
    assert not out.exists()


def test_infer_locators_non_directory_repo_refused(tmp_path):
    draft = _draft(tmp_path)
    missing = tmp_path / "nope"
    out = tmp_path / "updated.json"
    result = runner.invoke(
        app, ["infer-locators", str(missing), str(draft), "--out", str(out)]
    )
    assert result.exit_code == 1
    assert "No such repo directory" in result.output
    assert not out.exists()


# --- Claims-file guards ------------------------------------------------------


def test_infer_locators_missing_claims_file_refused(tmp_path):
    repo = _repo(tmp_path)
    out = tmp_path / "updated.json"
    result = runner.invoke(
        app, ["infer-locators", str(repo), str(tmp_path / "missing.json"), "--out", str(out)]
    )
    assert result.exit_code == 1
    assert not out.exists()


def test_infer_locators_invalid_claims_refused(tmp_path):
    repo = _repo(tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_text('[{"id": "x"}]', encoding="utf-8")
    out = tmp_path / "updated.json"
    result = runner.invoke(
        app, ["infer-locators", str(repo), str(bad), "--out", str(out)]
    )
    assert result.exit_code == 1
    assert "missing required field 'value'" in result.output
    assert not out.exists()


# --- --out guards ------------------------------------------------------------


def test_infer_locators_out_equals_claims_refused(tmp_path):
    repo = _repo(tmp_path)
    draft = _draft(tmp_path)
    result = runner.invoke(
        app, ["infer-locators", str(repo), str(draft), "--out", str(draft)]
    )
    assert result.exit_code == 1
    assert "--out must not be the claims input path" in result.output
    assert json.loads(draft.read_text()) == [_FIXTURE_CLAIM]


def test_infer_locators_existing_out_without_force_refused(tmp_path):
    repo = _repo(tmp_path)
    draft = _draft(tmp_path)
    out = tmp_path / "updated.json"
    out.write_text("PRE-EXISTING", encoding="utf-8")
    result = runner.invoke(
        app, ["infer-locators", str(repo), str(draft), "--out", str(out)]
    )
    assert result.exit_code == 1
    assert "--force" in result.output
    assert out.read_text(encoding="utf-8") == "PRE-EXISTING"


def test_infer_locators_existing_out_with_force_overwrites(tmp_path):
    repo = _repo(tmp_path)
    draft = _draft(tmp_path)
    out = tmp_path / "updated.json"
    out.write_text("PRE-EXISTING", encoding="utf-8")
    result = runner.invoke(
        app, ["infer-locators", str(repo), str(draft), "--out", str(out), "--force"]
    )
    assert result.exit_code == 0, result.output
    assert load_claims(out)


def test_infer_locators_missing_out_parent_refused(tmp_path):
    repo = _repo(tmp_path)
    draft = _draft(tmp_path)
    out = tmp_path / "no" / "such" / "updated.json"
    result = runner.invoke(
        app, ["infer-locators", str(repo), str(draft), "--out", str(out)]
    )
    assert result.exit_code == 1
    assert "--out directory does not exist" in result.output
    assert not out.exists()


# --- --metrics guards --------------------------------------------------------


def test_infer_locators_metrics_non_json_refused(tmp_path):
    repo = _repo(tmp_path)
    draft = _draft(tmp_path)
    metrics = _metrics(tmp_path, "not json")
    out = tmp_path / "updated.json"
    result = runner.invoke(
        app,
        ["infer-locators", str(repo), str(draft), "--out", str(out), "--metrics", str(metrics)],
    )
    assert result.exit_code == 1
    assert not out.exists()


def test_infer_locators_metrics_array_root_refused(tmp_path):
    repo = _repo(tmp_path)
    draft = _draft(tmp_path)
    metrics = _metrics(tmp_path, "[1, 2]")
    out = tmp_path / "updated.json"
    result = runner.invoke(
        app,
        ["infer-locators", str(repo), str(draft), "--out", str(out), "--metrics", str(metrics)],
    )
    assert result.exit_code == 1
    assert not out.exists()


def test_infer_locators_metrics_non_string_id_refused(tmp_path):
    repo = _repo(tmp_path)
    draft = _draft(tmp_path)
    metrics = _metrics(tmp_path, '{1: ["auc"]}')
    out = tmp_path / "updated.json"
    result = runner.invoke(
        app,
        ["infer-locators", str(repo), str(draft), "--out", str(out), "--metrics", str(metrics)],
    )
    assert result.exit_code == 1
    assert not out.exists()


def test_infer_locators_metrics_non_list_words_refused(tmp_path):
    repo = _repo(tmp_path)
    draft = _draft(tmp_path)
    metrics = _metrics(tmp_path, '{"auc": "auc"}')
    out = tmp_path / "updated.json"
    result = runner.invoke(
        app,
        ["infer-locators", str(repo), str(draft), "--out", str(out), "--metrics", str(metrics)],
    )
    assert result.exit_code == 1
    assert not out.exists()


def test_infer_locators_metrics_empty_string_word_refused(tmp_path):
    repo = _repo(tmp_path)
    draft = _draft(tmp_path)
    metrics = _metrics(tmp_path, '{"auc": ["auc", ""]}')
    out = tmp_path / "updated.json"
    result = runner.invoke(
        app,
        ["infer-locators", str(repo), str(draft), "--out", str(out), "--metrics", str(metrics)],
    )
    assert result.exit_code == 1
    assert not out.exists()


# --- Happy path --------------------------------------------------------------


def test_infer_locators_happy_path_writes_round_trippable_out(tmp_path):
    repo = _repo(tmp_path)
    draft = _draft(tmp_path)
    out = tmp_path / "updated.json"
    result = runner.invoke(
        app, ["infer-locators", str(repo), str(draft), "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    # The load-bearing invariant: whatever we emit loads cleanly through the
    # unchanged reproduce loader.
    loaded = load_claims(out)
    assert len(loaded) == 1
    assert loaded[0].id == "auc"
    assert loaded[0].value == 0.91


def test_infer_locators_without_metrics_echoes_value_only_mode(tmp_path):
    repo = _repo(tmp_path)
    draft = _draft(tmp_path)
    out = tmp_path / "updated.json"
    result = runner.invoke(
        app, ["infer-locators", str(repo), str(draft), "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert "no --metrics given; running value-only (semantic filter off)" in result.output


# --- --dry-run ---------------------------------------------------------------


def test_infer_locators_dry_run_writes_nothing(tmp_path):
    repo = _repo(tmp_path)
    draft = _draft(tmp_path)
    out = tmp_path / "updated.json"
    result = runner.invoke(
        app, ["infer-locators", str(repo), str(draft), "--out", str(out), "--dry-run"]
    )
    assert result.exit_code == 0, result.output
    assert not out.exists()
    assert not (tmp_path / "updated.review.md").exists()
    # Input untouched.
    assert json.loads(draft.read_text()) == [_FIXTURE_CLAIM]
    # No temp file left behind (the mkstemp only happens on the write path).
    assert [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")] == []
    # The full read+sweep+match still happened: the review sidecar prints.
    assert "proposed, pending human review" in result.output


# --- Click-param introspection -----------------------------------------------


def test_infer_locators_registers_args_and_flags():
    import typer

    cmd = typer.main.get_command(app).commands["infer-locators"]
    opts = [o for p in cmd.params for o in (list(p.opts) + list(p.secondary_opts))]
    assert "--out" in opts
    assert "--metrics" in opts
    assert "--force" in opts
    assert "--dry-run" in opts
    arg_names = [p.name for p in cmd.params if p.param_type_name == "argument"]
    assert "repo" in arg_names
    assert "claims" in arg_names


# --- Phase 2: matching behavior + output contract ----------------------------


def _json_repo(base, text):
    """A fixture repo holding one JSON artifact at <base>/out/results.json."""
    (base / "out").mkdir(parents=True)
    (base / "out" / "results.json").write_text(text, encoding="utf-8")
    return base


def _table_repo(base, text):
    """A fixture repo holding one TSV artifact at <base>/de.tsv."""
    base.mkdir(parents=True)
    (base / "de.tsv").write_text(text, encoding="utf-8")
    return base


def _dense_recovery_repo(base):
    """The M10 gate fixture: one value at the same scale in four columns, so
    the value-only matcher can never name a site (mirrors the matcher's own
    `_dense_recovery_fixture` in tests/verification/test_locator_match.py)."""
    base.mkdir(parents=True)
    (base / "de.tsv").write_text(
        "recovery\tprecision\trecall\tf1\n0.91\t0.91\t0.91\t0.91\n",
        encoding="utf-8",
    )
    return base


def _draft_claims(tmp_path, claims, name="draft.json"):
    path = tmp_path / name
    path.write_text(json.dumps(claims), encoding="utf-8")
    return path


def test_infer_locators_json_match_adds_from_path_others_semantically_identical(tmp_path):
    repo = _json_repo(tmp_path / "repo", '{"auc": 0.9134}\n')
    draft_claims = [
        {"id": "auc", "value": 0.91, "tolerance": 0.01},
        {"id": "other", "value": 0.42, "tolerance": 0.05},
    ]
    draft = _draft_claims(tmp_path, draft_claims)
    out = tmp_path / "updated.json"
    result = runner.invoke(
        app, ["infer-locators", str(repo), str(draft), "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written[0] == {
        "id": "auc",
        "value": 0.91,
        "tolerance": 0.01,
        "from": "out/results.json",
        "path": "auc",
    }
    # Semantic identity, not bytes: the non-bound claim keeps exactly its
    # {id, value, tolerance} keys/values from the input dict.
    assert written[1] == draft_claims[1]


def test_infer_locators_table_match_header_mode_keys_no_delimiter(tmp_path):
    repo = _table_repo(
        tmp_path / "repo", "gene_id\tlog2FoldChange\tpadj\ngene1\t2.1\t0.05\n"
    )
    draft = _draft_claims(tmp_path, [{"id": "fc", "value": 2.1, "tolerance": 0.1}])
    out = tmp_path / "updated.json"
    result = runner.invoke(
        app, ["infer-locators", str(repo), str(draft), "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    (claim,) = json.loads(out.read_text(encoding="utf-8"))
    assert claim == {
        "id": "fc",
        "value": 2.1,
        "tolerance": 0.1,
        "from": "de.tsv",
        "column": "log2FoldChange",
        "row": 0,
        "header": True,
    }
    assert "delimiter" not in claim


def test_infer_locators_ambiguous_refused_no_candidates_counts_no_locator_keys(tmp_path):
    repo = _json_repo(tmp_path / "repo", '{"x": 0.9134, "y": 0.9134}\n')
    draft_claims = [
        {"id": "amb", "value": 0.91, "tolerance": 0.01},
        {"id": "ref", "value": 2.0, "tolerance": 0.1},
        {"id": "miss", "value": 0.1234, "tolerance": 0.05},
    ]
    draft = _draft_claims(tmp_path, draft_claims)
    out = tmp_path / "updated.json"
    result = runner.invoke(
        app, ["infer-locators", str(repo), str(draft), "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert "bound=0" in result.output
    assert "ambiguous=1" in result.output
    assert "refused_low_information=1" in result.output
    assert "no_candidates=1" in result.output
    assert "skipped 0 artifact(s)" in result.output
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written == draft_claims


def test_infer_locators_zero_binds_still_writes_locator_less_out(tmp_path):
    repo = _json_repo(tmp_path / "repo", '{"x": 0.9134, "y": 0.9134}\n')
    draft_claims = [{"id": "amb", "value": 0.91, "tolerance": 0.01}]
    draft = _draft_claims(tmp_path, draft_claims)
    out = tmp_path / "updated.json"
    result = runner.invoke(
        app, ["infer-locators", str(repo), str(draft), "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert json.loads(out.read_text(encoding="utf-8")) == draft_claims
    assert "bound=0" in result.output


def test_infer_locators_metrics_binds_claim_value_only_leaves_ambiguous(tmp_path):
    repo = _dense_recovery_repo(tmp_path / "repo")
    draft_claims = [{"id": "r", "value": 0.91, "tolerance": 0.05}]
    draft = _draft_claims(tmp_path, draft_claims)
    # Without --metrics the same claim is ambiguous: four columns hold 0.91.
    out_value_only = tmp_path / "value_only.json"
    result = runner.invoke(
        app, ["infer-locators", str(repo), str(draft), "--out", str(out_value_only)]
    )
    assert result.exit_code == 0, result.output
    assert "ambiguous=1" in result.output
    (claim,) = json.loads(out_value_only.read_text(encoding="utf-8"))
    assert claim == draft_claims[0]
    # With --metrics the M10 semantic filter narrows the pool to the
    # recovery column and the claim binds with the full table locator.
    metrics = _metrics(tmp_path, json.dumps({"r": ["recovery"]}), name="metrics.json")
    out_semantic = tmp_path / "semantic.json"
    result = runner.invoke(
        app,
        [
            "infer-locators",
            str(repo),
            str(draft),
            "--out",
            str(out_semantic),
            "--metrics",
            str(metrics),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "bound=1" in result.output
    (claim,) = json.loads(out_semantic.read_text(encoding="utf-8"))
    assert claim == {
        "id": "r",
        "value": 0.91,
        "tolerance": 0.05,
        "from": "de.tsv",
        "column": "recovery",
        "row": 0,
        "header": True,
    }


def test_infer_locators_metrics_unknown_id_falls_back_echo_names_unmatched(tmp_path):
    repo = _json_repo(tmp_path / "repo", '{"auc": 0.9134}\n')
    draft_claims = [{"id": "auc", "value": 0.91, "tolerance": 0.01}]
    draft = _draft_claims(tmp_path, draft_claims)
    metrics = _metrics(
        tmp_path, json.dumps({"auc": ["recovery"], "ghost": ["auc"]}), name="metrics.json"
    )
    out = tmp_path / "updated.json"
    result = runner.invoke(
        app,
        [
            "infer-locators",
            str(repo),
            str(draft),
            "--out",
            str(out),
            "--metrics",
            str(metrics),
        ],
    )
    assert result.exit_code == 0, result.output
    # The unknown id is not an error: "ghost" has no claim, so the draft
    # claim still processes (its words matched nothing, the value-only
    # fallback binds) -- but the staleness is visible in the echo.
    (claim,) = json.loads(out.read_text(encoding="utf-8"))
    assert claim == {
        "id": "auc",
        "value": 0.91,
        "tolerance": 0.01,
        "from": "out/results.json",
        "path": "auc",
    }
    assert "matched 1 claim id(s), unmatched 1 claim id(s)" in result.output


def test_infer_locators_universal_round_trip_over_fixture_corpus(tmp_path):
    scenarios = [
        (
            "json",
            _json_repo(tmp_path / "s1", '{"auc": 0.9134}\n'),
            [{"id": "auc", "value": 0.91, "tolerance": 0.01}],
            None,
        ),
        (
            "table",
            _table_repo(
                tmp_path / "s2", "gene_id\tlog2FoldChange\tpadj\ngene1\t2.1\t0.05\n"
            ),
            [{"id": "fc", "value": 2.1, "tolerance": 0.1}],
            None,
        ),
        (
            "zero-binds",
            _json_repo(tmp_path / "s3", '{"x": 0.9134, "y": 0.9134}\n'),
            [{"id": "amb", "value": 0.91, "tolerance": 0.01}],
            None,
        ),
        (
            "metrics",
            _dense_recovery_repo(tmp_path / "s4"),
            [{"id": "r", "value": 0.91, "tolerance": 0.05}],
            {"r": ["recovery"]},
        ),
        (
            "misses",
            _json_repo(tmp_path / "s5", '{"auc": 0.9134}\n'),
            [
                {"id": "ref", "value": 2.0, "tolerance": 0.1},
                {"id": "miss", "value": 0.1234, "tolerance": 0.05},
            ],
            None,
        ),
    ]
    for tag, repo, claims, metrics_map in scenarios:
        draft = tmp_path / f"draft_{tag}.json"
        draft.write_text(json.dumps(claims), encoding="utf-8")
        out = tmp_path / f"out_{tag}.json"
        args = ["infer-locators", str(repo), str(draft), "--out", str(out)]
        if metrics_map is not None:
            metrics = tmp_path / f"metrics_{tag}.json"
            metrics.write_text(json.dumps(metrics_map), encoding="utf-8")
            args += ["--metrics", str(metrics)]
        result = runner.invoke(app, args)
        assert result.exit_code == 0, result.output
        # The load-bearing invariant: whatever we emit loads cleanly through
        # the unchanged reproduce loader, across the whole fixture corpus.
        assert load_claims(out), tag


def test_infer_locators_dry_run_deep_pin_prints_sidecar_writes_nothing(tmp_path):
    repo = _json_repo(tmp_path / "repo", '{"auc": 0.9134}\n')
    draft_claims = [{"id": "auc", "value": 0.91, "tolerance": 0.01}]
    draft = _draft_claims(tmp_path, draft_claims)
    input_before = draft.read_bytes()
    out = tmp_path / "updated.json"
    result = runner.invoke(
        app, ["infer-locators", str(repo), str(draft), "--out", str(out), "--dry-run"]
    )
    assert result.exit_code == 0, result.output
    assert not out.exists()
    assert not (tmp_path / "updated.review.md").exists()
    assert draft.read_bytes() == input_before
    assert [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")] == []
    # The full read+sweep+match happened and the matcher's per-claim sidecar
    # lines print: the bound line names the site and the R6 disclosure.
    assert (
        "claim auc: bound at out/results.json (path=auc) at raw; depends on"
        in result.output
    )


def test_infer_locators_sidecar_matcher_lines_skips_section_mode_note(tmp_path):
    repo = _json_repo(tmp_path / "repo", '{"auc": 0.9134}\n')
    (repo / "linked").symlink_to(repo / "out", target_is_directory=True)
    draft = _draft_claims(tmp_path, [{"id": "auc", "value": 0.91, "tolerance": 0.01}])
    out = tmp_path / "updated.json"
    result = runner.invoke(
        app, ["infer-locators", str(repo), str(draft), "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    sidecar = (tmp_path / "updated.review.md").read_text(encoding="utf-8")
    # The matcher's sidecar lines verbatim: the bound line names the site and
    # the R6 dependency disclosure.
    assert "claim auc: bound at out/results.json (path=auc) at raw; depends on" in sidecar
    # The never-silent-loss disclosure: the symlinked directory is named with
    # its source and reason.
    assert "Sweep skips (1)" in sidecar
    assert "- linked: symlinked directory, not followed" in sidecar
    # The mode note, value-only wording (no --metrics given).
    assert "Matching mode: value-only (semantic filter off)" in sidecar


def test_infer_locators_sidecar_semantic_mode_and_metrics_note(tmp_path):
    repo = _dense_recovery_repo(tmp_path / "repo")
    draft = _draft_claims(tmp_path, [{"id": "r", "value": 0.91, "tolerance": 0.05}])
    metrics = _metrics(tmp_path, json.dumps({"r": ["recovery"]}), name="metrics.json")
    out = tmp_path / "updated.json"
    result = runner.invoke(
        app,
        [
            "infer-locators",
            str(repo),
            str(draft),
            "--out",
            str(out),
            "--metrics",
            str(metrics),
        ],
    )
    assert result.exit_code == 0, result.output
    sidecar = (tmp_path / "updated.review.md").read_text(encoding="utf-8")
    assert "Matching mode: semantic (metric words narrow the candidate pool)" in sidecar
    # The metrics-source note: metric words are proposals, pending human
    # review -- the same framing as the sidecar header.
    assert "Metric words are proposals, pending human review" in sidecar
    # The semantic bind names the narrowing column.
    assert "via column recovery" in sidecar


def test_infer_locators_sidecar_suffix_rule_for_non_json_out(tmp_path):
    repo = _json_repo(tmp_path / "repo", '{"auc": 0.9134}\n')
    draft = _draft_claims(tmp_path, [{"id": "auc", "value": 0.91, "tolerance": 0.01}])
    out = tmp_path / "updated.claims"
    result = runner.invoke(
        app, ["infer-locators", str(repo), str(draft), "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    # Suffix rule: `.json` -> `.review.md`, anything else -> `<name>.review.md`.
    assert (tmp_path / "updated.claims.review.md").exists()
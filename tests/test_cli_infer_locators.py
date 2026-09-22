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
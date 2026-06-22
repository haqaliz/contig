"""Tests for run notifications (PRD contract A).

emit_event appends an in-app feed line, optionally POSTs a webhook, and optionally
sends email. The webhook/email side effects are injected (a fake poster/sender) so
the tests never touch the network; a failing side effect must never crash the run.
"""

import json

import pytest

from contig import notify
from contig.notify import emit_event


def _lines(runs_dir):
    path = runs_dir / "notifications.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_emit_event_appends_feed_line(tmp_path):
    emit_event(tmp_path, "r1", "finished", "Run r1 finished")
    rows = _lines(tmp_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["run_id"] == "r1"
    assert row["kind"] == "finished"
    assert row["message"] == "Run r1 finished"
    assert "ts" in row and row["ts"]


def test_emit_event_appends_in_order(tmp_path):
    emit_event(tmp_path, "r1", "awaiting_approval", "paused")
    emit_event(tmp_path, "r1", "finished", "done")
    rows = _lines(tmp_path)
    assert [r["kind"] for r in rows] == ["awaiting_approval", "finished"]


def test_emit_event_creates_runs_dir(tmp_path):
    nested = tmp_path / "does" / "not" / "exist"
    emit_event(nested, "r1", "failed", "boom")
    assert (nested / "notifications.jsonl").is_file()


def test_emit_event_rejects_unknown_kind(tmp_path):
    with pytest.raises(ValueError):
        emit_event(tmp_path, "r1", "exploded", "nope")
    assert not (tmp_path / "notifications.jsonl").exists()


def test_emit_event_posts_to_webhook_when_set(tmp_path, monkeypatch):
    captured = {}

    def fake_post(url, payload):
        captured["url"] = url
        captured["payload"] = payload

    monkeypatch.setattr(notify, "_post_webhook", fake_post)
    emit_event(tmp_path, "r1", "finished", "done", webhook="https://hook.example/x")
    assert captured["url"] == "https://hook.example/x"
    assert captured["payload"]["run_id"] == "r1"
    assert captured["payload"]["kind"] == "finished"


def test_emit_event_no_webhook_no_post(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(notify, "_post_webhook", lambda url, payload: calls.append(url))
    emit_event(tmp_path, "r1", "finished", "done")
    assert calls == []


def test_emit_event_webhook_failure_is_swallowed(tmp_path, monkeypatch):
    def boom(url, payload):
        raise RuntimeError("network down")

    monkeypatch.setattr(notify, "_post_webhook", boom)
    # Must not raise: a failing webhook never crashes the run.
    emit_event(tmp_path, "r1", "finished", "done", webhook="https://hook.example/x")
    # The feed line was still written despite the webhook failure.
    assert _lines(tmp_path)[0]["kind"] == "finished"


def test_emit_event_sends_email_when_smtp_env_present(tmp_path, monkeypatch):
    captured = {}

    def fake_send(config, payload):
        captured["config"] = config
        captured["payload"] = payload

    monkeypatch.setattr(notify, "_send_email", fake_send)
    monkeypatch.setenv("CONTIG_SMTP_HOST", "smtp.example")
    monkeypatch.setenv("CONTIG_SMTP_PORT", "587")
    monkeypatch.setenv("CONTIG_SMTP_USER", "u")
    monkeypatch.setenv("CONTIG_SMTP_PASSWORD", "p")
    monkeypatch.setenv("CONTIG_SMTP_FROM", "from@example")
    monkeypatch.setenv("CONTIG_SMTP_TO", "to@example")

    emit_event(tmp_path, "r1", "failed", "boom")
    assert captured["config"]["host"] == "smtp.example"
    assert captured["config"]["port"] == 587
    assert captured["payload"]["kind"] == "failed"


def test_emit_event_no_email_when_smtp_env_absent(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(notify, "_send_email", lambda config, payload: calls.append(config))
    for var in (
        "CONTIG_SMTP_HOST",
        "CONTIG_SMTP_PORT",
        "CONTIG_SMTP_USER",
        "CONTIG_SMTP_PASSWORD",
        "CONTIG_SMTP_FROM",
        "CONTIG_SMTP_TO",
    ):
        monkeypatch.delenv(var, raising=False)
    emit_event(tmp_path, "r1", "finished", "done")
    assert calls == []


def test_emit_event_partial_smtp_env_does_not_send(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(notify, "_send_email", lambda config, payload: calls.append(config))
    monkeypatch.setenv("CONTIG_SMTP_HOST", "smtp.example")
    monkeypatch.delenv("CONTIG_SMTP_PORT", raising=False)
    monkeypatch.delenv("CONTIG_SMTP_USER", raising=False)
    monkeypatch.delenv("CONTIG_SMTP_PASSWORD", raising=False)
    monkeypatch.delenv("CONTIG_SMTP_FROM", raising=False)
    monkeypatch.delenv("CONTIG_SMTP_TO", raising=False)
    emit_event(tmp_path, "r1", "finished", "done")
    assert calls == []


def test_emit_event_email_failure_is_swallowed(tmp_path, monkeypatch):
    def boom(config, payload):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(notify, "_send_email", boom)
    for var, val in (
        ("CONTIG_SMTP_HOST", "smtp.example"),
        ("CONTIG_SMTP_PORT", "587"),
        ("CONTIG_SMTP_USER", "u"),
        ("CONTIG_SMTP_PASSWORD", "p"),
        ("CONTIG_SMTP_FROM", "from@example"),
        ("CONTIG_SMTP_TO", "to@example"),
    ):
        monkeypatch.setenv(var, val)
    # Must not raise despite the SMTP failure.
    emit_event(tmp_path, "r1", "finished", "done")
    assert _lines(tmp_path)[0]["kind"] == "finished"


def test_emit_event_does_not_log_secrets(tmp_path, monkeypatch, caplog):
    def boom(config, payload):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(notify, "_send_email", boom)
    for var, val in (
        ("CONTIG_SMTP_HOST", "smtp.example"),
        ("CONTIG_SMTP_PORT", "587"),
        ("CONTIG_SMTP_USER", "secret-user"),
        ("CONTIG_SMTP_PASSWORD", "secret-password"),
        ("CONTIG_SMTP_FROM", "from@example"),
        ("CONTIG_SMTP_TO", "to@example"),
    ):
        monkeypatch.setenv(var, val)
    with caplog.at_level("WARNING"):
        emit_event(tmp_path, "r1", "finished", "done")
    assert "secret-password" not in caplog.text
    assert "secret-user" not in caplog.text

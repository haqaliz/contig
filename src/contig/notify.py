"""Run notifications: in-app feed + webhook + email (PRD contract A).

A single emit point that records run lifecycle transitions three ways:

  1. always: one JSON line appended to ``<runs_dir>/notifications.jsonl`` (the
     in-app activity feed the dashboard reads, newest first);
  2. if a webhook URL is supplied: a best-effort POST of that same payload;
  3. if the ``CONTIG_SMTP_*`` env is fully set: a best-effort email of it.

The webhook and email are best-effort: a failure is logged and swallowed, never
crashing the run. The POST and SMTP side effects are module-level functions so a
test can monkeypatch them and never touch the network. Secrets come only from env
and are never logged.
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
import urllib.request
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

logger = logging.getLogger(__name__)

# The lifecycle transitions a run can announce. A kind outside this set is a
# programming error (a typo would silently corrupt the feed), so it is rejected.
KINDS = frozenset({"finished", "failed", "cancelled", "awaiting_approval"})

# The env vars that together configure SMTP. Email is sent only when ALL are set;
# any missing one is a no-op (the unconfigured default).
_SMTP_ENV = (
    "CONTIG_SMTP_HOST",
    "CONTIG_SMTP_PORT",
    "CONTIG_SMTP_USER",
    "CONTIG_SMTP_PASSWORD",
    "CONTIG_SMTP_FROM",
    "CONTIG_SMTP_TO",
)


def emit_event(
    runs_dir: str | Path,
    run_id: str,
    kind: str,
    message: str,
    *,
    webhook: str | None = None,
) -> None:
    """Record a run lifecycle event to the feed, and optionally webhook + email.

    Appends ``{ts, run_id, kind, message}`` to ``<runs_dir>/notifications.jsonl``.
    ``ts`` is the current UTC instant. Raises ValueError for an unknown ``kind``.
    Webhook and email are best-effort: their failures are logged and swallowed.
    """
    if kind not in KINDS:
        raise ValueError(f"unknown notification kind {kind!r}; expected one of {sorted(KINDS)}")

    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "kind": kind,
        "message": message,
    }

    runs_dir = Path(runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)
    with open(runs_dir / "notifications.jsonl", "a") as fh:
        fh.write(json.dumps(payload) + "\n")

    if webhook:
        try:
            _post_webhook(webhook, payload)
        except Exception as exc:  # best-effort: a webhook never crashes the run
            logger.warning("notification webhook failed for run %s: %s", run_id, exc)

    config = _smtp_config()
    if config is not None:
        try:
            _send_email(config, payload)
        except Exception as exc:  # best-effort: email never crashes the run
            logger.warning("notification email failed for run %s: %s", run_id, exc)


def _smtp_config() -> dict | None:
    """Build the SMTP config from env, or None unless every var is set.

    The password is read but never logged; only host/port/from/to identify the
    send in any diagnostic.
    """
    values = {var: os.environ.get(var) for var in _SMTP_ENV}
    if not all(values.values()):
        return None
    try:
        port = int(values["CONTIG_SMTP_PORT"])
    except (TypeError, ValueError):
        return None
    return {
        "host": values["CONTIG_SMTP_HOST"],
        "port": port,
        "user": values["CONTIG_SMTP_USER"],
        "password": values["CONTIG_SMTP_PASSWORD"],
        "from": values["CONTIG_SMTP_FROM"],
        "to": values["CONTIG_SMTP_TO"],
    }


def _post_webhook(url: str, payload: dict, *, timeout: float = 10.0) -> None:
    """POST the JSON payload to the webhook URL (real network; injected in tests)."""
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=timeout):  # noqa: S310 (caller-supplied URL)
        pass


def _send_email(config: dict, payload: dict, *, timeout: float = 10.0) -> None:
    """Send the payload as a short email via SMTP (real network; injected in tests)."""
    msg = EmailMessage()
    msg["Subject"] = f"[contig] run {payload['run_id']} {payload['kind']}"
    msg["From"] = config["from"]
    msg["To"] = config["to"]
    msg.set_content(payload["message"] + "\n\n" + json.dumps(payload, indent=2))
    with smtplib.SMTP(config["host"], config["port"], timeout=timeout) as server:
        server.starttls()
        server.login(config["user"], config["password"])
        server.send_message(msg)

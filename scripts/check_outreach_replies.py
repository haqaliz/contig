#!/usr/bin/env python3
"""Watch the AOL Inbox for replies to the research-workbench outreach.

Deterministic filter only: known sender domains, a `Re:` subject with a known
topic, or a bounce. It never auto-replies. New matches are appended to a local
digest; an agent can then read and draft a response.

Run manually:
  python3 scripts/check_outreach_replies.py

Install a 15-minute macOS LaunchAgent:
  bash scripts/install_outreach_watcher.sh
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

STATE_DIR = Path(
    os.environ.get(
        "CONTIG_OUTREACH_STATE", "~/.local/state/contig-outreach"
    )
).expanduser()
SEEN_PATH = STATE_DIR / "seen.json"
DIGEST_PATH = STATE_DIR / "replies.md"

TARGET_DOMAINS = {
    "uhb.nhs.uk",
    "gosh.nhs.uk",
    "exeter.ac.uk",
    "amp.org",
    "genomicsengland.co.uk",
}
TOPIC_KEYWORDS = (
    "research-use",
    "panelapp",
    "msi/tmb",
    "coverage-readiness",
    "redacted report",
    "one panel",
)
AUTO_PREFIXES = (
    "automatic reply:",
    "auto-reply:",
    "autoreply:",
    "automatic response:",
    "auto response:",
    "out of office",
)


def _himalaya(*args: str) -> str:
    binary = os.environ.get("HIMALAYA_BIN", "himalaya")
    result = subprocess.run(
        [binary, *args], capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout


def _load_seen() -> set[str]:
    if not SEEN_PATH.is_file():
        return set()
    try:
        return set(json.loads(SEEN_PATH.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return set()


def _save_seen(seen: set[str]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SEEN_PATH.write_text(json.dumps(sorted(seen)), encoding="utf-8")


def _classify(envelope: dict) -> str | None:
    senders = [
        str(item.get("email", "")).lower()
        for item in envelope.get("from", [])
        if isinstance(item, dict)
    ]
    subject = str(envelope.get("subject", ""))
    lowered = subject.lower()
    if lowered.startswith(AUTO_PREFIXES):
        return "auto-reply"
    if any(
        sender.startswith("mailer-daemon") or sender.startswith("postmaster")
        for sender in senders
    ):
        return "bounce"
    if any(sender.split("@")[-1] in TARGET_DOMAINS for sender in senders):
        return "reply"
    if lowered.startswith("re:") and any(
        keyword in lowered for keyword in TOPIC_KEYWORDS
    ):
        return "reply"
    return None


def main() -> int:
    try:
        payload = json.loads(
            _himalaya(
                "envelope", "list", "-a", "aol", "-m", "Inbox",
                "-s", "50", "--json",
            )
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"watch failed: {exc}", file=sys.stderr)
        return 1

    seen = _load_seen()
    new_rows = []
    for envelope in payload.get("envelopes", []):
        envelope_id = str(envelope.get("id", ""))
        if not envelope_id or envelope_id in seen:
            continue
        kind = _classify(envelope)
        if kind is None:
            continue
        seen.add(envelope_id)
        senders = ", ".join(
            str(item.get("email", ""))
            for item in envelope.get("from", [])
            if isinstance(item, dict)
        )
        new_rows.append({
            "id": envelope_id,
            "kind": kind,
            "from": senders,
            "subject": str(envelope.get("subject", "")),
            "date": str(envelope.get("date", "")),
        })

    _save_seen(seen)
    if not new_rows:
        print("No new outreach replies.")
        return 0

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with DIGEST_PATH.open("a", encoding="utf-8") as handle:
        for row in new_rows:
            handle.write(
                f"## {row['kind']} — {row['date']}\n"
                f"- From: {row['from']}\n"
                f"- Subject: {row['subject']}\n"
                f"- Read: `himalaya message read -a aol {row['id']}`\n\n"
            )
    print(f"{len(new_rows)} new outreach message(s):")
    for row in new_rows:
        print(f"- [{row['kind']}] {row['from']} — {row['subject']}")
    print(f"Digest: {DIGEST_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

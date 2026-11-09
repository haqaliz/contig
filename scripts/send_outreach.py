#!/usr/bin/env python3
"""Send a JSON batch of plain-text outreach emails over SMTP.

Default is a dry run: it writes one .eml preview per message and sends nothing.
Sending requires an explicit --send (or --check to test the SMTP login).

Config (environment):
  CONTIG_SMTP_HOST        smtp.gmail.com / smtp.aol.com / 127.0.0.1 (Proton Bridge)
  CONTIG_SMTP_PORT        465 (default) / 587 / 1025
  CONTIG_SMTP_SECURITY    ssl (default) / starttls / none
  CONTIG_SMTP_USER        full email address
  CONTIG_SMTP_FROM        optional From address (default: CONTIG_SMTP_USER)
  CONTIG_SMTP_FROM_NAME   display name (default: Ali Haqiqi)
  CONTIG_SMTP_PASSWORD    app password (prefer Keychain below)
  CONTIG_SMTP_PASSWORD_CMD
                          command that prints the password (default:
                          security find-generic-password -a contig-outreach -s smtp -w)

Keychain setup (password is not written to shell history):
  read -rsp "App password: " SMTP_PASS; echo
  security add-generic-password -a contig-outreach -s smtp -w "$SMTP_PASS"
  unset SMTP_PASS

Usage:
  python scripts/send_outreach.py --messages docs/validation/outreach_messages_batch1.json
  python scripts/send_outreach.py --messages ... --send
  python scripts/send_outreach.py --messages ... --check
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import smtplib
import ssl
import subprocess
import sys
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

SIGNATURE = (
    "\n--\n"
    "Ali Haqiqi\n"
    "Contig — research-use variant/coverage/report validation\n"
    "https://github.com/haqaliz/contig\n"
    "Research use only; no diagnosis, ACMG adjudication, or treatment recommendation.\n"
)


def load_messages(path: str) -> list[dict]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise SystemExit("messages file must be a non-empty JSON list")
    for item in payload:
        for key in ("id", "to", "subject", "body"):
            if not item.get(key):
                raise SystemExit(f"message is missing {key!r}: {item}")
    return payload


def build_message(item: dict, from_address: str, from_name: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = f"{from_name} <{from_address}>"
    message["To"] = item["to"]
    message["Subject"] = item["subject"]
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain=from_address.split("@")[-1] or "contig.local")
    body = item["body"].rstrip() + SIGNATURE
    message.set_content(body)
    return message


def smtp_password() -> str:
    password = os.environ.get("CONTIG_SMTP_PASSWORD")
    if password:
        return password
    command = os.environ.get(
        "CONTIG_SMTP_PASSWORD_CMD",
        "security find-generic-password -a contig-outreach -s smtp -w",
    )
    try:
        return subprocess.check_output(
            shlex.split(command), text=True, stderr=subprocess.PIPE
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(
            "SMTP password unavailable. Set CONTIG_SMTP_PASSWORD or add the "
            "Keychain item described in the script header.\n"
            f"({exc})"
        ) from exc


def connect(args: argparse.Namespace):
    host = os.environ.get("CONTIG_SMTP_HOST")
    user = os.environ.get("CONTIG_SMTP_USER")
    if not host or not user:
        raise SystemExit("set CONTIG_SMTP_HOST and CONTIG_SMTP_USER first")
    port = int(os.environ.get("CONTIG_SMTP_PORT", "465"))
    security = os.environ.get("CONTIG_SMTP_SECURITY", "ssl").lower()
    timeout = 30
    if security == "ssl":
        client = smtplib.SMTP_SSL(host, port, timeout=timeout, context=ssl.create_default_context())
    else:
        client = smtplib.SMTP(host, port, timeout=timeout)
        if security == "starttls":
            client.starttls(context=ssl.create_default_context())
    client.login(user, smtp_password())
    return client


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--messages", required=True)
    parser.add_argument("--send", action="store_true", help="Actually send (default: dry run)")
    parser.add_argument("--check", action="store_true", help="Test the SMTP login only")
    parser.add_argument("--out-dir", default="/tmp/outreach-eml")
    parser.add_argument("--from-name", default=os.environ.get("CONTIG_SMTP_FROM_NAME", "Ali Haqiqi"))
    args = parser.parse_args()

    messages = load_messages(args.messages)
    from_address = os.environ.get("CONTIG_SMTP_FROM") or os.environ.get(
        "CONTIG_SMTP_USER", "contig-outreach@example.invalid"
    )

    if args.check:
        client = connect(args)
        client.quit()
        print(f"SMTP login OK for {os.environ.get('CONTIG_SMTP_USER')}")
        return 0

    if not args.send:
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        for item in messages:
            message = build_message(item, from_address, args.from_name)
            path = out / f"{item['id']}.eml"
            path.write_bytes(message.as_bytes())
            print(f"preview {item['id']}: {path}")
            print(f"  To: {item['to']}")
            print(f"  Subject: {item['subject']}")
        print(f"\nDry run only. Review the .eml files, then re-run with --send.")
        return 0

    client = connect(args)
    try:
        for item in messages:
            message = build_message(item, from_address, args.from_name)
            client.send_message(message)
            print(f"sent {item['id']} -> {item['to']}")
    finally:
        client.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())

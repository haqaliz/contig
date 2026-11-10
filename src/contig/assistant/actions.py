"""Approval-gated execution of assistant-suggested actions.

The deterministic router only suggests commands. Nothing runs until the user
approves the selected action. Execution is argv-based (no shell), restricted to
a small allowlist of assistant subcommands, and refuses templates that still
contain placeholders.
"""

from __future__ import annotations

import shlex
import subprocess
from collections.abc import Callable

ALLOWED_SUBCOMMANDS = frozenset(
    {"show", "verify", "methods", "report", "report-check"}
)

# A placeholder (<vcf>) or a shell operator must never reach the runner.
_UNSAFE = set(";|&$`<>*?()[]{}\n\r")


class ActionError(ValueError):
    """The suggested action cannot be executed safely."""


def parse_action(command: str) -> list[str]:
    """Turn a suggested command into argv, refusing anything outside the gate."""
    text = command.strip()
    if not text:
        raise ActionError("empty action")
    if any(character in _UNSAFE for character in text):
        raise ActionError(
            "action contains a placeholder or shell operator; refusing to execute it"
        )
    try:
        argv = shlex.split(text)
    except ValueError as exc:
        raise ActionError(f"cannot parse action: {exc}") from exc
    if len(argv) < 2 or argv[0] != "contig":
        raise ActionError("only `contig ...` actions can be executed")
    if argv[1] not in ALLOWED_SUBCOMMANDS:
        raise ActionError(f"action subcommand is not allowlisted: {argv[1]}")
    return argv


def execute_action(
    command: str,
    *,
    approved: bool = False,
    confirm: Callable[[str], bool] | None = None,
    runner: Callable[[list[str]], int] | None = None,
) -> tuple[bool, int]:
    """Run an action only after approval.

    Returns ``(ran, exit_code)``. ``approved=True`` is the explicit
    non-interactive approval; otherwise ``confirm`` is asked and a missing or
    false confirmation refuses execution.
    """
    argv = parse_action(command)
    if not approved:
        if confirm is None or not confirm(f"Run this action? {command}"):
            return False, 0
    run = runner or _run
    return True, run(argv)


def _run(argv: list[str]) -> int:
    try:
        completed = subprocess.run(argv, check=False)
    except FileNotFoundError as exc:
        raise ActionError(f"could not run {argv[0]!r}: {exc}") from exc
    return completed.returncode

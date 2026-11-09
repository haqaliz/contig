"""Helpers for CLI output assertions."""

from __future__ import annotations

import re

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def plain(text: str) -> str:
    """Strip ANSI SGR escape sequences from CLI output.

    Rich/Typer inserts a reset between the two hyphens of an option in some
    colored terminals (for example ``-\\x1b[0m-clinvar``), so a raw substring
    check for ``--clinvar`` fails even though the help is correct.
    """
    return _ANSI.sub("", text)

"""Shared test environment.

Keep Typer/Rich CLI help rendering stable: CI runs in a narrow, non-TTY
terminal, and a wide plain-text help table is what the `--help` assertions
expect. Without this, option names wrap and the ANSI escapes break substring
matching even though the command is correct.
"""

import os

os.environ["COLUMNS"] = "200"
os.environ["NO_COLOR"] = "1"

"""PyInstaller entry point for the standalone contig binary.

The console script (pyproject [project.scripts]) is contig.cli:app, but PyInstaller
freezes a script, not a module attribute, so this thin wrapper calls the Typer app.
The data files under contig/data are bundled via the build's --add-data flag.
"""

from contig.cli import app

if __name__ == "__main__":
    app()

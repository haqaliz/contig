"""Injectable STARsolo second-quantifier seam (PRD sc-concordance-autorun, Phase 1).

Single-cell cross-tool count concordance (`sc_count_concordance.py`) needs a
second, independent gene-count matrix on the same FASTQs. This seam lets Contig
produce that second matrix by running STARsolo itself against a prebuilt STAR
genome directory and a barcode whitelist, emitting a 10x-style MatrixMarket
triplet whose `matrix.mtx` feeds `load_sc_matrix` unchanged.

The seam mirrors the kallisto seam in `count_quantifier.py`: a `ScCountQuantifier`
is an injectable callable so the rest of the engine (and its tests) never has to
run a real tool. `starsolo_command` is a pure argv builder, asserted directly in
tests; `run_starsolo_quantifier` is the default implementation that shells out.
STAR itself is never executed in CI (the subprocess success path is covered only
by a manual gate); tests exercise the builder, the read-order derivation, the
chemistry table, and the honest error paths.

Two footguns are pinned as pure, unit-tested functions:

- `chemistry_geometry` refuses to guess CB/UMI geometry for an unknown chemistry
  (never a silently wrong barcode layout).
- `readfiles_order` reverses the sample sheet's `[fastq_1(CB), fastq_2(cDNA)]`
  into STARsolo's `--readFilesIn <cDNA> <CB>` order.

Unlike the kallisto seam there is NO transcript->gene collapse step: STARsolo
emits gene-level counts natively, so the returned path is the Solo `matrix.mtx`.

Honesty: a missing binary, missing reads/index/whitelist, a nonzero exit, or a
missing Solo `matrix.mtx` all raise the one named `SecondScQuantifierError`. It
never leaks a bare FileNotFoundError and never returns a partial/absent matrix.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from pydantic import ValidationError

from contig.samplesheet import fastq_paths

# A second single-cell quantifier:
# (reads, index, whitelist, chemistry, out_dir) -> produced matrix.mtx path. The
# CLI auto path takes one of these and tests inject a fake, so no tool runs in CI.
ScCountQuantifier = Callable[[str, str, str, str, str], str]

# The binary name, as a module-level constant so tests can monkeypatch it to a
# bogus (or trivially-exiting) value and drive the error paths without touching
# PATH or ever running a real STAR.
_STAR = "STAR"

# Chemistry presets: name -> (CBstart, CBlen, UMIstart, UMIlen), 1-based, in
# STARsolo's --soloCB*/--soloUMI* convention. 10x v3 has a 12bp UMI, v2 a 10bp.
_CHEMISTRY_PRESETS: dict[str, tuple[int, int, int, int]] = {
    "10xv3": (1, 16, 17, 12),
    "10xv2": (1, 16, 17, 10),
}


class SecondScQuantifierError(Exception):
    """Raised when the STARsolo second quantifier cannot run or is misconfigured.

    A missing binary, missing/unreadable reads/index/whitelist, an unknown
    chemistry, fewer than two FASTQs (no 10x cDNA,CB pair), a nonzero exit, or a
    missing Solo `matrix.mtx` are all surfaced through this one named error so the
    CLI can turn them into a clear skip note (no false PASS, no leaked traceback,
    and never a silent/partial matrix masquerading as a corroborating count).
    """


def chemistry_geometry(name: str) -> tuple[int, int, int, int]:
    """Return the (CBstart, CBlen, UMIstart, UMIlen) tuple for a chemistry (pure).

    Raises `SecondScQuantifierError` for an unknown chemistry rather than guessing
    a barcode/UMI layout — a wrong geometry silently produces garbage cells.
    """
    geometry = _CHEMISTRY_PRESETS.get(name)
    if geometry is None:
        known = ", ".join(sorted(_CHEMISTRY_PRESETS))
        raise SecondScQuantifierError(
            f"unknown single-cell chemistry '{name}' (known: {known})"
        )
    return geometry


def readfiles_order(fastqs: list[str]) -> tuple[str, str]:
    """Map sample-sheet FASTQ order to STARsolo's `--readFilesIn` order (pure).

    The sample sheet yields `[fastq_1(=CB/R1), fastq_2(=cDNA/R2), ...]`; STARsolo
    wants `(cDNA, CB)`, so return `(fastqs[1], fastqs[0])`. Only the first pair is
    used. Fewer than two FASTQs cannot form a 10x cDNA,CB pair (e.g. single-end),
    so raise `SecondScQuantifierError`.
    """
    if len(fastqs) < 2:
        raise SecondScQuantifierError(
            f"single-cell concordance needs a cDNA,CB FASTQ pair; got {len(fastqs)}"
        )
    return (fastqs[1], fastqs[0])


def starsolo_command(
    fastqs: list[str],
    index: str,
    whitelist: str,
    chemistry: str,
    out_dir: str,
) -> list[str]:
    """Build the `STAR` STARsolo argv as a single list (pure).

    Derives CB/UMI geometry via `chemistry_geometry` and the `--readFilesIn`
    (cDNA, CB) order via `readfiles_order`. No execution, no I/O. Solo emits
    gene-level counts natively (`--soloFeatures Gene`) and no alignment BAM
    (`--outSAMtype None`); the triplet lands under `<out_dir>/`.
    """
    cb_start, cb_len, umi_start, umi_len = chemistry_geometry(chemistry)
    cdna, cb = readfiles_order(fastqs)
    return [
        _STAR,
        "--runMode",
        "alignReads",
        "--soloType",
        "CB_UMI_Simple",
        "--genomeDir",
        index,
        "--soloCBwhitelist",
        whitelist,
        "--soloCBstart",
        str(cb_start),
        "--soloCBlen",
        str(cb_len),
        "--soloUMIstart",
        str(umi_start),
        "--soloUMIlen",
        str(umi_len),
        "--readFilesIn",
        cdna,
        cb,
        "--soloFeatures",
        "Gene",
        "--outSAMtype",
        "None",
        "--outFileNamePrefix",
        f"{out_dir}/",
    ]


def run_starsolo_quantifier(
    reads: str,
    index: str,
    whitelist: str,
    chemistry: str,
    out_dir: str,
) -> str:
    """Run STARsolo to produce a second single-cell matrix; return its `matrix.mtx`.

    Validates that the reads sample sheet exists and the index (STAR genome dir)
    and whitelist exist BEFORE any spawn (a clear error beats a confusing tool
    failure), derives FASTQ paths from the sample sheet, builds the STARsolo
    command, runs it, and locates the Solo `matrix.mtx` under `out_dir`.

    A missing binary (FileNotFoundError from the spawn), a nonzero exit, a
    malformed sample sheet (bare ValueError / pydantic ValidationError from
    `fastq_paths`), an unknown chemistry / too-few FASTQs (from the argv builder),
    or a missing Solo `matrix.mtx` are all re-raised as a clear
    `SecondScQuantifierError`, never leaked and never a silent/partial matrix.

    The subprocess success path is intentionally NOT exercised in CI; the manual
    gate covers it against a real STAR genome index, whitelist, and FASTQs.
    """
    reads_path = Path(reads)
    index_path = Path(index)
    whitelist_path = Path(whitelist)
    if not reads_path.is_file():
        raise SecondScQuantifierError(
            f"second quantifier reads sheet not found: {reads}"
        )
    if not index_path.is_dir():
        raise SecondScQuantifierError(
            f"second quantifier index (STAR genome dir) not found: {index}"
        )
    if not whitelist_path.is_file():
        raise SecondScQuantifierError(
            f"second quantifier barcode whitelist not found: {whitelist}"
        )

    try:
        fastqs = [str(p) for p in fastq_paths(reads)]
    except (ValueError, ValidationError) as exc:
        raise SecondScQuantifierError(
            f"second quantifier reads sheet is malformed: {reads} ({exc})"
        ) from exc

    argv = starsolo_command(fastqs, index, whitelist, chemistry, out_dir)

    try:
        # intentionally NOT exercised in CI; manual gate covers it
        result = subprocess.run(argv, capture_output=True)
    except FileNotFoundError as exc:
        raise SecondScQuantifierError(
            f"STAR not found (is the '{_STAR}' binary on PATH?): {exc}"
        ) from exc

    if result.returncode != 0:
        detail = result.stderr.decode(errors="replace").strip() if result.stderr else ""
        raise SecondScQuantifierError(
            f"STAR exited nonzero ({result.returncode}): {detail}"
        )

    matrix = next(Path(out_dir).rglob("matrix.mtx*"), None)
    if matrix is None:
        raise SecondScQuantifierError(
            f"STARsolo produced no matrix.mtx under {out_dir}"
        )
    return str(matrix)

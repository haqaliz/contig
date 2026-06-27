"""Injectable second-variant-caller seam (PRD concordance-autorun, Phase 1).

Cross-tool concordance (concordance.py) needs a second, independent call set on the
same input. C1 made the user pre-compute that VCF; this seam lets Contig produce it
by running a second caller (bcftools by default) on an aligned BAM and a reference.

The seam mirrors `Executor`/`default_executor` in `runner.py`: a `VariantCaller` is
an injectable callable so the rest of the engine (and its tests) never has to run a
real tool. `bcftools_command` is a pure argv builder, asserted directly in tests;
`run_bcftools_caller` is the default implementation that shells out. bcftools itself
is never executed in CI (the subprocess success path is covered only by a manual
gate); tests exercise the builder and the honest error paths.

Honesty: a missing binary, a missing BAM, or a missing reference raises a clear,
named `SecondCallerError`. It never leaks a bare FileNotFoundError and never lets a
silent failure masquerade as a usable call set.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

# A second variant caller: (bam_path, ref_path, out_dir) -> produced_vcf_path.
# The CLI auto path takes one of these and tests inject a fake, exactly as
# `Executor` is injected in runner.py, so no tool runs in CI.
VariantCaller = Callable[[str, str, str], str]

# The binary name, as a module-level constant so tests can monkeypatch it to a bogus
# value and drive the missing-binary error path without touching PATH.
_BCFTOOLS = "bcftools"

# Name of the produced second call set, written under the caller's out_dir.
_SECOND_VCF_NAME = "second.vcf.gz"


class SecondCallerError(Exception):
    """Raised when the second caller cannot run or its inputs are missing.

    A missing binary, a missing/unreadable BAM or reference, or a nonzero exit are
    all surfaced through this one named error so the CLI can turn them into a clear
    skip note (no false PASS, no leaked traceback).
    """


def bcftools_command(bam: str, ref: str, out: str) -> tuple[list[str], list[str]]:
    """Build the two-stage piped bcftools command as a pair of argv lists (pure).

    Stage 1 (`bcftools mpileup -f <ref> <bam>`) writes pileup to stdout; stage 2
    (`bcftools call -mv -Oz -o <out>`) reads that stdin and writes the bgzipped VCF.
    Returning the two stages separately keeps the function pure and lets the runner
    wire the pipe explicitly. No execution, no I/O.
    """
    mpileup = [_BCFTOOLS, "mpileup", "-f", ref, bam]
    call = [_BCFTOOLS, "call", "-mv", "-Oz", "-o", out]
    return mpileup, call


def run_bcftools_caller(bam: str, ref: str, out_dir: str) -> str:
    """Run bcftools to produce a second call set; return the produced VCF path.

    Validates that the BAM and reference exist BEFORE any spawn (a clear error
    beats a confusing tool failure), builds the `mpileup | call` command, runs it as
    an explicit pipe (mirroring `runner.default_executor`), and returns the path to
    `<out_dir>/second.vcf.gz`. A missing binary (FileNotFoundError from the spawn) or
    a nonzero exit is re-raised as a clear SecondCallerError, never leaked.

    The subprocess success path is intentionally NOT exercised in CI; the manual gate
    covers it on a real germline BAM and reference.
    """
    bam_path = Path(bam)
    ref_path = Path(ref)
    if not bam_path.is_file():
        raise SecondCallerError(f"second caller BAM not found: {bam}")
    if not ref_path.is_file():
        raise SecondCallerError(f"second caller reference not found: {ref}")

    out_path = Path(out_dir) / _SECOND_VCF_NAME
    mpileup, call = bcftools_command(bam, ref, str(out_path))

    try:
        pileup = subprocess.Popen(mpileup, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        caller = subprocess.Popen(
            call, stdin=pileup.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        # Let stage 1 receive SIGPIPE if stage 2 exits early.
        if pileup.stdout is not None:
            pileup.stdout.close()
        _, call_err = caller.communicate()
        pileup.wait()
    except FileNotFoundError as exc:
        raise SecondCallerError(
            f"bcftools not found (is the '{_BCFTOOLS}' binary on PATH?): {exc}"
        ) from exc

    if pileup.returncode != 0 or caller.returncode != 0:
        detail = call_err.decode(errors="replace").strip() if call_err else ""
        raise SecondCallerError(
            "bcftools second caller exited nonzero "
            f"(mpileup={pileup.returncode}, call={caller.returncode}): {detail}"
        )

    return str(out_path)

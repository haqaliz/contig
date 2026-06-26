"""Injectable second-variant-caller seam (PRD concordance-autorun, Phase 1).

These tests cover only the pure argv builder and the error paths (missing binary,
missing inputs). bcftools is NEVER executed here: the success subprocess path is
intentionally out of CI, behind a manual gate. Real files only, via tmp_path.
"""

import pytest

from contig.verification.second_caller import (
    SecondCallerError,
    bcftools_command,
    run_bcftools_caller,
)


def _flatten(command):
    """Collapse the two-stage piped command into one token list for assertions."""
    mpileup, call = command
    return list(mpileup) + list(call)


def test_bcftools_command_builds_expected_argv(tmp_path):
    bam = tmp_path / "aligned.bam"
    ref = tmp_path / "ref.fa"
    out = tmp_path / "second.vcf.gz"

    mpileup, call = bcftools_command(str(bam), str(ref), str(out))

    # Stage 1: bcftools mpileup -f <ref> <bam>
    assert mpileup[0] == "bcftools"
    assert "mpileup" in mpileup
    f_idx = mpileup.index("-f")
    assert mpileup[f_idx + 1] == str(ref)
    assert str(bam) in mpileup

    # Stage 2: bcftools call -mv -Oz -o <out>
    assert call[0] == "bcftools"
    assert "call" in call
    assert "-mv" in call
    assert "-Oz" in call
    o_idx = call.index("-o")
    assert call[o_idx + 1] == str(out)


def test_run_bcftools_caller_missing_binary_is_clear_error(tmp_path, monkeypatch):
    bam = tmp_path / "aligned.bam"
    ref = tmp_path / "ref.fa"
    bam.write_text("")  # placeholder so the input-existence check passes
    ref.write_text("")

    # Force the binary to be absent so the spawn raises FileNotFoundError, which the
    # module must translate into a clear SecondCallerError that names bcftools.
    monkeypatch.setattr(
        "contig.verification.second_caller._BCFTOOLS",
        "bcftools-does-not-exist-xyz",
    )

    with pytest.raises(SecondCallerError) as excinfo:
        run_bcftools_caller(str(bam), str(ref), str(tmp_path))

    assert "bcftools" in str(excinfo.value).lower()


def test_run_bcftools_caller_missing_bam_errors(tmp_path):
    ref = tmp_path / "ref.fa"
    ref.write_text("")
    missing_bam = tmp_path / "nope.bam"

    with pytest.raises(SecondCallerError) as excinfo:
        run_bcftools_caller(str(missing_bam), str(ref), str(tmp_path))

    assert "bam" in str(excinfo.value).lower()


def test_run_bcftools_caller_missing_ref_errors(tmp_path):
    bam = tmp_path / "aligned.bam"
    bam.write_text("")
    missing_ref = tmp_path / "nope.fa"

    with pytest.raises(SecondCallerError) as excinfo:
        run_bcftools_caller(str(bam), str(missing_ref), str(tmp_path))

    assert "ref" in str(excinfo.value).lower()

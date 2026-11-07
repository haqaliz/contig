"""MSI verification via MSIsensor output or an external MSIsensor binary."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class MsiResult:
    total_sites: int
    somatic_sites: int
    score: float
    status: str
    threshold: float
    output_path: str
    detail: str = ""
    tumor_bam: str = ""
    normal_bam: str = ""
    sites: str = ""
    bed: str = ""


def parse_msi_output(path: str | Path, *, threshold: float = 10.0) -> MsiResult:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"MSIsensor output not found: {path}")
    lines = [line.rstrip("\n") for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
    header_index = next((i for i, line in enumerate(lines) if "Total_Number_of_Sites" in line), None)
    if header_index is None or header_index + 1 >= len(lines):
        raise ValueError(f"MSIsensor output has no score row: {path}")
    fields = lines[header_index + 1].split("\t")
    if len(fields) < 3:
        raise ValueError(f"MSIsensor output score row is malformed: {path}")
    try:
        total = int(fields[0])
        somatic = int(fields[1])
        score = float(fields[2])
    except ValueError as exc:
        raise ValueError(f"MSIsensor output score row is not numeric: {path}") from exc
    status = "MSI-H" if score >= threshold else "MSS"
    return MsiResult(
        total_sites=total,
        somatic_sites=somatic,
        score=score,
        status=status,
        threshold=threshold,
        output_path=str(path),
        detail=f"{somatic}/{total} somatic sites; threshold {threshold:g}% => {status}",
    )


def run_msisensor(
    tumor_bam: str | Path,
    normal_bam: str | Path,
    sites: str | Path,
    bed: str | Path,
    *,
    output: str | Path,
    msisensor_bin: str = "msisensor",
    threshold: float = 10.0,
    timeout: int = 1800,
) -> MsiResult:
    for label, path in (("tumor BAM", tumor_bam), ("normal BAM", normal_bam), ("sites", sites), ("BED", bed)):
        if not Path(path).is_file():
            raise FileNotFoundError(f"MSI {label} not found: {path}")
    output = Path(output)
    command = [
        msisensor_bin, "msi",
        "-d", str(sites),
        "-n", str(normal_bam),
        "-t", str(tumor_bam),
        "-e", str(bed),
        "-o", str(output),
        "-l", "1",
        "-q", "1",
        "-b", "2",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise ValueError(f"MSIsensor binary not found: {msisensor_bin}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"MSIsensor timed out after {timeout}s") from exc
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise ValueError(f"MSIsensor failed (exit {result.returncode}): {message[:300]}")
    parsed = parse_msi_output(output, threshold=threshold)
    parsed.tumor_bam = str(tumor_bam)
    parsed.normal_bam = str(normal_bam)
    parsed.sites = str(sites)
    parsed.bed = str(bed)
    return parsed


def msi_status(computed: str, reported: str | None) -> str:
    if not reported:
        return "computed"
    value = reported.strip().upper()
    if value.startswith("MSI"):
        expected = "MSI-H"
    elif value.startswith("MSS"):
        expected = "MSS"
    else:
        return "unverified"
    return "match" if expected == computed else "divergent"

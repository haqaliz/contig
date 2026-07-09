# Variant Annotation Assay — M1 Implementation Plan (germline structural verify)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable nf-core/sarek's built-in annotation step on the germline `variant_calling` assay and add a Contig verification axis that proves the annotation *ran correctly* (every variant carries an annotation record) and captures the annotation tool + DB version into provenance — research-use only, never a pathogenicity/clinical verdict.

**Architecture:** Mirror the shipped somatic plausibility slice. A new pure verifier (`verification/annotation_structural.py`) parses the annotated VCF's bytes and emits WARN-capped / UNVERIFIED `QCResult`s; a new provenance parser (`compute_annotation_identity`) reads the tool + version straight from the annotated VCF header (the tool records its own version there), attached at `_finalize` exactly like `reference_identity`. Enabling annotation is one declarative `default_params` line on the germline registry entry. No real sarek/VEP/SnpEff ever runs in CI — every test drives synthetic VCF fixtures.

**Tech Stack:** Python 3, Pydantic v2 models, stdlib `gzip`/`statistics`, pytest. No new dependencies (matches the repo's stdlib-only discipline).

## Global Constraints

- **Research-use verification only.** No pathogenicity/clinical/significance verdict emitted by Contig, ever. All annotation output is surfaced as "what tool X reported at DB version Y," attributed. (PRD G3 / R1; `USE_CASE_UNIVERSE.md` bright line.)
- **UNVERIFIED, never PASS, when inputs absent.** A missing/empty annotated VCF, or a VCF with no annotation INFO, yields `status="unverified"` — never a silent pass. (PRD G1; matches `somatic_plausibility.py`.)
- **WARN-capped.** No annotation check may emit `fail` (bands are uncalibrated); the max severity is `warn`. FAIL deferred to a calibrated follow-on. (PRD R3.)
- **No real tool runs in CI.** No sarek/VEP/SnpEff/samtools subprocess in tests; synthetic VCF fixtures only. (PRD R2.)
- **Test-first (TDD).** Every task writes the failing test first, watches it fail, then implements the minimum to pass.
- **Reproduce-safe provenance.** `default_params` are re-injected on `rerun`/`resume` (never stored as derived params); annotation provenance is re-derived from the annotated VCF, not from a scratch path. (Matches the somatic `default_params` R5 pattern in `cli.py:_inject_default_params`.)
- **Annotation INFO keys:** VEP writes `CSQ`, SnpEff writes `ANN`. Support both.

---

### Task 1: Annotation-structural verifier

**Files:**
- Create: `src/contig/verification/annotation_structural.py`
- Create: `tests/verification/test_annotation_structural.py`

**Interfaces:**
- Consumes: `contig.models.QCResult` (fields: `check`, `status`, `message`, `value`, `kind`).
- Produces:
  - `annotation_metrics(vcf_path: str | os.PathLike) -> AnnotationMetrics` where `AnnotationMetrics` is a frozen dataclass `(info_key: str | None, total_records: int, annotated_records: int)`. `info_key` is `"CSQ"`, `"ANN"`, or `None` (neither declared in header).
  - `evaluate_annotation_structural(vcf_path: str | os.PathLike) -> list[QCResult]` — emits `annotation_present` and `annotation_complete`, both `kind="structural"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/verification/test_annotation_structural.py
import gzip
from pathlib import Path

from contig.verification.annotation_structural import (
    AnnotationMetrics,
    annotation_metrics,
    evaluate_annotation_structural,
)

VEP_HEADER = (
    "##fileformat=VCFv4.2\n"
    '##INFO=<ID=CSQ,Number=.,Type=String,Description="Consequence annotations from '
    'Ensembl VEP. Format: Allele|Consequence|IMPACT|SYMBOL">\n'
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
)


def _write(tmp_path: Path, name: str, body: str, gz: bool = False) -> Path:
    p = tmp_path / name
    if gz:
        with gzip.open(p, "wt") as fh:
            fh.write(body)
    else:
        p.write_text(body)
    return p


def test_all_records_annotated_passes(tmp_path):
    body = VEP_HEADER + (
        "chr1\t100\t.\tA\tG\t50\tPASS\tCSQ=G|missense_variant|MODERATE|BRCA1\n"
        "chr1\t200\t.\tC\tT\t50\tPASS\tCSQ=T|synonymous_variant|LOW|BRCA1\n"
    )
    vcf = _write(tmp_path, "ann.vcf", body)
    m = annotation_metrics(vcf)
    assert m == AnnotationMetrics(info_key="CSQ", total_records=2, annotated_records=2)
    results = evaluate_annotation_structural(vcf)
    by_check = {r.check: r for r in results}
    assert by_check["annotation_present"].status == "pass"
    assert by_check["annotation_present"].kind == "structural"
    assert by_check["annotation_complete"].status == "pass"
    assert by_check["annotation_complete"].value == 1.0


def test_partial_annotation_warns(tmp_path):
    body = VEP_HEADER + (
        "chr1\t100\t.\tA\tG\t50\tPASS\tCSQ=G|missense_variant|MODERATE|BRCA1\n"
        "chr1\t200\t.\tC\tT\t50\tPASS\tDP=30\n"  # no CSQ on this record
    )
    vcf = _write(tmp_path, "partial.vcf", body)
    results = evaluate_annotation_structural(vcf)
    by_check = {r.check: r for r in results}
    assert by_check["annotation_complete"].status == "warn"
    assert by_check["annotation_complete"].value == 0.5


def test_no_annotation_info_is_unverified(tmp_path):
    body = (
        "##fileformat=VCFv4.2\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "chr1\t100\t.\tA\tG\t50\tPASS\tDP=30\n"
    )
    vcf = _write(tmp_path, "plain.vcf", body)
    results = evaluate_annotation_structural(vcf)
    statuses = {r.check: r.status for r in results}
    assert statuses["annotation_present"] == "unverified"


def test_snpeff_ann_key_and_gzip(tmp_path):
    body = (
        "##fileformat=VCFv4.2\n"
        '##INFO=<ID=ANN,Number=.,Type=String,Description="Functional annotations: '
        "'Allele | Annotation | Annotation_Impact | Gene_Name'\">\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "chr1\t100\t.\tA\tG\t50\tPASS\tANN=G|missense_variant|MODERATE|TP53\n"
    )
    vcf = _write(tmp_path, "snpeff.vcf.gz", body, gz=True)
    m = annotation_metrics(vcf)
    assert m.info_key == "ANN"
    assert m.annotated_records == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/verification/test_annotation_structural.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'contig.verification.annotation_structural'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/contig/verification/annotation_structural.py
"""Deterministic structural verification that an annotation step ran correctly.

Germline/somatic variant calling can enable nf-core/sarek's annotation step
(VEP -> CSQ, SnpEff -> ANN). This module proves the annotation actually ran over
the call set: it reads the annotated VCF bytes and reports whether the annotation
INFO field is declared and present, and what fraction of records carry it.

Research-use only: it verifies the annotation EXECUTED, never what the annotation
MEANS. It emits no pathogenicity/clinical judgement. Missing annotation degrades
to UNVERIFIED (never a false pass); a partial annotation is at most WARN.
"""

from __future__ import annotations

import gzip
import os
from dataclasses import dataclass
from pathlib import Path

from contig.models import QCResult

_ANNOTATION_KEYS = ("CSQ", "ANN")  # VEP, SnpEff


@dataclass(frozen=True)
class AnnotationMetrics:
    """What the annotated VCF's bytes say about annotation coverage."""

    info_key: str | None  # "CSQ" | "ANN" | None (neither declared in header)
    total_records: int
    annotated_records: int


def _open_text(path: str | os.PathLike):
    """Open a VCF for text reading, transparently gunzipping a `.gz` path."""
    p = Path(path)
    if p.name.endswith(".gz"):
        return gzip.open(p, "rt")
    return open(p)


def _declared_key(header_lines: list[str]) -> str | None:
    """Return the first annotation INFO key declared in the header, or None."""
    for key in _ANNOTATION_KEYS:
        needle = f"##INFO=<ID={key},"
        if any(line.startswith(needle) for line in header_lines):
            return key
    return None


def _record_has_key(info: str, key: str) -> bool:
    """True if an INFO column carries the annotation key (KEY=... token)."""
    return any(field.split("=", 1)[0] == key for field in info.split(";"))


def annotation_metrics(vcf_path: str | os.PathLike) -> AnnotationMetrics:
    """Stream an annotated VCF; return declared key + record counts.

    `info_key` is the header-declared annotation key (CSQ/ANN) or None. When the
    header declares no key we still fall back to sniffing the first data record's
    INFO, so a header-stripped-but-annotated VCF is not misread as un-annotated.
    """
    header_lines: list[str] = []
    key: str | None = None
    resolved = False
    total = 0
    annotated = 0

    with _open_text(vcf_path) as fh:
        for line in fh:
            if line.startswith("#"):
                header_lines.append(line)
                continue
            if not resolved:
                key = _declared_key(header_lines)
                resolved = True
            line = line.rstrip("\n")
            if not line:
                continue
            cols = line.split("\t")
            if len(cols) < 8:
                continue
            info = cols[7]
            if key is None:
                # Header declared nothing; sniff the record for either key.
                for candidate in _ANNOTATION_KEYS:
                    if _record_has_key(info, candidate):
                        key = candidate
                        break
            total += 1
            if key is not None and _record_has_key(info, key):
                annotated += 1

    return AnnotationMetrics(info_key=key, total_records=total, annotated_records=annotated)


def evaluate_annotation_structural(vcf_path: str | os.PathLike) -> list[QCResult]:
    """Emit the annotation structural checks for an annotated VCF (capped at WARN).

    - annotation_present: the annotated VCF declares/carries an annotation field
      AND at least one record is annotated -> pass; otherwise unverified (never a
      false pass — no key means we cannot claim annotation ran).
    - annotation_complete: fraction of data records carrying the annotation field;
      1.0 -> pass, <1.0 -> warn (some variants left un-annotated), no records or no
      key -> unverified.
    """
    m = annotation_metrics(vcf_path)

    if m.info_key is None or m.annotated_records == 0:
        return [
            QCResult(
                check="annotation_present",
                status="unverified",
                message=(
                    "no annotation field (CSQ/ANN) found in the VCF; "
                    "cannot verify an annotation step ran"
                ),
                value=None,
                kind="structural",
            )
        ]

    results = [
        QCResult(
            check="annotation_present",
            status="pass",
            message=(
                f"annotation field {m.info_key} present on "
                f"{m.annotated_records}/{m.total_records} records"
            ),
            value=None,
            kind="structural",
        )
    ]

    if m.total_records == 0:
        fraction = None
        status = "unverified"
        message = "annotation declared but the VCF has no data records"
    else:
        fraction = m.annotated_records / m.total_records
        if fraction >= 1.0:
            status = "pass"
            message = f"all {m.total_records} records carry {m.info_key}"
        else:
            status = "warn"
            message = (
                f"{m.annotated_records}/{m.total_records} records carry "
                f"{m.info_key}; some variants were left un-annotated"
            )

    results.append(
        QCResult(
            check="annotation_complete",
            status=status,
            message=message,
            value=fraction,
            kind="structural",
        )
    )
    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/verification/test_annotation_structural.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/contig/verification/annotation_structural.py tests/verification/test_annotation_structural.py
git commit -m "feat(verify): annotation structural verifier (CSQ/ANN presence + completeness) [C7 M1]"
```

---

### Task 2: Annotation provenance model + parser

**Files:**
- Modify: `src/contig/models.py` (add `AnnotationProvenance` model; add `annotation_identity` field to `RunRecord`)
- Modify: `src/contig/bundle.py` (add `compute_annotation_identity`)
- Create: `tests/test_annotation_provenance.py`

**Interfaces:**
- Consumes: `contig.verification.annotation_structural._open_text` (VCF opener). Import it, do not re-implement gzip handling.
- Produces:
  - `AnnotationProvenance(BaseModel)` fields: `tool: Literal["VEP", "SnpEff"]`, `version: str | None`, `raw_header: str | None`.
  - `compute_annotation_identity(run_dir: Path) -> AnnotationProvenance | None` — globs `**/*.vcf.gz` under `run_dir`, returns the provenance parsed from the first VCF whose header carries `##VEP=` or `##SnpEffVersion`; None when none found.
  - `RunRecord.annotation_identity: AnnotationProvenance | None = None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_annotation_provenance.py
import gzip
from pathlib import Path

from contig.bundle import compute_annotation_identity
from contig.models import AnnotationProvenance


def _write_gz(path: Path, body: str) -> Path:
    with gzip.open(path, "wt") as fh:
        fh.write(body)
    return path


def test_vep_provenance_parsed(tmp_path):
    body = (
        "##fileformat=VCFv4.2\n"
        '##VEP="v110" time="2026-07-10" cache="/vep/homo_sapiens/110_GRCh38"\n'
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "chr1\t100\t.\tA\tG\t50\tPASS\tCSQ=G|missense_variant\n"
    )
    d = tmp_path / "results" / "annotation"
    d.mkdir(parents=True)
    _write_gz(d / "sample_VEP.ann.vcf.gz", body)
    prov = compute_annotation_identity(tmp_path)
    assert isinstance(prov, AnnotationProvenance)
    assert prov.tool == "VEP"
    assert prov.version == "v110"


def test_snpeff_provenance_parsed(tmp_path):
    body = (
        "##fileformat=VCFv4.2\n"
        '##SnpEffVersion="5.1d (build 2022-04-19)"\n'
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "chr1\t100\t.\tA\tG\t50\tPASS\tANN=G|missense_variant\n"
    )
    d = tmp_path / "results"
    d.mkdir(parents=True)
    _write_gz(d / "sample_snpEff.ann.vcf.gz", body)
    prov = compute_annotation_identity(tmp_path)
    assert prov.tool == "SnpEff"
    assert prov.version.startswith("5.1d")


def test_no_annotated_vcf_returns_none(tmp_path):
    body = (
        "##fileformat=VCFv4.2\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "chr1\t100\t.\tA\tG\t50\tPASS\tDP=30\n"
    )
    d = tmp_path / "results"
    d.mkdir(parents=True)
    _write_gz(d / "plain.vcf.gz", body)
    assert compute_annotation_identity(tmp_path) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_annotation_provenance.py -v`
Expected: FAIL with `ImportError: cannot import name 'compute_annotation_identity'` / `AnnotationProvenance`

- [ ] **Step 3: Write minimal implementation**

First, add the model to `src/contig/models.py` immediately after the `ReferenceIdentity` class:

```python
class AnnotationProvenance(BaseModel):
    """Which annotation tool + DB version a run's annotated VCF was produced by.

    Parsed from the annotated VCF's own header (the tool records its version there),
    captured for provenance. Research-use attribution only — this records WHAT tool
    and DB reported, never a significance judgement.
    """

    tool: Literal["VEP", "SnpEff"]
    version: str | None = None
    raw_header: str | None = None
```

Then add the field to `RunRecord` (next to `reference_identity`):

```python
    reference_identity: ReferenceIdentity | None = None
    annotation_identity: AnnotationProvenance | None = None
```

Then add the parser to `src/contig/bundle.py` (import `AnnotationProvenance` from `contig.models` and `_open_text` from `contig.verification.annotation_structural`):

```python
def _parse_annotation_header(header_lines: list[str]) -> "AnnotationProvenance | None":
    """Parse VEP/SnpEff tool + version from a VCF's header lines, or None."""
    for line in header_lines:
        if line.startswith("##VEP="):
            # ##VEP="v110" time="..." cache="..."
            value = line[len("##VEP="):].strip()
            version = value.split()[0].strip('"') if value else None
            return AnnotationProvenance(tool="VEP", version=version, raw_header=line.strip())
        if line.startswith("##SnpEffVersion="):
            value = line[len("##SnpEffVersion="):].strip().strip('"')
            return AnnotationProvenance(
                tool="SnpEff", version=value or None, raw_header=line.strip()
            )
    return None


def compute_annotation_identity(run_dir: Path) -> "AnnotationProvenance | None":
    """Locate an annotated VCF under run_dir and parse its annotation provenance.

    Globs `**/*.vcf.gz`, reads only each file's header (up to `#CHROM`), and returns
    the first VEP/SnpEff provenance found. None when no annotated VCF exists — never
    a fabricated tool/version. Reproduce-safe: derived from the output VCF, not a
    stored scratch path.
    """
    for vcf in sorted(Path(run_dir).glob("**/*.vcf.gz")):
        header_lines: list[str] = []
        with _open_text(vcf) as fh:
            for line in fh:
                if not line.startswith("#"):
                    break
                header_lines.append(line)
                if line.startswith("#CHROM"):
                    break
        prov = _parse_annotation_header(header_lines)
        if prov is not None:
            return prov
    return None
```

Add the imports at the top of `bundle.py`:

```python
from contig.models import AnnotationProvenance, ReferenceIdentity, RunRecord, sha256_file
from contig.verification.annotation_structural import _open_text
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_annotation_provenance.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/contig/models.py src/contig/bundle.py tests/test_annotation_provenance.py
git commit -m "feat(verify): AnnotationProvenance model + header parser (VEP/SnpEff tool+version) [C7 M1]"
```

---

### Task 3: Wire verifier + provenance into the run lifecycle

**Files:**
- Modify: `src/contig/runner.py` (`_discover_qc`: germline annotation gate)
- Modify: `src/contig/self_heal.py` (`_finalize`: set `record.annotation_identity`)
- Modify: `src/contig/methods.py` (render an annotation clause)
- Create: `tests/test_annotation_lifecycle.py`

**Interfaces:**
- Consumes: `evaluate_annotation_structural` (Task 1), `compute_annotation_identity` (Task 2), `AnnotationProvenance` (Task 2).
- Produces: annotation `QCResult`s appear in `_discover_qc(run_dir, "variant_calling")` when an annotated VCF exists; `record.annotation_identity` set at finalize; a methods clause when provenance is present.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_annotation_lifecycle.py
import gzip
from pathlib import Path

from contig.runner import _discover_qc
from contig.methods import methods_text  # existing public renderer; see note below
from contig.models import AnnotationProvenance, RunRecord


def _write_gz(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as fh:
        fh.write(body)
    return path


VEP_VCF = (
    "##fileformat=VCFv4.2\n"
    '##VEP="v110" cache="/vep/homo_sapiens/110_GRCh38"\n'
    '##INFO=<ID=CSQ,Number=.,Type=String,Description="... Format: Allele|Consequence">\n'
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
    "chr1\t100\t.\tA\tG\t50\tPASS\tCSQ=G|missense_variant\n"
)


def test_discover_qc_emits_annotation_checks_for_germline(tmp_path):
    _write_gz(tmp_path / "results" / "annotation" / "s_VEP.ann.vcf.gz", VEP_VCF)
    results = _discover_qc(tmp_path, assay="variant_calling")
    checks = {r.check for r in results}
    assert "annotation_present" in checks
    assert "annotation_complete" in checks


def test_methods_renders_annotation_clause():
    record = RunRecord(
        run_id="r1",
        pipeline="nf-core/sarek",
        pipeline_revision="3.5.1",
        target=_minimal_target(),  # see helper note
        input_checksums={},
        assay="variant_calling",
        annotation_identity=AnnotationProvenance(tool="VEP", version="v110"),
    )
    text = methods_text(record)
    assert "VEP" in text
    assert "v110" in text
```

> **Helper note:** reuse the existing `RunRecord`/`ExecutionTarget` construction helper already used in `tests/test_methods.py` (grep it for `_minimal_target` or the inline target dict) rather than inventing one — copy that exact fixture builder into this file's top. If `methods_text` is named differently, grep `src/contig/methods.py` for the public `def ...text` entry point and use that name.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_annotation_lifecycle.py -v`
Expected: FAIL — `annotation_present` not in checks (gate not wired) / no "VEP" in methods text.

- [ ] **Step 3: Write minimal implementation**

In `src/contig/runner.py`, inside `_discover_qc`, add a germline-gated block next to the existing `if assay == "variant_calling":` plausibility block (append after it, reusing the same VCF discovery pattern but selecting an *annotated* VCF):

```python
    # Annotation structural verification (capability C7, germline slice). Gated to
    # germline. We look for an annotated VCF (one carrying CSQ/ANN) anywhere under
    # the run and verify the annotation step ran over every record. Absent
    # annotation is handled inside evaluate_annotation_structural as UNVERIFIED, so
    # a plain (un-annotated) germline run is never dragged down — we simply don't
    # find an annotated VCF and skip. Research-use only: no significance claim.
    if assay == "variant_calling":
        from contig.verification.annotation_structural import (
            annotation_metrics,
            evaluate_annotation_structural,
        )

        for vcf in sorted(run_dir.rglob("*.vcf.gz")):
            if annotation_metrics(vcf).info_key is not None:
                results.extend(evaluate_annotation_structural(vcf))
                break
```

In `src/contig/self_heal.py`, in `_finalize`, right after the `record.reference_identity = ...` line, add:

```python
    record.annotation_identity = compute_annotation_identity(run_dir)
```

and extend the existing bundle import:

```python
from contig.bundle import (
    compute_annotation_identity,
    compute_output_checksums,
    compute_reference_identity,
    write_bundle,
)
```

In `src/contig/methods.py`, add an annotation clause function and call it where `_reference_clause(record)` is composed into the methods text:

```python
def _annotation_clause(record: RunRecord) -> str:
    """A clause attributing the annotation tool + DB version, if recorded."""
    ai = record.annotation_identity
    if ai is None:
        return ""
    version = f" {ai.version}" if ai.version else ""
    return (
        f" Variant annotation was performed with {ai.tool}{version}; annotations are"
        " reported as produced by that tool and its databases (research use)."
    )
```

Then append `_annotation_clause(record)` into the same assembled string that already includes `_reference_clause(record)` (grep `_reference_clause(` in `methods.py` for the composition site and add the annotation clause immediately after it).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_annotation_lifecycle.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/contig/runner.py src/contig/self_heal.py src/contig/methods.py tests/test_annotation_lifecycle.py
git commit -m "feat(verify): wire annotation structural verify + provenance into germline run lifecycle [C7 M1]"
```

---

### Task 4: Enable sarek annotation on the germline registry entry

**Files:**
- Modify: `src/contig/registry.py` (add `default_params` to the `variant_calling` entry)
- Modify: `tests/test_planner.py` (or wherever `_inject_default_params` is tested; grep first)
- Create/Modify: `tests/test_annotation_registry.py`

**Interfaces:**
- Consumes: `contig.cli._inject_default_params`, `contig.registry.select_pipeline`.
- Produces: `select_pipeline("variant_calling").default_params` includes the annotation tool; a germline run's params gain `tools` including `vep` unless the user already set `tools`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_annotation_registry.py
from contig.cli import _inject_default_params
from contig.registry import select_pipeline


def test_germline_default_params_enable_vep():
    entry = select_pipeline("variant_calling")
    assert "vep" in str(entry.default_params.get("tools", ""))


def test_inject_does_not_override_user_tools():
    params = {"tools": "haplotypecaller"}  # user chose their own tools
    _inject_default_params(params, "variant_calling")
    assert params["tools"] == "haplotypecaller"  # user value preserved


def test_inject_adds_default_when_absent():
    params = {}
    _inject_default_params(params, "variant_calling")
    assert "vep" in str(params.get("tools", ""))
```

> **Design note (resolve before coding):** confirm the exact `--tools` string against the sarek 3.5.1 docs the repo pins. Germline annotation typically needs the caller *and* the annotator, e.g. `"haplotypecaller,vep"`. Verify `_inject_default_params` merges without clobbering a user `tools` value (read its body in `cli.py:295` — it already implements non-override for somatic). If sarek requires `--step annotate` or a `--vep_cache`/`--snpeff_cache` to actually run annotation, capture that as an M1 caveat in the PRD's Technical Considerations rather than silently assuming the cache exists — the verifier already degrades to UNVERIFIED when annotation did not run, so a missing cache is surfaced honestly, not as a false pass.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_annotation_registry.py -v`
Expected: FAIL — `default_params` has no `tools` / no `vep`.

- [ ] **Step 3: Write minimal implementation**

In `src/contig/registry.py`, add `default_params` to the germline entry:

```python
    PipelineEntry(
        assay="variant_calling",
        pipeline="nf-core/sarek",
        revision="3.5.1",
        description="Germline short-variant calling (GATK best-practices), research use.",
        # Enable sarek's built-in annotation step (VEP -> CSQ) alongside the germline
        # caller so a Contig germline run also produces an annotated VCF (capability
        # C7). Research-use only: Contig verifies the annotation RAN, never adjudicates
        # significance. Injected non-destructively by _inject_default_params (a user
        # who sets their own --tools keeps it). Re-injected on rerun/resume, never
        # stored as a derived param (same reproduce-safety as somatic's --tools).
        default_params={"tools": "haplotypecaller,vep"},
    ),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_annotation_registry.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/contig/registry.py tests/test_annotation_registry.py
git commit -m "feat(assay): enable sarek annotation (VEP) on germline variant_calling [C7 M1]"
```

---

### Task 5: Full-slice integration test + docs sync

**Files:**
- Create: `tests/test_annotation_integration.py`
- Modify: `CHANGELOG.md` (Unreleased → Added)
- Modify: `docs/technical/CAPABILITY_ROADMAP.md` (mark C7 M1 shipped)

**Interfaces:**
- Consumes: everything above. This task adds no new production code; it proves the slice end-to-end on fixtures and records the change.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_annotation_integration.py
import gzip
from pathlib import Path

from contig.runner import _discover_qc
from contig.bundle import compute_annotation_identity


def _write_gz(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as fh:
        fh.write(body)
    return path


def test_annotated_germline_run_verifies_and_captures_provenance(tmp_path):
    body = (
        "##fileformat=VCFv4.2\n"
        '##VEP="v110" cache="/vep/homo_sapiens/110_GRCh38"\n'
        '##INFO=<ID=CSQ,Number=.,Type=String,Description="... Format: Allele|Consequence">\n'
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "chr1\t100\t.\tA\tG\t50\tPASS\tCSQ=G|missense_variant\n"
        "chr1\t200\t.\tC\tT\t50\tPASS\tCSQ=T|synonymous_variant\n"
    )
    _write_gz(tmp_path / "results" / "annotation" / "s_VEP.ann.vcf.gz", body)

    results = _discover_qc(tmp_path, assay="variant_calling")
    present = next(r for r in results if r.check == "annotation_present")
    complete = next(r for r in results if r.check == "annotation_complete")
    assert present.status == "pass"
    assert complete.status == "pass" and complete.value == 1.0

    prov = compute_annotation_identity(tmp_path)
    assert prov is not None and prov.tool == "VEP" and prov.version == "v110"


def test_unannotated_germline_run_yields_no_false_pass(tmp_path):
    body = (
        "##fileformat=VCFv4.2\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "chr1\t100\t.\tA\tG\t50\tPASS\tDP=30\n"
    )
    _write_gz(tmp_path / "results" / "variantcalling" / "s.vcf.gz", body)
    results = _discover_qc(tmp_path, assay="variant_calling")
    ann = [r for r in results if r.check.startswith("annotation_")]
    # An un-annotated germline run simply has no annotated VCF: no annotation check
    # fires (skipped), and NONE reports pass.
    assert all(r.status != "pass" for r in ann)
    assert compute_annotation_identity(tmp_path) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_annotation_integration.py -v`
Expected: PASS already if Tasks 1–4 are correct — if so, this test is the regression lock. If it FAILs, fix the wiring in Task 3 before proceeding.

- [ ] **Step 3: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS (no regressions). If `overall_verdict`/report snapshot tests assert a fixed QC-check count, update those snapshots to include the new annotation checks — this is expected, not a failure of this slice.

- [ ] **Step 4: Sync docs**

Add to `CHANGELOG.md` under `## [Unreleased]` → `### Added`:

```markdown
- **Research-use variant annotation, germline structural verify** (capability C7, M1).
  A Contig germline (`variant_calling`) run now enables nf-core/sarek's built-in
  annotation step (VEP → `CSQ`) and verifies it ran: a new
  `verification/annotation_structural.py` reports `annotation_present` and
  `annotation_complete` (WARN-capped, UNVERIFIED when no annotated VCF is found —
  never a false pass), and the annotation tool + version is parsed from the VCF
  header into a new `AnnotationProvenance` record, rendered in `contig methods`.
  Research-use only: Contig verifies the annotation EXECUTED, never adjudicates
  pathogenicity. Test-first; no real VEP/sarek run in CI.
```

In `docs/technical/CAPABILITY_ROADMAP.md`, change the C7 heading/table row status from `PLANNED` to `M1 SHIPPED (Unreleased) — germline structural verify + provenance; somatic (M2), plausibility (M3), VEP-vs-SnpEff concordance (M4) pending`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_annotation_integration.py CHANGELOG.md docs/technical/CAPABILITY_ROADMAP.md
git commit -m "test(verify): C7 M1 annotation slice integration test + changelog/roadmap sync [C7 M1]"
```

---

## Self-Review

**Spec coverage (PRD → task):**
- G1 (run + structurally verify, UNVERIFIED-when-absent) → Task 1 (`evaluate_annotation_structural`) + Task 3 (germline gate) + Task 5 (no-false-pass integration test). ✓
- G2 (attributed, reproducible provenance, rendered in methods) → Task 2 (`AnnotationProvenance` + parser) + Task 3 (`_finalize` capture + methods clause). ✓
- G3 (no over-claiming) → enforced by copy in every message/clause + Global Constraints; no pathogenicity code exists anywhere in the plan. ✓
- Enable sarek annotation via `default_params` → Task 4. ✓
- Test-first, no real tools in CI → every task; synthetic fixtures only. ✓
- Eval capture (annotation coverage) → `annotation_complete.value` (the coverage fraction) is the captured metric; folding into the C6 corpus is M5 (out of M1 scope, correctly deferred). ✓

**Placeholder scan:** No TBD/TODO left in production steps. Two explicit "resolve-before-coding" design notes (Task 3 helper name, Task 4 `--tools` string) point at exact grep targets and are legitimately environment-dependent, not hidden work.

**Type consistency:** `AnnotationMetrics(info_key, total_records, annotated_records)`, `AnnotationProvenance(tool, version, raw_header)`, `evaluate_annotation_structural`, `compute_annotation_identity`, `annotation_metrics` are used with identical signatures across Tasks 1–5. `QCResult(kind="structural")` matches the `QCKind` literal in `models.py`. `RunRecord.annotation_identity` defined in Task 2, consumed in Task 3.

**Known scope boundary:** M1 does not run VEP in CI; the `default_params` change (Task 4) is unit-tested for param injection only. The real sarek-annotation execution path is validated by the same manual/live gate the other assays use, not by CI — consistent with the repo's standing "no real nf-core run in CI" rule.

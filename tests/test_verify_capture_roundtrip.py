"""Phase 3 integration pins for the eval-concordance-capture slice (PRD M5/M5b/N1).

The four R4a families (`concordance_somatic_overlap`, `concordance_consequence`,
`somatic_plausibility`, `annotation_plausibility`) are now captured into
`RunRecord.verification_inputs` by `_discover_qc` (commits fa0a694, 702913f,
e758f7e). This file pins the INTEGRATION of that capture with the
verify-corpus scorer -- the round trip from a run record into a pending
VerificationCase (spec AC4-AC7), the load-bearing per-kind status-consistency
contract (the scorer must re-derive, from the captured PRE-BAND inputs, the
SAME status the run's QCResult carried), and the family-key enumeration (a
fifth concordance/plausibility capture key is a deliberate act).

Everything here is derived from the module evaluators' own `capture_metrics=`
out-params and the guard's own re-derivation -- never hand-invented shapes.

MESSAGE-STABILITY NOTE (task 3): the with/without-capture byte-identity pins
are ALREADY complete outside this file -- `test_verify_capture_somatic.py`
(full equality `_dump(with) == _dump(plain)` for concordance, plausibility,
swap, and Strelka2 evaluators), `test_verify_capture_annotation.py` (full
equality for both concordance layouts + the plausibility evaluator), and the
wiring test `test_discover_qc_writes_nothing_without_param` in
`test_verify_capture_wiring.py` (no-param byte-identity through `_discover_qc`
for both somatic and variant-calling runs). No consolidated test is added
here; the coverage is not merely adequate, it is stronger (full QCResult
equality, which subsumes message identity).
"""

from __future__ import annotations

import gzip
import re
from pathlib import Path

import contig.runner
from contig.models import ExecutionTarget, QCResult, RunRecord, TaskEvent, VerificationCase
from contig.verify_corpus import (
    _worst_status,
    evaluate_verify_case,
    should_capture_verification,
    verification_case_from_run,
)
from contig.verification.annotation_concordance import (
    evaluate_annotation_concordance_from_run,
)
from contig.verification.annotation_plausibility import evaluate_annotation_plausibility
from contig.verification.somatic_concordance import evaluate_somatic_concordance
from contig.verification.somatic_plausibility import evaluate_somatic_plausibility

# --- shared constants ---------------------------------------------------------

# The four R4a family keys `_discover_qc` can write (N1: pinned below by a
# source scan -- a fifth concordance/plausibility key is a deliberate act).
R4A_FAMILY_KEYS = {
    "concordance_somatic_overlap",
    "concordance_consequence",
    "somatic_plausibility",
    "annotation_plausibility",
}

# The four-family capture dict a full somatic + variant-calling run round-trips
# verbatim into a pending VerificationCase (per-family shapes mirror the wiring
# tests in test_verify_capture_wiring.py).
FOUR_FAMILIES: dict[str, dict[str, dict[str, float]]] = {
    "concordance_somatic_overlap": {
        "mutect2_vs_strelka2": {"value": 0.85, "n_shared": 20.0}
    },
    "concordance_consequence": {
        "vep_vs_snpeff": {"value": 0.95, "n_shared": 20.0}
    },
    "somatic_plausibility": {
        "TUMOR": {"median_vaf": 0.30, "somatic_variant_count": 12.0}
    },
    "annotation_plausibility": {
        "sample": {"real_consequence_fraction": 1.0, "intergenic_fraction": 0.0}
    },
}

# --- run-record builders (test_verify_capture.py precedent) -------------------


def _record(
    *,
    events: list[TaskEvent],
    qc_results: list[QCResult],
    verification_inputs: dict[str, dict[str, dict[str, float]]] | None,
) -> RunRecord:
    return RunRecord(
        run_id="r",
        pipeline="nf-core/sarek",
        pipeline_revision="3.4.1",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="w"),
        input_checksums={},
        parameters={},
        events=events,
        qc_results=qc_results,
        assay="somatic_variant_calling",
        verification_inputs=verification_inputs,
    )


def _green(verdict: str) -> list[QCResult]:
    return [QCResult(check=f"x:{verdict}", status=verdict, message=verdict, kind="metric")]  # type: ignore[arg-type]


def _succeeded(*, qc_results, verification_inputs):
    """A run record with all tasks COMPLETED (the capture predicate's first arm)."""
    return _record(
        events=[TaskEvent(process="P", status="COMPLETED", exit=0)],
        qc_results=qc_results,
        verification_inputs=verification_inputs,
    )


# --- VCF fixtures (mirroring the module tests' fixtures) ----------------------


def _gz(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as fh:
        fh.write(body)
    return path


def _sites(n: int, chrom: str = "chr1", start: int = 100):
    """n distinct (chrom, pos, ref, alt) site tuples, deterministic and disjoint."""
    return [(chrom, start + i, "A", "G") for i in range(n)]


# Somatic concordance fixture (FILTER-PASS sites, no sample columns needed).
_CONC_HEADER = "##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"


def _crec(chrom, pos, ref, alt):
    return f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t.\tPASS\t.\n"


def _conc_vcf(path: Path, sites) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_CONC_HEADER + "".join(_crec(*s) for s in sites))
    return path


# Somatic plausibility fixture (Mutect2 two-sample, tumor AF driven).
_PL_HEADER = (
    "##fileformat=VCFv4.2\n"
    "##tumor_sample=TUMOR\n"
    "##normal_sample=NORMAL\n"
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tNORMAL\tTUMOR\n"
)


def _prec(chrom, pos, ref, alt, tumor_fmt, normal_fmt="0/0:0.0:10,0:10", fmt="GT:AF:AD:DP"):
    return f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t.\tPASS\t.\t{fmt}\t{normal_fmt}\t{tumor_fmt}\n"


def _pl_vcf(path: Path, recs) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_PL_HEADER + "".join(recs))
    return path


def _recs_with_af(af, n, start_pos=100):
    """n biallelic records, each tumor AF == af (deterministic median == af)."""
    return [
        _prec("chr1", start_pos + i, "A", "G", f"0/1:{af}:14,6:20")
        for i in range(n)
    ]


# Annotation fixtures (VEP CSQ / SnpEff ANN headers, two-file layout).
VEP_HEADER = (
    "##fileformat=VCFv4.2\n"
    '##INFO=<ID=CSQ,Number=.,Type=String,Description="Consequence annotations from '
    'Ensembl VEP. Format: Allele|Consequence|IMPACT|SYMBOL">\n'
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
)

ANN_HEADER = (
    "##fileformat=VCFv4.2\n"
    '##INFO=<ID=ANN,Number=.,Type=String,Description="Functional annotations: '
    "'Allele | Annotation | Annotation_Impact | Gene_Name'\">\n"
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
)

# A CSQ header whose Format string omits "Consequence" -> unresolvable.
CSQ_NO_CONSEQUENCE_HEADER = (
    "##fileformat=VCFv4.2\n"
    '##INFO=<ID=CSQ,Number=.,Type=String,Description="Consequence annotations from '
    'Ensembl VEP. Format: Allele|IMPACT|SYMBOL">\n'
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
)


def _csq_body(sites, term: str = "missense_variant", symbol: str = "GENE1") -> str:
    return "".join(
        f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t50\tPASS\tCSQ={alt}|{term}|MODERATE|{symbol}\n"
        for chrom, pos, ref, alt in sites
    )


def _ann_body(sites, term: str = "missense_variant", symbol: str = "GENE1") -> str:
    return "".join(
        f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t50\tPASS\tANN={alt}|{term}|MODERATE|{symbol}\n"
        for chrom, pos, ref, alt in sites
    )


# --- guard-side harness --------------------------------------------------------


def _predicted(family: str, family_inputs: dict, assay: str = "somatic_variant_calling") -> str:
    """The status `evaluate_verify_case` re-derives for ONE family from the
    captured pre-band inputs (spec AC4-AC7: values, never stored statuses)."""
    case = VerificationCase(
        case_id="pin",
        description="status-consistency pin (synthetic)",
        source="synthetic",
        assay=assay,
        inputs={family: family_inputs},
    )
    return evaluate_verify_case(case).families[family]


def _module_worst(results: list[QCResult]) -> str:
    """The family-level status the module evaluator emitted for the same metric
    values, reduced exactly the way the guard reduces (worst non-informational)."""
    return _worst_status(r.status for r in results if not r.informational)


# --- 1. ROUND-TRIP: run record -> pending VerificationCase (spec AC4-AC7) -------


def test_round_trip_four_families_verbatim_warn():
    record = _succeeded(qc_results=_green("warn"), verification_inputs=FOUR_FAMILIES)

    assert should_capture_verification(record) is True
    case = verification_case_from_run(record)
    # The four-family dict is copied verbatim: keys, pair/sample keys, values.
    assert case.inputs == FOUR_FAMILIES
    assert set(case.inputs) == R4A_FAMILY_KEYS
    # The description states the pipeline, the driving verdict, and every family.
    assert "nf-core/sarek" in case.description
    assert "warn" in case.description
    for family in R4A_FAMILY_KEYS:
        assert family in case.description


def test_round_trip_four_families_verbatim_fail():
    record = _succeeded(qc_results=_green("fail"), verification_inputs=FOUR_FAMILIES)

    assert should_capture_verification(record) is True
    assert verification_case_from_run(record).inputs == FOUR_FAMILIES


def test_round_trip_pass_verdict_or_empty_inputs_do_not_capture():
    passed = _succeeded(qc_results=_green("pass"), verification_inputs=FOUR_FAMILIES)
    assert should_capture_verification(passed) is False

    empty = _succeeded(qc_results=_green("warn"), verification_inputs={})
    assert should_capture_verification(empty) is False


# --- 2. PER-KIND STATUS CONSISTENCY (the load-bearing pin) ----------------------
# For each family, captured inputs (taken from the module evaluator's own
# `capture_metrics=` out-param on real fixtures) must re-derive through the
# guard to the SAME status the run's QCResult carried for those values.


def test_somatic_overlap_status_consistency_warn_pass_unverified(tmp_path):
    # warn: 17 shared + 3 Mutect2-only -> union 20, raw jaccard 17/20 = 0.85
    # (< the 0.90 warn band, above the 10-site floor).
    shared = _sites(17)
    mut = _conc_vcf(tmp_path / "mutect2.vcf", shared + _sites(3, start=100_000))
    strl = _conc_vcf(tmp_path / "strelka.vcf", shared)
    capture: dict[str, dict[str, float]] = {}
    results = evaluate_somatic_concordance([mut], [strl], capture_metrics=capture)
    assert capture["mutect2_vs_strelka2"] == {"value": 17 / 20, "n_shared": 20.0}
    assert _module_worst(results) == "warn"
    assert _predicted("concordance_somatic_overlap", capture) == "warn"

    # pass: identical 20-site callers -> jaccard 1.0.
    sites = _sites(20)
    mut = _conc_vcf(tmp_path / "mutect2_pass.vcf", sites)
    strl = _conc_vcf(tmp_path / "strelka_pass.vcf", sites)
    capture = {}
    results = evaluate_somatic_concordance([mut], [strl], capture_metrics=capture)
    assert capture["mutect2_vs_strelka2"] == {"value": 1.0, "n_shared": 20.0}
    assert _module_worst(results) == "pass"
    assert _predicted("concordance_somatic_overlap", capture) == "pass"

    # unverified: union 5 < the 10-site floor; raw values still captured.
    few = _sites(5)
    mut = _conc_vcf(tmp_path / "mutect2_few.vcf", few)
    strl = _conc_vcf(tmp_path / "strelka_few.vcf", few)
    capture = {}
    results = evaluate_somatic_concordance([mut], [strl], capture_metrics=capture)
    assert capture["mutect2_vs_strelka2"] == {"value": 1.0, "n_shared": 5.0}
    assert _module_worst(results) == "unverified"
    assert _predicted("concordance_somatic_overlap", capture) == "unverified"


def test_consequence_status_consistency_warn_pass_unverified(tmp_path):
    # warn: 20 shared sites, 17 agreeing consequences -> raw 17/20 = 0.85
    # (< the 0.90 warn band, above the 10-site floor). One run dir per case:
    # the run-level wrapper counts ANNOTATION-DECLARING files, so a second
    # case's VCFs in the same dir would make the layout ambiguous.
    warn_dir = tmp_path / "warn"
    agree = _sites(17)
    disagree = _sites(3, start=100_000)
    _gz(warn_dir / "vep.vcf.gz", VEP_HEADER + _csq_body(agree) + _csq_body(disagree))
    _gz(
        warn_dir / "snpeff.vcf.gz",
        ANN_HEADER + _ann_body(agree) + _ann_body(disagree, term="synonymous_variant"),
    )
    capture: dict[str, dict[str, float]] = {}
    results = evaluate_annotation_concordance_from_run(warn_dir, capture_metrics=capture)
    assert capture["vep_vs_snpeff"] == {"value": 17 / 20, "n_shared": 20.0}
    assert _module_worst(results) == "warn"
    assert _predicted("concordance_consequence", capture) == "warn"

    # pass: identical 20-site annotators -> agreement 1.0.
    pass_dir = tmp_path / "pass"
    sites = _sites(20)
    _gz(pass_dir / "vep.vcf.gz", VEP_HEADER + _csq_body(sites))
    _gz(pass_dir / "snpeff.vcf.gz", ANN_HEADER + _ann_body(sites))
    capture = {}
    results = evaluate_annotation_concordance_from_run(pass_dir, capture_metrics=capture)
    assert capture["vep_vs_snpeff"] == {"value": 1.0, "n_shared": 20.0}
    assert _module_worst(results) == "pass"
    assert _predicted("concordance_consequence", capture) == "pass"

    # unverified: 5 shared < the 10-site floor; raw values still captured.
    few_dir = tmp_path / "few"
    few = _sites(5)
    _gz(few_dir / "vep.vcf.gz", VEP_HEADER + _csq_body(few))
    _gz(few_dir / "snpeff.vcf.gz", ANN_HEADER + _ann_body(few))
    capture = {}
    results = evaluate_annotation_concordance_from_run(few_dir, capture_metrics=capture)
    assert capture["vep_vs_snpeff"] == {"value": 1.0, "n_shared": 5.0}
    assert _module_worst(results) == "unverified"
    assert _predicted("concordance_consequence", capture) == "unverified"


def test_somatic_plausibility_status_consistency_pass_warn_fail(tmp_path):
    # pass: median_vaf 0.30 in-band, 12 biallelic records in [10, 100000].
    vcf = _pl_vcf(tmp_path / "tumor.vcf", _recs_with_af(0.30, 12))
    capture: dict[str, dict[str, float]] = {}
    results = evaluate_somatic_plausibility(vcf, capture_metrics=capture)
    assert capture == {"TUMOR": {"median_vaf": 0.30, "somatic_variant_count": 12}}
    assert _module_worst(results) == "pass"
    assert _predicted("somatic_plausibility", capture) == "pass"

    # warn: median_vaf 0.99 above the 0.95 warn ceiling (count stays in-band).
    vcf = _pl_vcf(tmp_path / "tumor_warn.vcf", _recs_with_af(0.99, 12))
    capture = {}
    results = evaluate_somatic_plausibility(vcf, capture_metrics=capture)
    assert capture == {"TUMOR": {"median_vaf": 0.99, "somatic_variant_count": 12}}
    assert _module_worst(results) == "warn"
    assert _predicted("somatic_plausibility", capture) == "warn"

    # fail: no biallelic records -> the pack's fail_below: 1 floor; the
    # uncomputable median_vaf is OMITTED from the capture (nothing to re-derive
    # from), so the guard sees only the count -- and still lands on the same
    # fail. Note: "unverified" is structurally unreachable for THIS family via
    # the capture: every captured metric is computable and every rule in
    # SOMATIC_PLAUSIBILITY_PACK is banded (pass/warn/fail only), and when
    # nothing is computable the family is honestly ABSENT rather than empty
    # (pinned by the wiring tests) -- so the third status pinned here is the
    # pack's fail floor, not unverified.
    vcf = _pl_vcf(tmp_path / "tumor_empty.vcf", [])
    capture = {}
    results = evaluate_somatic_plausibility(vcf, capture_metrics=capture)
    assert capture == {"TUMOR": {"somatic_variant_count": 0}}
    assert _module_worst(results) == "fail"
    assert _predicted("somatic_plausibility", capture) == "fail"


def test_annotation_plausibility_status_consistency_pass_warn_unverified(tmp_path):
    # pass: 2/3 real (missense) >= the 0.10 floor, 1/3 intergenic <= 0.95.
    body = VEP_HEADER + (
        "chr1\t100\t.\tA\tG\t50\tPASS\tCSQ=G|missense_variant|MODERATE|BRCA1\n"
        "chr1\t200\t.\tC\tT\t50\tPASS\tCSQ=T|missense_variant|MODERATE|BRCA1\n"
        "chr1\t300\t.\tG\tA\t50\tPASS\tCSQ=A|intergenic_variant|MODIFIER|.\n"
    )
    vcf = tmp_path / "vep_pass.vcf"
    vcf.write_text(body)
    capture: dict[str, dict[str, float]] = {}
    results = evaluate_annotation_plausibility(vcf, capture_metrics=capture)
    assert capture == {
        "sample": {"real_consequence_fraction": 2 / 3, "intergenic_fraction": 1 / 3}
    }
    assert _module_worst(results) == "pass"
    assert _predicted("annotation_plausibility", capture) == "pass"

    # warn: real_consequence_fraction 1/20 = 0.05 below the 0.10 floor;
    # intergenic 19/20 = 0.95 sits exactly ON the 0.95 ceiling (not above).
    body = VEP_HEADER + (
        "".join(
            f"chr1\t{200 + i}\t.\tA\tG\t50\tPASS\tCSQ=G|intergenic_variant|MODIFIER|.\n"
            for i in range(19)
        )
        + "chr1\t100\t.\tA\tG\t50\tPASS\tCSQ=G|missense_variant|MODERATE|BRCA1\n"
    )
    vcf = tmp_path / "vep_warn.vcf"
    vcf.write_text(body)
    capture = {}
    results = evaluate_annotation_plausibility(vcf, capture_metrics=capture)
    assert capture == {
        "sample": {"real_consequence_fraction": 0.05, "intergenic_fraction": 0.95}
    }
    assert _module_worst(results) == "warn"
    assert _predicted("annotation_plausibility", capture) == "warn"

    # unverified: unresolvable CSQ Format -> both metrics uncomputable; the
    # module emits two explicit unverified checks, the capture holds an empty
    # sample dict, and the runner's empty-sample filter writes the family as an
    # EMPTY dict -- which the guard honestly re-derives to unverified (the
    # wired shape, not a hand-built one).
    body = CSQ_NO_CONSEQUENCE_HEADER + (
        "chr1\t100\t.\tA\tG\t50\tPASS\tCSQ=G|MODERATE|BRCA1\n"
    )
    vcf = tmp_path / "vep_unresolvable.vcf"
    vcf.write_text(body)
    capture = {}
    results = evaluate_annotation_plausibility(vcf, capture_metrics=capture)
    assert capture == {"sample": {}}
    assert _module_worst(results) == "unverified"
    assert _predicted("annotation_plausibility", {}) == "unverified"


# --- 4. FAMILY-KEY ENUMERATION (N1) ---------------------------------------------
# The capture-key write set is pinned by scanning `_discover_qc`'s source for
# `capture_inputs["..."]` assignments: adding a fifth concordance/plausibility
# family -- or any new capture key -- is a deliberate act that must update this
# test. Deterministic; no runtime import games.


def test_family_key_enumeration_pins_the_four_r4a_families():
    src = Path(contig.runner.__file__).read_text()
    writes = set(re.findall(r'capture_inputs\["([^"]+)"\]', src))

    # Every family `_discover_qc` can write today, enumerated from the source:
    # the four R4a keys plus the eight pre-existing families.
    assert writes == {
        "multiqc",
        "germline",
        "rnaseq_plausibility",
        "rnaseq_composition",
        "scrnaseq",
        "methylseq",
        "ampliseq",
        "mag",
        "concordance_somatic_overlap",
        "concordance_consequence",
        "somatic_plausibility",
        "annotation_plausibility",
    }
    # The R4a four are exactly the concordance/plausibility families written.
    assert {
        "concordance_somatic_overlap",
        "concordance_consequence",
        "somatic_plausibility",
        "annotation_plausibility",
    } == R4A_FAMILY_KEYS & writes

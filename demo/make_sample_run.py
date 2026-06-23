"""Generate the demo's guaranteed self-heal PASS bundle.

This is a STANDALONE generator. It drives Contig's real self-heal loop with an
injected fake executor (the same pattern the test suite uses, see
tests/test_self_heal.py and tests/test_cli.py) so the demo always shows the same
story: a run that OOM-fails (exit 137) on its first attempt, then self-heals to a
clean, verified PASS on the retry.

Nothing here is mocked except the executor (the thing that would otherwise shell
out to Nextflow). The detector, the diagnosis, the patch proposer, the bundle
writer, the QC verdict, and the signing path are all the real engine, so the
artifact this writes is a genuine Contig run bundle a partner can verify.

Run it:

    uv run python demo/make_sample_run.py

It writes a signed bundle into a temporary runs directory, then copies
run_record.json, signature.json, and the public key into demo/sample-run/. The
signing key it uses is a THROWAWAY demo key generated on the fly (never a real
secret); the matching public key is saved so a partner can verify the signature.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from contig import signing
from contig.models import ExecutionTarget
from contig.self_heal import self_heal_run

# The run id the demo refers to everywhere (DEMO.md, the rendered report). It is
# also the bundle directory name under demo/, so `contig verify sample-run
# --runs-dir demo` (which looks for demo/<run-id>/) resolves to demo/sample-run/.
RUN_ID = "sample-run"

# A two-column Nextflow trace TSV. The first attempt reports the STAR_ALIGN task
# FAILED with exit 137 (out of memory); the retry reports it COMPLETED with a
# realtime and a peak memory so the bundle carries resource actuals too.
_TRACE_OOM = (
    "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\n"
    "1\tab/cd\t1\tNFCORE_RNASEQ:STAR_ALIGN (CONTROL_REP1)\tFAILED\t137\t-\t-\t-\n"
)
_TRACE_OK = (
    "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\t"
    "duration\trealtime\t%cpu\tpeak_rss\n"
    "1\tab/cd\t1\tNFCORE_RNASEQ:STAR_ALIGN (CONTROL_REP1)\tCOMPLETED\t0\t"
    "2026-06-23\t12m 4s\t12m 2s\t320.0%\t14.8 GB\n"
)

# A MultiQC general-stats payload good enough for the RNA-seq rule pack to return
# a PASS verdict (two samples, both with a healthy unique-mapping and assignment
# rate), so the verified result is an honest pass, not an "unverified".
_GOOD_MQC = json.dumps(
    {
        "report_general_stats_data": [
            {
                "CONTROL_REP1": {
                    "uniquely_mapped_percent": 92.4,
                    "percent_assigned": 86.1,
                    "total_reads": 31_200_000.0,
                },
                "TREATED_REP1": {
                    "uniquely_mapped_percent": 91.0,
                    "percent_assigned": 84.7,
                    "total_reads": 29_800_000.0,
                },
            }
        ]
    }
)


def _demo_executor():
    """A fake executor: OOM on attempt 1, then a clean PASS with QC on the retry.

    The first call writes an OOM trace plus an out-of-memory log line and returns
    nonzero, so the self-heal loop detects an OOM and applies its safe resource
    bump. The second call writes a completed trace, a results tree with the
    MultiQC json (so the QC verdict is a real PASS) and an output file (so the
    bundle carries output checksums), and returns zero.
    """
    state = {"attempt": 0}

    def execute(cmd, trace_path):
        state["attempt"] += 1
        trace = Path(trace_path)
        run_dir = trace.parent
        if state["attempt"] == 1:
            trace.write_text(_TRACE_OOM)
            (run_dir / "run.log").write_text(
                "Process NFCORE_RNASEQ:STAR_ALIGN (CONTROL_REP1) terminated with "
                "an error exit status (137). Process killed: out of memory (exit 137)."
            )
            return 1
        # The retry succeeds: write the completed trace, the QC json, and an
        # output file so the verified PASS rests on real captured artifacts.
        trace.write_text(_TRACE_OK)
        (run_dir / "run.log").write_text("Pipeline completed successfully.")
        mqc = run_dir / "results" / "multiqc"
        mqc.mkdir(parents=True, exist_ok=True)
        (mqc / "multiqc_data.json").write_text(_GOOD_MQC)
        (run_dir / "results" / "star_salmon").mkdir(parents=True, exist_ok=True)
        (run_dir / "results" / "star_salmon" / "salmon.merged.gene_counts.tsv").write_text(
            "gene_id\tCONTROL_REP1\tTREATED_REP1\nENSG00000139618\t1204\t1187\n"
        )
        return 0

    return execute


def main() -> None:
    if not signing.signing_available():
        raise SystemExit(
            "Signing is unavailable: install the cryptography package "
            "(it is a Contig dependency, so `uv sync` provides it)."
        )

    # A throwaway demo signing key, generated fresh each run. It is NOT a real
    # secret: the matching public key is saved next to the bundle so a partner can
    # verify the signature offline.
    private_key, public_key = signing.generate_keypair()

    out_dir = Path(__file__).resolve().parent / "sample-run"
    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="contig-demo-") as tmp:
        runs_dir = Path(tmp) / "runs"
        work_dir = Path(tmp) / "work"
        target = ExecutionTarget(
            backend="local", container_runtime="docker", work_dir=str(work_dir)
        )

        # write_bundle signs the record when CONTIG_SIGNING_KEY is set in the
        # environment, so set it just for this generation.
        import os

        os.environ["CONTIG_SIGNING_KEY"] = private_key
        try:
            record = self_heal_run(
                pipeline="nf-core/rnaseq",
                revision="3.26.0",
                profiles=["test", "docker"],
                target=target,
                input_paths=[],
                runs_dir=runs_dir,
                run_id=RUN_ID,
                executor=_demo_executor(),
                params={"outdir": str(runs_dir / RUN_ID / "results")},
                nextflow_version="26.04.4",
                max_attempts=3,
            )
        finally:
            del os.environ["CONTIG_SIGNING_KEY"]

        run_dir = runs_dir / RUN_ID
        shutil.copy(run_dir / "run_record.json", out_dir / "run_record.json")
        shutil.copy(run_dir / "signature.json", out_dir / "signature.json")
        # Carry the results tree too, so `contig verify` checks the signature AND
        # the output integrity (the record hashes these files); without them
        # verify would honestly report them as missing.
        results_src = run_dir / "results"
        results_dst = out_dir / "results"
        if results_dst.exists():
            shutil.rmtree(results_dst)
        if results_src.is_dir():
            shutil.copytree(results_src, results_dst)
        (out_dir / "PUBLIC_KEY.txt").write_text(
            "This is the public verification key for demo/sample-run.\n"
            "The matching private key was a throwaway, generated for this demo "
            "and discarded; it is NOT a real secret.\n"
            "Verify the bundle with:\n"
            f"  uv run contig verify {RUN_ID} --runs-dir demo --json\n\n"
            f"public_key={public_key}\n"
        )

    verdict = record.verdict
    repairs = len(record.repair_history)
    print(f"Wrote signed self-heal bundle to {out_dir}")
    print(f"  run id:  {RUN_ID}")
    print(f"  verdict: {verdict}")
    print(f"  repairs: {repairs} self-heal step(s)")
    print("Verify it with:")
    print(f"  uv run contig verify {RUN_ID} --runs-dir demo --json")


if __name__ == "__main__":
    main()

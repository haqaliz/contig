# Card — feat/self-heal-custom-work-dir

**Source:** inline brief (no GitHub issue; `gh issue list` shows only closed #13).
**Branch:** `feat/self-heal-custom-work-dir/aliz`
**Origin:** picked by `/contig-next` from the C2 deferral list.

## Brief

Close C2 deferral item (a) (`docs/technical/CAPABILITY_ROADMAP.md:518-520`):
`read_task_errors` hardcodes `Path(run_dir)/"work"` (`src/contig/runner.py:1198`)
while Nextflow is given `target.work_dir` (`src/contig/nfconfig.py:100`, settable via
`--work-dir` at `src/contig/cli.py:400`), so on any custom work dir it returns `""`
and the sole call site (`src/contig/self_heal.py:1310`) diagnoses on `run.log` alone —
losing the `.command.err` text the detector is documented to need, and thinning every
captured pending-corpus case.

Thread the real work dir through (keep the `run_dir`-only default so
`tests/test_runner.py:60-90` passes untouched) and make an unreadable work dir an
explicit honest note rather than a silent empty string.

**Caveat to design for, not paper over:** an `s3://` work dir (mandatory on AWS Batch
per `src/contig/nfconfig.py:119-121`) can never be read from local disk, so this fixes
local/HPC custom dirs only and must not claim to restore Batch self-heal.

**Constraints:** read-path change only — `LaunchManifest` deliberately stores no
`work_dir` (`src/contig/models.py:408-415`), so no manifest, verdict, exit-code, or
signature change. Test-first, synthetic fixtures, no real Nextflow in CI.

## Roadmap citation (verbatim)

> Also deferred, filed by the inert-repair-honesty slice (C2), none fixed here:
> **(a)** `read_task_errors` hardcodes `Path(run_dir)/"work"` (`runner.py:1077`)
> while Nextflow is actually given `target.work_dir` (`nfconfig.py:100`) — the
> detector goes blind on a custom `--work-dir`;

*(The roadmap's `runner.py:1077` line number is stale; the current location is
`runner.py:1191-1214`.)*

## Related roadmap risk

`docs/ROADMAP.md:219` R8 — "Running on customer compute is too brittle/varied
(HPC vs cloud vs local)". AWS Batch is the sharp case: `nfconfig.py:119-121`
*requires* an `s3://` work dir there.

## Sibling item already fixed (do not re-pick)

Item **(d)** of the same deferral list (dashboard `FAILURE_CLASSES` omitting five
classes) is already closed — `dashboard/lib/derive.ts:278-299` mirrors all 20
literals. The roadmap prose is stale there.

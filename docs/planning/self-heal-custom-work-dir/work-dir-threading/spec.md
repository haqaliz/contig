# Aspect spec — work-dir-threading

Parent PRD: [`../prd.md`](../prd.md). This is the **only** aspect; the feature is not
decomposed further.

## Problem slice

`read_task_errors` looks for `.command.err` under `<run_dir>/work`; Nextflow was told
`target.work_dir`. Make the function read the work dir the run actually used, say so
honestly when that dir is structurally unreadable, and stop it (and its sibling
`read_run_log`) from raising during diagnosis.

## User outcome

A run launched with `--work-dir` gets a real diagnosis and real self-heal instead of
`tool_crash` @ 0.4 and an inert repair loop. A run on a remote work dir gets an explicit
statement of the limit instead of silence.

## In scope

- R1 `read_task_errors` takes the work dir directly (PRD M1, with the signature
  correction below).
- R2 `self_heal.py:1310` passes `current_target.work_dir` (PRD M2).
- R3 A remote work dir returns a self-labelled, salient-token-bearing note (PRD M3, S1).
- R4 A local absent work dir still returns `""` (PRD M4).
- R5 `file://` is read as the local path it names (PRD S2).
- R6 Neither `read_task_errors` nor `read_run_log` raises (PRD M6).
- R7 The missing end-to-end `self_heal_run` test (PRD M5).

## Signature correction to PRD M1 (deviation, with reason)

PRD M1 says `read_task_errors(run_dir, work_dir, ...)`. **Verified against the code:
`run_dir` is referenced on exactly one line** (`runner.py:1198`, `work = Path(run_dir) /
"work"`) and nowhere else in the body. Once `work_dir` is supplied, `run_dir` is a dead
parameter — the same defect class M1 exists to eliminate, one level down.

**Shipped signature:** `read_task_errors(work_dir, max_tasks=10, tail_lines=40)`.

The four existing tests still keep their assertions verbatim; each call changes from
`read_task_errors(tmp_path)` to `read_task_errors(tmp_path / "work")`, which is
*more* faithful to what each was always testing.

## Out of scope

Everything in the PRD's Out of Scope section, unchanged: no remote log fetching, no
launch-time warning, no corpus relabelling, no `detect.py` change, no Snakemake, no
`LaunchManifest` field.

## Acceptance criteria (testable)

| # | Criterion |
|---|---|
| A1 | `self_heal_run` with a custom `work_dir` holding a classifiable `.command.err` diagnoses that specific class. **Fails before the change** (`tool_crash`). |
| A2 | `read_task_errors("s3://bucket/work")` returns a note naming the work dir; performs no filesystem call. |
| A3 | The note contains at least one `_SALIENT_TOKENS` entry (`corpus.py:207-219`) and is a single line. |
| A4 | The note is prefixed `[contig]` and does not imitate tool output. |
| A5 | `read_task_errors(<absent local dir>)` returns `""` exactly. |
| A6 | `read_task_errors("file:///abs/work")` reads `/abs/work`. |
| A7 | `read_task_errors("C:\\work")` is treated as local, not remote (rule keys on `://`). |
| A8 | `read_task_errors("")` is local-and-absent → `""`. |
| A9 | An unreadable `.command.err` is skipped; the other tasks' text still returns. |
| A10 | A non-UTF-8 `run.log` decodes with replacement instead of raising. |
| A11 | All four pre-existing `tests/test_runner.py` assertions unchanged; only their call argument differs. |
| A12 | `tests/test_self_heal.py:301` asserts real captured content, not bare truthiness. |
| A13 | Full suite green; `git diff --stat src/contig/models.py` empty. |

## Dependencies & sequencing

None external. Internal order: the pure helpers and the reader must land before the
call-site wiring, because A1 depends on both.

## Risks specific to this aspect

- Removing `run_dir` is a wider signature change than the PRD wrote. Blast radius
  verified as three references repo-wide (PRD R6).
- A2 asserts "no filesystem call" — implement by checking the remote rule **before**
  constructing any `Path`, and assert it with a monkeypatched `Path.is_dir` that fails
  the test if called.

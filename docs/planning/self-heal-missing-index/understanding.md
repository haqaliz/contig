# Understanding: self-heal-missing-index

Phase-2 dig note (grounded in a code map of the worktree). File:line refs are to
`src/contig/` unless noted.

## What the work is really asking

Make the `missing_index` self-heal patch *actually recover the run* instead of
being a no-op re-run. The detect → diagnose → propose scaffolding is all present
and correct; only the **apply / repair action** is hollow.

## What already exists (do NOT rebuild)

- **Detection is real and tested.** `detect.py:159-176` emits
  `failure_class="missing_index"` (confidence 0.85) when a log line contains one of
  `not found` / `missing` / `no such file` AND (`index` or one of `.fai .bai .tbi
  .csi`). Covered by `tests/test_detect.py` (`test_missing_fai_is_missing_index`).
  The brief's open question "confirm detect emits missing_index" is **answered:
  yes**. Detection is out of scope for changes.
- **Patch proposal exists.** `repair.py:56-65` proposes
  `Patch(kind="reference", operation={"build_index": True},
  risk="needs_confirmation", expected_signal="index present")`. Note **risk =
  needs_confirmation** → this is a *gated* patch, so the loop only applies it via
  the approval gate or `--auto-approve`.
- **FailureClass `missing_index`** is in the `FailureClass` Literal
  (`models.py:182-199`).

## The actual gap

`apply_patch` (`self_heal.py:274-330`) handles `kind in ("param","reference")` by
merging `operation["set_param"]` into params. A `build_index` patch has **no
`set_param`**, so `swap is None`, params/target are returned unchanged, and the
re-run is identical → fails again. The code comment at ~293-295 states this
explicitly, and `tests/test_self_heal.py:test_apply_patch_reference_build_index_is_rerun_only`
asserts the current no-op behavior (that test will need to change).

## The architectural fork (the key PRD decision)

"Build the index" has two viable shapes:

- **(A) Run an external build command** (e.g. `samtools faidx ref.fasta` for a
  `.fai`, `samtools index x.bam` for a `.bai`) before the re-run. This is a **new
  action shape**: a command that is not the Nextflow argv. The existing `Executor`
  seam (`runner.py:72`, `Callable[[list[str], Path], int]`) is Nextflow-specific
  (must write a trace), so (A) likely needs a **new injected seam** (an
  `IndexBuilder` callable) with a default that shells out and a fake in tests —
  mirroring how `Executor` is faked. Requires mapping the missing-index path
  (parsed from `diagnosis.evidence`) → a build command, which is tool/extension
  specific (feasibility risk: how many index kinds, how tool-agnostic).
- **(B) Let the pipeline regenerate the index** by mutating params (e.g. clearing a
  stale `--star_index` / `--fasta_fai` path so nf-core builds it itself). This is a
  **config mutation** that fits the *existing* `apply_patch` `set_param` path — much
  smaller, no new seam, no external tool execution. Limit: only works for indices
  the pipeline can self-build, and may not address a truly missing standalone index
  a user must supply.

This fork decides the whole shape of the slice. It is the primary thing to resolve
in the interview.

## Other open questions

- **Index scope:** all of `.fai/.bai/.tbi/.csi/.dict/STAR/BWA`, or a small declared
  starting set (the detector already keys on `.fai .bai .tbi .csi`)?
- **Missing vs stale:** detection only covers fully-missing ("no such file"); is
  stale-index detection/repair in scope, or strictly missing? (Lean: missing only.)
- **Corpus:** a pending case is already captured on failure
  (`self_heal.py:399-409`). Do we also **seed a golden** `missing_index` case into
  `src/contig/data/detector_corpus.jsonl` this slice (moat #2), or is the existing
  detector test enough?
- **Outcome vocabulary:** success should record a distinct `RepairStep.outcome`
  (e.g. `built_index_and_retried`) mirroring the resource-aware-retry slice's
  `gave_up_at_ceiling` pattern (`self_heal.py:544`, `models.py:225-233`).
- **Surface footprint:** repair_history + `repair_progress.jsonl` only (like the
  prior slice), or also a report/verdict line?

## Guardrails check (CLAUDE.md)

Layer 2 (run + self-heal) only; no Layer-1 authoring. No raw-read egress — the
index build runs on the user's compute. Bounded by the existing `max_attempts`.
Test-first via the injected seam; **no real tool/Nextflow execution in tests**.
Gets better as base models improve (a smarter diagnoser flows through the same
repair). No contradictions found between the brief and the code, except that
detection is already done (a simplification, not a conflict).

# Understanding — reference-mismatch-detector (Phase 2 dig)

Synthesized from two read-only dig agents (pre-flight/launch path; ReferenceIdentity
+ verification/corpus conventions). All file:line refs are in this worktree.

## What the work is really asking

A **pre-flight** guard that catches a reference whose FASTA and GTF use
incompatible contig-naming schemes (the classic `chr1` vs `1`) **before** an
nf-core run launches and silently produces empty quantification that still passes
structural QC. Explicit `--fasta`/`--gtf` mode only; iGenomes (`--genome KEY`)
skips (no local files to inspect). Deterministic, local, no network.

## Where it attaches (the chokepoint)

`src/contig/cli.py` → `_dispatch_run()` (the function shared by `run` and `rerun`).
The reference is resolved at **cli.py:380** via `params.update(resolve_reference(...))`
(`reference.py:21`), which **absolutizes and existence-checks** the paths. Insert
the new check **immediately after** that, gated on `"fasta" in params and "gtf" in
params` — which is exactly the explicit-mode branch; iGenomes returns `{"genome":
...}` and is skipped for free. It lands **before** `launch.json` is written
(cli.py:415) and **before** `self_heal_run()` (cli.py:418), so a bad config never
starts a run.

**One chokepoint covers both surfaces.** The dashboard run-trigger
(`dashboard/app/api/runs/launch/route.ts` → `dashboard/lib/runs.ts:dispatchRealRun`
at :511) does **not** re-implement reference logic — it spawns the same
`contig run` CLI subprocess. So a check in `_dispatch_run()` protects CLI **and**
dashboard with no TS changes.

## The established pre-flight pattern to mirror

Existing pre-flight validators return `list[str]` of problems (empty = OK), and the
CLI raises `typer.Exit(code=1)` when non-empty:
- `validate_samplesheet(path) -> list[str]` (`samplesheet.py:40`, used cli.py:373-378)
- `preflight_aws_batch` / `preflight_slurm -> list[str]` (`nfconfig.py:104/130`)
- `resolve_reference(...)` raises `ReferenceError` (`reference.py:17`), caught at cli.py:380-383

→ The new check should follow the **`list[str]` + `typer.Exit(1)`** refuse pattern,
NOT emit a post-run `QCResult`. (QCResults are verify-time artifacts; this is a
launch gate.) This is the natural fit for a hard "refuse before compute" guard.

## Reuse / inputs available

- At the chokepoint, `params["fasta"]`/`params["gtf"]` are **absolute, validated**
  paths — ready to open. (`ReferenceIdentity` itself is a *finalize-time* capture
  in `bundle.py:compute_reference_identity` (:76-109), computed later than
  pre-flight — so the detector shares the same FASTA/GTF *inputs* but does not
  depend on the ReferenceIdentity object being built yet. The brief's "reuse
  ReferenceIdentity" is really "reuse the same resolved reference paths.")
- **Gzip handling:** mirror `concordance.py:_open_text` (:79-84): `gzip.open(p,"rt")`
  when `.gz`, else `open(p)`. Need to handle `.fa.gz` / `.gtf.gz`.
- **No existing FASTA/GTF reader** — this is net-new parsing (FASTA: lines starting
  `>`, take the first whitespace-delimited token; GTF: column 1 of non-`#` lines).
  Both should be **bounded/streamed**, not slurped (genomes are large).
- Tests: `tests/verification/`, real files via `tmp_path`, helper writers (see
  `test_concordance.py`). No mocks, no network. Mirror this.

## Open questions for the interview (real decisions)

1. **Severity: refuse (hard block, exit 1) vs WARN-and-proceed?** Brief says "refuse
   or WARN." A guaranteed-empty-output naming mismatch argues for **refuse**; but a
   partial/scaffold reference must not false-positive. Likely: refuse only on a
   *disjoint* naming scheme; otherwise pass. Need the rule pinned.
2. **The mismatch rule (conservative, to avoid false positives).** Candidate: compare
   the **set** of contig names. If **no** GTF contig appears in the FASTA contig set
   → refuse (naming-scheme mismatch / guaranteed empty). If the GTF is a subset (or
   overlaps) → pass (legit partial reference). Special-case the `chr`-prefix pattern
   for a precise message ("FASTA uses `chr1`, GTF uses `1`"). Confirm this rule.
3. **Corpus seeding — likely OUT of scope.** The detector corpus
   (`data/detector_corpus.jsonl`, `FailureCase` with `events`+`log_text`) models
   *run failures diagnosed from logs*. A pre-flight refuse has no run/events/logs, so
   it doesn't fit the corpus shape. The brief's "seeds corpus cases" was aspirational;
   recommend deferring corpus integration (and the new `reference_mismatch`
   `FailureClass`) unless we want it for the eventual C2 *repair*. Confirm defer.
4. **New `FailureClass`?** `models.py:200-217` has `missing_reference` but no
   `reference_mismatch`. Only needed if we wire to corpus/self-heal — see #3. Likely
   defer.
5. **Surface footprint:** CLI stderr refuse message only this slice? (No dashboard/
   HTML/report change needed, since it blocks at launch.) Confirm.
6. **Parsing robustness / honesty default:** strip `>` and take token before first
   whitespace (FASTA); skip `#` lines, split on tab, take field 0 (GTF). Empty/garbage
   files or zero parseable contigs → treat as "uncomparable" = **pass** (never a
   false refuse). Confirm the honesty default (skip/pass when uncomparable, never
   fabricate a mismatch).

## Guardrails check (CLAUDE.md)

- Layer 2 (pre-flight verify) ✓ · No raw-read egress (reads only reference files,
  local) ✓ · No over-claiming (refuse only on a clear disjoint mismatch; pass when
  uncomparable) ✓ · Test-first ✓.

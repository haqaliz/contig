# PRD: self-heal-dict-index (GATK sequence-dictionary self-heal)

Status: draft for review. Owner: aliz. Branch: `feat/self-heal-dict-index/aliz`.
Capability: **C2 — self-heal breadth** (next single-file kind on the shipped
index-build seam). Sources: `docs/planning/_card/issue.md` (contig-next handoff),
`_card/understanding.md` (Phase-2 dig), `docs/technical/CAPABILITY_ROADMAP.md:108-119`,
the prior slice's PRD `docs/planning/self-heal-index-family/prd.md`.

## Problem Statement

Contig's self-heal loop already detects a **missing single-file index**, builds it, and
retries — `.fai` (`samtools faidx`), `.bai` (`samtools index`), `.tbi` (`tabix`), `.csi`
(`bcftools index`) all ship (v0.5.0, `CHANGELOG.md`). One common companion is still
missing: the **GATK sequence dictionary** (`ref.dict`). GATK/Picard tools refuse to run
when the FASTA's `.dict` is absent, and this is a frequent failure on the **already-shipped
germline assay** (sarek/HaplotypeCaller require a sequence dictionary beside the
reference). Today such a run dead-ends in a manual fix.

`.dict` was **explicitly deferred** from the `.bai`/`.tbi`/`.csi` slice
(`self-heal-index-family/prd.md:132-133, 221`) for one reason: it is the only kind whose
build input is **not** the indexed path minus its suffix. This slice closes that gap.

**Why it's the moat (`CLAUDE.md`, `CAPABILITY_ROADMAP.md:114-119`):** unattended-completion
rate is the headline reliability metric; every recovered failure mode raises it and adds a
golden corpus case that sharpens the detector for everyone. Self-heal is the surface that
"gets better as base models improve." No incumbent (Galaxy, Terra, Seqera, DNAnexus)
autonomously diagnoses and repairs a missing sequence dictionary — they restart
mechanically (`FEATURES.md:61-68`).

## Goals & Success Metrics

- **G1 — Recover a missing `.dict` end to end.** A germline run that fails with a
  missing-sequence-dictionary error is detected as `missing_index`, the source FASTA is
  resolved, `samtools dict` builds `ref.dict`, and the pipeline re-runs to success — the
  recorded outcome is `built_index_and_retried`. *Metric:* a build-and-retry integration
  test (injected executor + injected builder) goes RED→GREEN.
- **G2 — Honest give-up, never a false pass.** When no FASTA companion exists on disk the
  outcome is `index_unresolvable`; when the build returns non-zero it is
  `index_build_failed`; both leave the verdict FAIL. *Metric:* two negative tests assert
  the exact outcome strings and a non-pass verdict.
- **G3 — Correct source resolution.** `ref.dict` resolves to the first existing of
  `ref.fasta`/`ref.fa`/`ref.fasta.gz`/`ref.fa.gz`, and the build argv is
  `["samtools","dict","-o","<ref.dict>","<resolved-fasta>"]`. *Metric:* a per-kind
  exact-argv test plus a deriver unit test covering each candidate extension and the
  none-exist case.
- **G4 — No regression, no real tool, no network.** Baseline (**869 passed, 1 skipped**)
  stays green; the four existing kinds keep recovering unchanged; `samtools`/GATK never
  run in CI (injected builder). *Metric:* full `uv run pytest` green.

## User Personas & Scenarios

- **A, lone computational biologist** runs nf-core/sarek germline against a reference
  downloaded without its `.dict`; today gets a cryptic GATK USER ERROR and a dead run.
  Wants Contig to notice, build the dict, and finish unattended.
- **C, core facility** runs many references for many PIs; wants the same missing-companion
  failure to self-heal consistently rather than land in a per-PI manual queue.

## Requirements

### Must-have (this slice)

- **R1 — Detector recognizes a missing `.dict` (targeted branch).** Add a
  sequence-dictionary-aware rule to `detect.py` that classifies `missing_index` when a log
  line names a `.dict` file **and** asserts its absence, tolerating GATK's wording. GATK's
  real message is *"…Fasta dict file …/ref.dict for reference …/ref.fasta **does not
  exist**…"* — which the current first-stage filter (`"not found"`, `"missing"`, `"no such
  file"` at `detect.py:165`) does **not** match. The new branch must accept `.dict` +
  any of (`does not exist`, `not found`, `no such file`, `missing`). Keep it **narrow**
  (low blast-radius): do not broaden the global notfound keyword set, and do not let a
  genuine wrong-reference/contig-mismatch line classify as a buildable missing dict.
- **R2 — Token extractor recognizes `.dict`.** Add `dict` to the index-token regex at
  `self_heal.py:58` so `_parse_missing_index` returns `(<path>.dict, ".dict")`.
- **R3 — Generalized source-derivation table.** Refactor `_INDEX_BUILD` from
  `{ext: build_argv_fn}` to `{ext: (derive_source_fn, build_argv_fn)}`. The four existing
  kinds use a pure suffix-strip deriver (behavior unchanged). `.dict` uses a
  filesystem-probing deriver that, given the `.dict` path and the run dir, returns the
  first existing FASTA companion among `ref.fasta`, `ref.fa`, `ref.fasta.gz`, `ref.fa.gz`
  (extension **replaced**, not stripped), or `None` if none exists.
- **R4 — Build command.** `.dict` argv is `["samtools","dict","-o","<index_path>",
  "<resolved-fasta>"]` — output is the missing `.dict` path itself (GATK looks for
  `ref.dict`, i.e. replace-extension), input is the resolved FASTA. Stays in the
  `samtools` family already used for `.fai`/`.bai`.
- **R5 — Honest outcomes, reusing the existing machinery.** Wire through
  `_apply_patch_and_maybe_build` (`self_heal.py:390-439`) unchanged in spirit: a resolved
  source that builds (rc 0) → `built_index_and_retried`; an unresolvable source (deriver
  returns `None`) → `index_unresolvable`; a failed build (rc≠0) → `index_build_failed`.
  Reuse the `missing_index` `FailureClass` and the `Patch(kind="reference",
  operation={"build_index": True})` proposal (`repair.py:56`) — **no model change, no new
  FailureClass, no IndexBuilder seam change**.
- **R6 — Corpus seed.** Add one `missing-index-dict` case to
  `data/detector_corpus.jsonl` (`expected_class:"missing_index"`), `log_text` using a
  realistic GATK sequence-dictionary message whose wording trips the R1 rule.
- **R7 — Tests-first.** Strict TDD mirroring `tests/test_self_heal.py:1047-1147` and the
  per-kind parametrize at `:1312-1342`, plus `tests/test_detect.py`. **RED baseline
  first:** a test proving a missing-`.dict` failure does NOT recover today (parses to
  `None` → `index_unresolvable`) before the GREEN generalization. No mocks of real tools;
  inject the builder/executor; no network.

### Should-have

- The new detector branch's intent is commented (why `.dict` needs its own absence
  wording, and why it stays narrow to avoid colliding with reference-mismatch).
- The deriver's FASTA candidate list is a single named constant so a future kind can reuse
  it.

### Nice-to-have (explicitly later, not now)

- A normalizing hint when a FASTA companion is found but oddly named.
- BAM/CRAM `.csi`, STAR/BWA directory indexes (different shape; see Out of Scope).

## Technical Considerations

- **Insertion point unchanged.** The build is still invoked from
  `_apply_patch_and_maybe_build` at the gated-apply sites (`self_heal.py:554/594/642`);
  only parse/derive/dispatch internals change. `apply_patch` stays pure.
- **The "pure, no I/O" contract relaxes for derivation only.** `_index_build_command`
  (`self_heal.py:84-101`) currently does a pure `removesuffix`. The `.dict` deriver must
  probe the filesystem, so the deriver receives the run dir (cwd) and may stat candidate
  paths. Suffix-strip derivers ignore the cwd and stay pure. The build itself already runs
  through the injected `IndexBuilder` (`runner.py:83-126`) — unchanged.
- **Output/input self-consistency.** `out = index_path` (the missing `ref.dict`),
  `input = resolved FASTA`. This avoids the `ref.fasta.dict` vs `ref.dict` trap (GATK uses
  replace-extension).
- **Detector ordering.** `missing_index` is checked before `missing_reference`
  (`detect.py:159` vs `:178`); a `.dict` line that also names `reference`/`genome` must
  resolve to `missing_index` first. Cover with a detect test.
- **Reproducibility/verification impact.** No change to verdict-reduction or the near-zero
  false-pass guarantee: an unrecovered run stays FAIL. The build lands in
  `repair_history` and the bundle, strengthening the auditable trail. No raw-read egress —
  the dict is built from a local FASTA on the user's compute.
- **Corpus/eval flywheel.** The new seed extends `missing_index` support; over time real
  `.dict` recoveries flow into the corpus (C6).

## Data Model / Contracts

- **No model change.** `RepairStep.outcome` reuses the three existing free-`str` values;
  `Patch`, `FailureClass`, `apply_patch`'s contract, and the `IndexBuilder` seam type are
  unchanged.
- **Internal change only:** `_INDEX_BUILD` value shape becomes a `(deriver, argv_fn)`
  tuple; `_index_build_command` consults the deriver. Internal, no public surface change.
- **Corpus** gains one `FailureCase` row (`expected_class="missing_index"`) in
  `data/detector_corpus.jsonl`.

## Risks & Open Questions

- **R-risk-1 — GATK message wording drift.** The exact missing-dict phrasing varies (GATK4
  wrapper vs Picard `CreateSequenceDictionary`). Mitigation: the R1 branch keys on a
  `.dict` token + a small set of absence phrasings, robust to tool wording; the corpus
  seed uses a realistic line and a detect test pins it. *Open:* confirm the precise
  phrasing set from a real sarek failure if one is available; otherwise ship the
  conservative set (`does not exist`, `not found`, `no such file`, `missing`).
- **R-risk-2 — False resolution to a wrong FASTA.** If multiple companions exist, the
  deriver picks the first by a fixed priority order; a wrong pick still produces a dict the
  re-run either accepts or rejects (terminating honestly within `max_attempts`). Mitigation:
  deterministic candidate order; the build target is the exact `.dict` path the log named.
- **R-risk-3 — `.dict` misread as reference-mismatch.** A wrong-reference (contig
  mismatch) is a *different* failure (deferred repair). Mitigation: R1 requires an
  *absence* phrasing, which a contig-mismatch error does not carry; keep the branch narrow.
- **R-risk-4 — Re-proposal loop.** At most one build per index path within `max_attempts`
  (existing bound). Cover with a termination test.
- **Open:** none blocking — the three design decisions (build tool = `samtools dict`;
  targeted detector branch; generalized `(deriver, argv)` table) were resolved in the
  interview.

## Out of Scope (confirmed deferred)

- **Directory-shaped STAR/BWA indexes** (multi-file/dir, not a single parsed path).
- **BAM/CRAM `.csi`** (`samtools index -c`) and **stale-index detection**.
- **The reference/build-*mismatch* repair** (wrong reference, not a buildable missing
  dict) — its own deferred C2 slice.
- **Peak-RSS-informed resource scaling.**
- **Dashboard/HTML surface** — outcomes land in `repair_history`/JSONL, matching the prior
  index slices.
- Any clinical claim; any Layer-1 workflow authoring.

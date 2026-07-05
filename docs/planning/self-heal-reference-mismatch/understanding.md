# Understanding — self-heal-reference-mismatch (C2 reference/build-mismatch repair)

Phase 2 deep-dig note. Grounded in a full code map (path:line cited inline).

## What the work is really asking

Turn the v0.7.0 pre-flight contig-naming **refusal** into an **autonomous recovery**:
when a `contig run` is refused because the FASTA and GTF use disjoint contig naming
that is an unambiguous `chr`-prefix asymmetry (`chr1…` vs `1…`), harmonize the
seqnames so they match, record the harmonization for reproduce, and proceed —
instead of exiting with code 1.

## Affected code (confirmed by the map)

- **Detector (pre-flight, pure):** `src/contig/reference_check.py`. `check_reference_consistency(fasta, gtf) -> list[str]` returns problem strings; disjoint-only rule (`reference_check.py:50-54`). The `chr`-asymmetry is reported **only as a suffix on the message string** (`reference_check.py:55-64`) — there is no structured "which side is chr-prefixed" field. The raw sets come from `fasta_contigs()` / `gtf_contigs()`, and `_all_chr_prefixed()` (`reference_check.py:44`) is the predicate we reuse.
- **Pre-flight gate:** `_dispatch_run` in `cli.py:262`; the check + refusal is `cli.py:392-408`, refusing via `raise typer.Exit(code=1)`, overridable by `--allow-reference-mismatch` (`cli.py:221/282`). Runs **after** `resolve_reference`, **before** the manifest write (`cli.py:422-441`) and `self_heal_run` (`cli.py:444-461`).
- **Launch manifest:** `LaunchManifest` (`models.py:298-323`) carries `allow_reference_mismatch: bool = False` — the exact precedent for persisting a launch-time decision so `rerun` (`cli.py:508/527`) and `resume` (`cli.py:1097/1116`) reproduce it.
- **Provenance:** `ReferenceIdentity` (`models.py:186-195`) computed at finalize (`self_heal.py:811`, `bundle.py:76-109`), hashes the fasta/gtf and lands in `run_record.json`. A harmonized run would hash the **harmonized** file (sha differs) and naturally wants a `harmonized: bool` / `harmonized_from` field here.
- **Self-heal seams (if we go the repair-step route):** `IndexBuilder = Callable[[list[str], Path], int]` (`runner.py:86`), injected as a kwarg-default through `self_heal_run` / `_apply_patch_and_maybe_build`; `RepairStep.outcome` strings like `built_index_and_retried` / `index_unresolvable` (`self_heal.py:483-519`); patches proposed in `repair.py` with a `risk` tier.
- **FailureClass:** a `Literal` (`models.py:200-217`) — only `missing_reference` exists; **no `reference_mismatch` member yet**.
- **Detector corpus:** `src/contig/data/detector_corpus.jsonl`; each line is a `FailureCase` with `events` + `log_text` + `expected_class` — i.e. keyed on a **runtime failed-task log signature** (`corpus.py:28`, `models.py:337-345`).
- **Test scaffolds to mirror:** `tests/test_reference_check.py` (real `tmp_path` FASTA/GTF, no mocks) for pure harmonizer logic; `tests/test_self_heal.py` `_heal` + closure fakes for loop integration.

## The central design fork (MUST resolve in the interview)

The map surfaced **two hook points**, and they are not equivalent:

1. **Pre-flight harmonization at the gate** (`cli.py:392-408`). The detection already
   lives here, so the repair lives here too: compute the asymmetry from the raw sets,
   write a harmonized copy to run scratch, repoint `params["gtf"]`/`["fasta"]`, persist
   the decision in the manifest + `ReferenceIdentity`, and proceed. **Cleanest fit** —
   the mismatch is a *structural pre-flight* condition, not a runtime task failure.

2. **Full self-heal repair step** — new `reference_mismatch` `FailureClass`, a
   `detect.py` rule, a `repair.py` patch, a new injectable harmonizer seam, handled in
   `_apply_patch_and_maybe_build`. This matches the shipped index-self-heal *pattern*,
   BUT the self-heal loop and the corpus operate on **runtime failed-task log
   signatures** — and this mismatch is caught **before any task runs**. Shoe-horning a
   pre-flight structural condition into the runtime-failure machinery is a poor fit,
   and would mean *letting the silent failure happen* to detect it from logs — the
   opposite of what v0.7.0 set out to do.

### Contradiction to surface (not paper over)

The handoff brief says "seed a new **`reference_mismatch` golden corpus case**." But
`detector_corpus.jsonl` feeds the **runtime log-signature detector** (`detect.py`),
which classifies *failed tasks*. A pre-flight structural check is not that detector,
so a corpus seed there only makes sense if we want the **runtime** detector to also
recognize the *downstream symptom* of an un-harmonized mismatch (e.g. an empty count
matrix / "0 features assigned"). The corpus-seeding goal therefore needs reframing:
either (a) seed the runtime symptom as a separate safety net, or (b) defer corpus
seeding and capture eval data via the harmonization decision in provenance instead.
This is the moat-vs-architecture question the interview must settle.

## Recommendation going into the interview

- **Hook point 1 (pre-flight gate)** is the honest architecture: repair where we
  detect. Keep it a deterministic, pure harmonizer with the gate as the only side-
  effecting caller.
- **Harmonize the GTF, not the FASTA** (provisional): the GTF is annotation and far
  smaller; the FASTA headers are the alignment ground truth. Write the harmonized copy
  to run scratch — **never mutate the user's original in place**.
- **Safe-harmonization predicate must be strict:** only when adding/stripping `chr`
  makes the two sets *match*. If they still disagree after the candidate rewrite (true
  wrong-assembly), there is **no safe repair** — keep refusing honestly.
- **Risk tier:** harmonization mutates a reference input → treat as `needs_confirmation`
  semantically; reconcile with the existing `--allow-reference-mismatch` escape hatch
  and whether the default is auto-proceed or propose-and-approve.

## Guardrails check (CLAUDE.md)

Layer 2 (self-heal/execution) ✓. No raw-read egress (rewrites a local annotation) ✓.
No correctness over-claiming (harmonize only an unambiguous naming asymmetry; refuse a
true wrong-assembly) ✓. Test-first, synthetic fixtures, no nf-core in CI ✓. **Not**
Layer 1 (we are not authoring a workflow; we are repairing reference inputs to a
consumed pipeline) ✓.

## Open questions for the interview

1. **Hook point:** pre-flight gate repair (recommended) vs full self-heal repair step.
2. **Corpus/eval capture:** how to honor "seed a `reference_mismatch` corpus case"
   given the corpus is runtime-log-keyed (reframe per the contradiction above).
3. **Auto vs approval:** auto-harmonize-and-proceed by default, or
   propose-and-require-approval; relation to `--allow-reference-mismatch`.
4. **Predicate edge cases:** `MT`/`chrM`, scaffold/`GL…`/`KI…` contigs, partial-overlap
   (subset) references the detector already passes today.
5. **Which file is rewritten** (GTF vs FASTA) and the scratch output location.
6. **Outcome/decision naming** (e.g. `harmonized_reference_and_proceeded`) and the
   honest give-up when no safe harmonization exists.

## Update — RESOLVED (contig-alias-harmonization, `feat/contig-alias-harmonization/aliz`)

The `MT`/`chrM` per-contig alias edge case flagged in open question 4 above is now
**RESOLVED**. `plan_harmonization` (`src/contig/reference_harmonize.py`) resolves each
GTF contig against a FASTA-driven candidate set (prefix variants ∪ alias group,
intersected with the actual FASTA contig set): mitochondrion `M`↔`MT` is a universal
code constant, and a small curated GRCh38 scaffold table
(`src/contig/data/contig_aliases.tsv`) covers common unplaced scaffolds. This also
resolves the residual case (implied by the same edge-case question) where autosomes
already match and only the mito spelling differs — previously silently skipped
because harmonization was gated behind the disjoint-only detector. Scaffold/`GL…`/
`KI…` contigs beyond the seeded GRCh38 table remain future work (deferred, not
resolved).

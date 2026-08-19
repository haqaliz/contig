# PRD: verify-time concordance capture

Status: draft for review. Owner: aliz. Branch: `feat/verify-time-concordance-capture/aliz`.
Sources: `docs/planning/_card/issue.md` (contig-next handoff brief), `_card/understanding.md`
(deep dig), `docs/technical/CAPABILITY_ROADMAP.md` C6, CHANGELOG v0.53.0 (R4a).
Capability: **C6 eval flywheel — closing the last R4a capture deferral**.

## Problem Statement

The C6 eval flywheel captures pre-band verification inputs for every run-dir-derived
family (multiqc, plausibility, composition, scrnaseq, germline, somatic/annotation
plausibility, `concordance_somatic_overlap`, `concordance_consequence`), so the corpus
can learn how the verdict behaves on real runs. Two concordance families are still
excluded: **`concordance_genotype`** (germline) and **`concordance_spearman`**
(RNA-seq + single-cell), because their second call set / count matrix exists only at
`contig verify` time (user-supplied path or autorun), never in the run dir. The v0.53.0
record committed the revisit trigger: "a verify-time capture channel that does not
break the signed payload." This slice ships that channel.

**Evidence it's real:** the scorer already enumerates and thresholds both families
(`verify_corpus.py:90-110`) and the holdout already scores 6 concordance cases — the
only missing piece is the producer-side capture. The gap is documented as "still
deferred" at `verify_corpus.py:80-89` and in CHANGELOG v0.53.0 with this exact
revisit trigger.

## Goals & Success Metrics

- **G1 — Verify-time capture.** When `contig verify` runs any of the six concordance
  flags (`--concordance-vcf`, `--concordance-auto`, `--concordance-counts`,
  `--concordance-counts-auto`, `--concordance-sc-counts`, `--concordance-sc-counts-auto`)
  and the evaluator returns a non-empty result list, a pending `VerificationCase` for the
  computed family lands in `<runs_dir>/pending_verify_corpus.jsonl`.
  *Metric:* round-trip pin — capture → promote → re-derive under current thresholds →
  statuses match.
- **G2 — Signed payload untouched.** The verify path never writes `run_record.json` or
  `signature.json`; capture is a sidecar append only.
  *Metric:* pre-existing signature tests pass unchanged; a test asserts no write to the
  bundle dir on verify.
- **G3 — Guards unmoved.** `verify-guard` (95.5%), `eval-guard` (92.9%),
  `heal-guard` (100%), `reproduce-guard` (13/14) baselines and their corpora are
  byte-identical.
  *Metric:* the four guard commands pass bare; `cmp`-level stability of the four
  baseline/corpus files.
- **G4 — Honest contract preserved.** At most WARN, never changes the verify exit code,
  `unverified` below the shared floor; capture never alters any QC result or the
  concordance list itself.
  *Metric:* all pre-existing concordance tests pass unchanged; new tests pin the
  additive/back-compat shape of the `capture_metrics` out-params.

## User Personas & Scenarios

- **Internal (the founder/CI):** runs `contig verify --concordance-counts <matrix>` on a
  real run, then `contig verify-case-promote` labels the captured case, growing the
  golden corpus with a real concordance outcome. Over time the per-family scores in
  `verify_baseline.json` per_family become non-tautological.
- **The corpus (moat #2):** a real verify-time concordance case is band-sensitive by
  construction — stored pre-band `{value, n_shared}` re-derive under current thresholds,
  so a band change measurably moves the stored case (mutation-control pin).

## Requirements

### Must-have (this slice)

- **R1 — Producer out-params.** `evaluate_concordance`, `evaluate_count_concordance`,
  and `evaluate_sc_count_concordance` gain an additive `capture_metrics:
  dict[str, dict[str, float]] | None = None` out-param (the somatic precedent,
  `somatic_concordance.py:120-149`): populated with raw (unrounded) `{"value", "n_shared"}`
  on **both** the normal and the too-few-shared paths, so a low-n case stays
  self-describing. Absent, behavior is byte-identical. The single-cell path reuses the
  count-core out-param (one change, both RNA-seq and sc inherit it).
- **R2 — Verify-time hook.** In `verify()` immediately after the six-way dispatch
  (cli.py:1651), when `concordance` is a non-empty list: build a `VerificationCase` and
  `append_verify_case` it to `<runs_dir>/pending_verify_corpus.jsonl` (the shared
  `self_heal.py:1763` default path). Always-on, no flag, gated only on "results exist"
  (user decision).
- **R3 — Case shape.** `case_id = f"{run_id}-verify-concordance"`, `source =
  "pending:{run_id}"` (so the existing promote rewrite works unchanged), `assay` from the
  record, `expected_verdict = None` until promote, inputs keyed `"S1"` (user decision)
  under the family key (`concordance_genotype` | `concordance_spearman`).
- **R4 — Promote compatibility.** No change to `verify-case-promote`; a captured case
  promotes with `--expected-verdict`, dedupes against golden by case_id, auto-snapshots
  the grown golden into history.
- **R5 — Round-trip + mutation-control pins.** Mirror `tests/test_verify_capture_roundtrip.py`:
  capture → promote → re-derive under current thresholds → per-family status matches the
  scorer's; a threshold change flips a stored case (family_packs override seam).
- **R6 — Tests-first, no real tools.** Every path CI-tested with synthetic fixtures and
  injected seams (autorun second tools never run in CI; manual gate unchanged). No new
  dependency.

### Should-have

- The family-key enumeration pin (`test_verify_capture_roundtrip.py:438-464`) scans
  **runner.py only**, so a cli.py-side writer does not trip it; extend the pin's
  docstring/coverage deliberately to also assert the verify-time writer's family keys,
  or note why not.
- Honest-scope CHANGELOG entry and `CAPABILITY_ROADMAP.md` C6 superseded-note update
  (the R4a deferral is closed for all four concordance families).
- **Output byte-stability pin** (review-gate resolution): with capture active vs not,
  `verify`'s text and JSON output is byte-identical — the capture channel is invisible
  to every existing output path, never adding a line, key, or side effect to the
  user-facing surfaces.

### Nice-to-have (explicitly later, not now)

- Dashboard surface for pending verify-time cases (existing pending-review tool reads
  the same sidecar file — likely already works; verify only).
- Capture-time echo of "captured pending verification case <id>" in verify's text output.

## Technical Considerations

- **Hook point:** `verify()` at cli.py:1461-1710; dispatch closes at cli.py:1651 with
  `record`, `runs_dir`, `run_id`, and the `concordance` list all in scope — one
  insertion covers all four terminal paths. The verify path is strictly read-only on the
  signed payload (load at cli.py:1614; no `write_bundle`; drift re-hash ignores
  unrecorded files, cli.py:1442-1443; signature covers the record, not sidecars,
  bundle.py:38-39).
- **Sidecar:** reuse `append_verify_case` (`verify_corpus.py:340-345`, pure append) and
  the shared default path `<runs_dir>/pending_verify_corpus.jsonl` — already the
  `verify-case-promote --pending` default (cli.py:2510), so no CLI change.
- **Out-param precedent:** `somatic_concordance.py:126-146` and
  `annotation_concordance.py:162-187`; raw stats exist internally as
  `ConcordanceStats` (`concordance.py:135-148`) and `CountConcordanceStats`
  (`count_concordance.py:177-191`). QCResult carries no n_shared field (message-text
  only), so the out-param — not message parsing — is the honest channel.
- **Reproducibility/verification impact:** none on run semantics; the verify verdict,
  exit code, and concordance list are untouched. The capture is observable only in the
  sidecar, which is outside every signed artifact.
- **Dependencies:** none blocking; stdlib-only; no new package.

## Risks & Open Questions

- **R-risk-1 — case_id collision.** `verification_case_from_run` uses `f"{run_id}-verify"`
  (verify_corpus.py:479); a same-run finalize case exists in the same sidecar. Resolved:
  distinct `f"{run_id}-verify-concordance"` (user decision). A repeated `contig verify`
  of the same run appends a second line with the same case_id — **resolved
  (review-gate decision): dedupe-on-append in the verify-time writer only** (skip when
  `case_id` is already present in the pending file), keeping promote unambiguous; the
  shared `append_verify_case` is untouched and the finalize path unaffected.
- **R-risk-2 — Autorun results capture.** Autorun paths run real tools (bcftools,
  kallisto, STARsolo) never exercised in CI; capture happens after the tool result
  exists, so the capture itself is pure I/O and CI-tested with injected seams. **Decision
  (review-gate): the second tool's identity is deliberately NOT part of the case** —
  the corpus is band-sensitive, not tool-sensitive, and a fabricated tool name (for
  user-supplied paths) would be worse than none. Stated as a decision, not a gap, so no
  future slice "fixes" it by guessing tool names.
- **R-risk-3 — "Always-on" semantics.** A user who runs `contig verify` without any
  concordance flag writes nothing; a user with a flag writes one sidecar line. The
  sidecar lives at runs_dir root, outside the bundle, and is invisible to drift and
  signature checks. **Decision (review-gate): capture fires even on a copied/foreign
  bundle** — the finalize-time capture writes the sidecar unconditionally
  (`self_heal.py:1759-1765`), so verify-time capture matching that posture is
  consistent; the user chose `--runs-dir`. Accepted (user decision).
- **Open:** none blocking — all interview decisions resolved.

## Out of Scope (confirmed deferred)

- Any change to concordance verdict semantics (WARN-capped, exit-code-neutral,
  `unverified` floors) — capture observes, never alters.
- Any change to the scorer, holdout corpus, baselines, or the four guards.
- Verify-time capture for other families (all others are run-dir-derived and already
  captured).
- Dashboard UI work (the existing pending-review tool reads the same file; verify only).
- Any clinical claim; any Layer-1 workflow authoring.

## Data Model

No model change. `VerificationCase` (models.py:701-721) is reused as-is; the inputs
shape `{family: {"S1": {"value": float, "n_shared": float}}}` matches the existing
contract and the holdout's concordance lines. `RunRecord` is untouched — no signature
break.

# Understanding — eval-concordance-capture (deep dig, 2026-08-12)

Source: `docs/planning/_card/issue.md` (inline brief from the contig-next recommendation),
verified against the worktree code at v0.52.0.

## What the work is really asking

The v0.51.0 C6 fold-in shipped labeled verification capture
(`RunRecord.verification_inputs`, pending-case append, `contig verify-guard`) for
every scoreable family **except the C1 concordance family** — its stated deferral
"PRD R4a: capture deferred, status DERIVATION in scope" is a code comment at
`src/contig/verify_corpus.py:80-82`. This slice closes that deferral: capture
pre-band concordance inputs so concordance cases can ride the same
capture → promote → guarded-re-derive pipeline as the other families.

## What the dig found (file:line)

- **Capture contract:** `verification_inputs: dict[family, dict[sample, dict[metric, float]]]`
  (`src/contig/models.py:363-370`), populated via an out-param `capture_inputs` threaded
  through `_discover_qc(run_dir, assay, *, capture_inputs)` (`src/contig/runner.py:285-296`),
  wired at record creation (`runner.py:1276-1291`). Hardcoded per-family writes; the
  docstring list at `runner.py:296-300` is the de-facto registry. Capture is **not**
  verdict-gated; the pending-case append at `self_heal._finalize` (`self_heal.py:1754-1765`)
  is (WARN/FAIL + succeeded + non-empty inputs, `verify_corpus.py:438-455`).
- **Guard side is DONE:** `verify_corpus.py:83-88` (`_CONCORDANCE_FAMILY_KINDS`:
  `concordance_spearman`, `concordance_genotype`, `concordance_somatic_overlap`,
  `concordance_consequence`), thresholds at `verify_corpus.py:98-103`, status reduction
  at `verify_corpus.py:159-180` consuming `{"value", "n_shared"}` per sample. Holdout
  already carries concordance cases (verify_corpus_holdout.jsonl lines 16-21). **No
  guard-side change needed.**
- **Concordance emission points:** somatic + annotation are auto-wired inside
  `_discover_qc` (`runner.py:428`, `runner.py:378`); germline/RNA-seq/single-cell are
  CLI-verify-only (`cli.py:1641-1911`) — their second call set is user-supplied or
  autorun-generated **at verify time**, never present in the run dir.

## The contradiction (flagging, not papering over)

The brief says "all four shipped slices — germline, RNA-seq, somatic, single-cell —
plus the autorun paths". The code says only **two** of those have a run-dir source at
capture time: `concordance_somatic_overlap` (Mutect2 vs Strelka2 from one sarek run)
and `concordance_consequence` (VEP vs SnpEff from one run). Germline
`--concordance-vcf/-auto`, RNA-seq `--concordance-counts[-auto]`, and single-cell
`--concordance-sc-counts[-auto]` all need a second set that does not exist under the
run dir, so there is nothing to capture into `verification_inputs` at run time
without either mutating the signed record post-verify or inventing run-dir sources.

## Also found (same R4a neighbourhood)

`somatic_plausibility` and `annotation_plausibility` are **scoreable families in the
guard** (`verify_corpus.py:72-73`, holdout lines 12-15) but are **never written** into
`verification_inputs` by `_discover_qc` — their branches (`runner.py:357-378`,
`runner.py:386-464`) lack the `capture_inputs` write the germline branch has
(`runner.py:339-344`, `capture_metrics=` out-param precedent).

## Open questions for the interview

1. Scope of families: run-dir-derived only (somatic + annotation concordance), or also
   the plausibility capture gaps (somatic_plausibility, annotation_plausibility)?
2. Germline / RNA-seq / single-cell concordance: defer with a committed revisit
   trigger (their inputs exist only at verify time — post-record, signature-breaking),
   or is there appetite for a verify-time capture channel? (Recommend: defer, honestly.)
3. Per-pair sample key for captured concordance inputs (holdout uses `"S1"`; real runs
   need a stable label, e.g. `mutect2_vs_strelka2`).
4. Stats exposure: `evaluate_somatic_concordance` and `evaluate_consequence_concordance`
   currently throw away `shared`/`union`/`matches` after stringifying them into the
   message — needs the `capture_metrics=` out-param precedent. Confirm that's in scope.

## Guardrails check

Layer 2 (verify/eval-data capture), inside the founder's edge, no new deps, test-first,
no real nf-core in CI. The fold-in's mutation control (`test_verify_corpus.py:66-94`)
is the anti-tautology instrument; a concordance capture must not move the guarded
number by composition (capture changes write cases, not thresholds).

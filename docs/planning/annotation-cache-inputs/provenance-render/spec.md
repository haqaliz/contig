# Spec — annotation-cache-inputs / provenance-render

## Problem slice and user outcome

The read side of the cache-input follow-on: the run record already carries both
ends of the annotation-cache chain — the inputs in `RunRecord.parameters`
(`vep_cache`/`snpeff_cache` when user-supplied, `download_cache`/`outdir_cache`
when auto-downloaded) and the observed build in `AnnotationProvenance.db_version`
(VCF-header-derived, shipped in C7 M5). This aspect surfaces the input end in the
two human-readable renderers so the chain "which cache was configured → which
build was observed" is readable in `contig methods` and the HTML report. No model
change, no signature break (user decision, 2026-09-12).

## In-scope requirements (PRD M5, N1)

- **M5a — methods line.** `contig methods` (the annotation tool line at
  `methods.py:91-106`) gains a cache-input parenthetical when the record's
  parameters carry cache inputs: user-supplied paths render as
  `cache inputs /v,/s` (or per-tool when only one is present), auto-download
  renders as `cache download (auto)` — and nothing renders when neither exists
  (no orphan label, mirroring the `db_version` omission rule).
- **M5b — HTML provenance panel.** `report.py`'s annotation identity block
  (`report.py:435-453`) gains the same one-line cache-input echo, using the
  exact shared wording.
- **N1 — `contig show`.** A one-line cache-input echo on `contig show` if the
  show renderer reaches the record's parameters cheaply; skip if the seam is
  awkward (documented, not blocked).

## Out-of-scope boundaries

- No new model field on `AnnotationProvenance` or `RunRecord` (parameters are
  the provenance); no signature break; no dashboard change (out of scope for
  this slice — the dashboard reads bundles, follow-on).
- No re-derivation: renderers only read `record.parameters` (never recompute
  what the wiring would have injected).

## Acceptance criteria (testable)

1. A record whose parameters carry `vep_cache`/`snpeff_cache` renders both paths
   in the methods annotation line.
2. A record whose parameters carry `download_cache == "true"` +
   `outdir_cache` renders the auto-download wording (with the outdir path when
   useful, without it when not) in methods and HTML.
3. A record with neither renders exactly as today (byte-identical for a
   parameters-clean record; the existing methods/HTML test pins stay green).
4. `contig show` echoes one line when cache inputs exist, nothing otherwise.
5. Full suite green.

## Dependencies and sequencing

- Depends on the cli-flags aspect only for realistic fixture records (tests can
  construct `RunRecord.parameters` directly — no hard dependency; run the two
  aspects' tasks in either order).
- Single plan, 2-3 TDD tasks (methods → HTML → show).

## Open questions / risks

- None blocking: exact wording is the reviewer's call at implementation time
  (keep "cache/build" labeling discipline — never "database version").
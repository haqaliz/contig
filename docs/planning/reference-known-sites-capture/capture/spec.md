# Spec: reference-known-sites-capture / capture

| | |
|---|---|
| Slug | `reference-known-sites-capture` |
| Aspect | `capture` |
| Source | `docs/planning/reference-known-sites-capture/prd.md` (approved) |

## Problem slice

The whole feature is one cohesive slice (capture-only C5 provenance): add a
`--known-sites` CLI surface for the three germline roles, capture them into
`ReferenceIdentity`, round-trip them through `rerun`/`resume`, render them in the
text + HTML provenance, and pin the disclosed signature break's verify-site behavior.

## In-scope requirements (from the PRD)

- R1 — `--dbsnp` / `--known-indels` / `--known-snps` flags on `contig run`,
  variant-assay-gated (refused on other assays), forwarded into `params`.
- R2 — `KnownSiteIdentity` model + `ReferenceIdentity.known_sites`; capture extended in
  `compute_reference_identity` at `_finalize`; the iGenomes early-return must not swallow
  the known-sites branch.
- R3 — Honest degradation: `sha256 None` on missing/unreadable, absent when no flags,
  iGenomes → role + asset path with `sha256 None`; hash VCF.gz only, skip `.tbi`.
- R3b — Pre-flight existence **warning** (not refusal) per explicit path.
- R4 — `LaunchManifest` round-trip via `rerun` and `resume`.
- R5 — Render in `contig methods` + HTML provenance panel, iGenomes "pipeline-downloaded"
  phrasing, build naming only when the filename/asset map carries it.
- Signature — old signed bundles load + `contig verify` reports `signed: True,
  signature_ok: False`; disclosed in CHANGELOG; verify-path pinned by test.

## Out-of-scope boundaries

- Somatic roles (`pon`, `germline_resource`), VQSR label params (`*_vqsr`).
- Dashboard TS rendering of `reference_identity`.
- GTF-version resolution, assembly-signature pre-flight mismatch (blocker-deferred).
- Generic nf-core `-p key=value` passthrough.
- Verdict/exit-code changes.

## Acceptance criteria (testable)

1. `compute_reference_identity` with explicit known-sites params → three
   `KnownSiteIdentity` entries with real sha256; deterministic.
2. Missing/unreadable known-sites file → `sha256 None`, never a raise, never fabricated;
   run still finalizes.
3. iGenomes mode → role + asset path, `sha256 None`, `source="igenomes"`; the `genome`
   early-return does not drop the branch.
4. No flags → `known_sites` absent; non-variant assay with flags → refused at pre-flight;
   missing explicit path → pre-flight warning, run proceeds, `sha256 None`.
5. `LaunchManifest` round-trip: `rerun`/`resume` re-feed the flags; finalize capture
   byte-identical across a re-run.
6. `contig methods` + HTML render the known-sites rows; build naming only when carried.
7. Signature pin: pre-slice signed bundle loads AND `contig verify` reports
   `signed: True, signature_ok: False`; CHANGELOG disclosure.

## Dependencies & sequencing

- Model (R2) → capture (R2) → CLI + manifest (R1/R3b/R4) → render (R5) → signature
  verify-path pin. Each is test-first; the suite stays green after every phase
  (`uv run pytest`, baseline 2892 passed / 1 skipped).

## Open questions / risks

- BQSR blind spot (accepted): known-sites consumed by BaseRecalibrator are captured only
  when user-supplied via flags.
- No demand-pull yet (push slice, same tier as the C5 capture slice).
- Signature break is disclosed, non-narrow, and accepted per the PRD.
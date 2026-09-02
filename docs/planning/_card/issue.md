# Brief — reproduce-env-alias-map

**Source:** contig-next handoff (2026-09-02). No GitHub issue exists; the work was
never filed. The id lives in the branch/PR (`feat/reproduce-env-alias-map/aliz`).

## One-paragraph brief

Env-resurrection hardening for `contig reproduce`: the slice-2 PRD's deferred
"curated import→package alias map" (`cv2`→`opencv-python`, `sklearn`→`scikit-learn`,
`PIL`→`pillow`, `yaml`→`pyyaml`, etc.) plus a bounded iterative resolution (install →
retry → next missing import, capped with provable termination), so a repo one
PyPI-name-mismatched dep from running actually resurrects instead of degrading to
UNVERIFIED. Keep the existing honest contract (unknown names stay verbatim, install
failure stays UNVERIFIED, never a false reproduce), reuse the `contig_aliases.tsv`
data-file-plus-loud-loader pattern, land the repair chain in the already-shipped
`ReproduceRecord.repair_history`, and keep CI synthetic (scripted installer, no real
pip/network) per every prior C8 slice.

**Caveat:** the slice-2 real-repo smoke gate was never run, so field value is reasoned
not observed; test-first, stdlib-only, no signature break.

## Anchors (where this is named in the docs)

- `docs/planning/reproduce-env-resurrection/prd.md:110-113` — M5: "verbatim install
  target (no alias map this slice)… The curated alias map is an explicit later slice
  (Nice-to-have)."
- `docs/planning/reproduce-env-resurrection/prd.md:143-145` — deferral list:
  "Curated import→package alias map (`cv2`→`opencv-python`, …) — resolves common M5
  mismatches. Iterative multi-module resolution (install one, hit the next missing
  import, repeat, still bounded) — this slice does single install + single retry only."
- `docs/planning/reproduce-env-resurrection/prd.md:215` (R3) — the post-merge smoke on
  a real repo is the go/no-go for slice 3 (alias map / iterative).
- `docs/technical/CAPABILITY_ROADMAP.md` C8 slice 2 (env resurrection) deferral list —
  "import→package alias map, iterative multi-module resolution, version pinning from a
  traced execution, venv isolation."
- CHANGELOG v0.55.x honesty notes — the slice-2 real-repo smoke "has not been run
  yet"; the manual gate carries a never-run checklist.

## Scope edges (from the handoff)

- In scope: curated alias data file + loud loader, alias-aware install target,
  bounded iterative multi-module resolution with provable termination.
- Out of scope: version pinning from a traced execution, venv isolation, non-Python
  environments (R/conda/apt), figure claims, PDF-table extraction.
- Honest contract preserved: unknown import names install verbatim; a failed install /
  exhausted budget stays UNVERIFIED (never a false reproduce).
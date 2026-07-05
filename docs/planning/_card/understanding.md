# Understanding: contig-alias-harmonization

Written after mapping the v0.9.0 harmonizer seam (Phase 2 dig). Every claim carries a `file:line`.

## What the work is really asking

When a user supplies a **UCSC-style FASTA** (`chr1…chr22, chrX, chrY, chrM`) and an
**Ensembl-style GTF** (`1…22, X, Y, MT`), today's chr-prefix harmonizer
(`reference_harmonize.py:39-79`) harmonizes the **autosomes** correctly but produces the
**wrong mitochondrial name** and lets the run proceed with the mito contig silently
mismatched. The feature closes that silent gap by resolving the mitochondrial alias
(`M`↔`MT`) as part of harmonization, while preserving the refuse-on-wrong-assembly
invariant.

## Why today's harmonizer mishandles the canonical case (the concrete bug)

Trace `plan_harmonization({chr1,chr2,chrM}, {1,2,MT})`:
- `_all_chr_prefixed(fa)=True`, `_all_chr_prefixed(gt)=False` → `direction="add_chr"`
  (`reference_harmonize.py:59-61`).
- `transformed = {f"chr{n}" for n in gt}` = `{chr1, chr2, chrMT}` (`:61`). **`chrMT ≠ chrM`.**
- Intersection guard `transformed & fa` = `{chr1, chr2}` — non-empty → **passes** (`:71`).
- `harmonize_gtf` rewrites GTF col1 with `_apply` (pure `chr`-add, `:86-91`) → GTF mito
  becomes `chrMT`.
- Post-condition re-check `check_reference_consistency(fasta, harmonized_gtf)` is
  **disjoint-only** (`reference_check.py:51-53`): `{chr1,chr2,chrM}` shares `{chr1,chr2}`
  with `{chr1,chr2,chrMT}` → **not disjoint → returns `[]` → run proceeds** (`cli.py:470-481`).

Result: mito gene annotations sit on `chrMT` while the FASTA/BAM contig is `chrM` →
mito-region quantification silently yields nothing. This is the "residual case" the brief
names as the real target.

## Affected areas (the seam)

| Concern | Location |
|---|---|
| Prefix direction predicate to widen | `reference_harmonize.py:59-67` |
| The per-name transform (`_apply`, pure chr add/strip) | `reference_harmonize.py:86-91` |
| Post-transform intersection guard (refuse invariant) | `reference_harmonize.py:71` |
| `HarmonizationDirection` literal (persisted as free-form `str`) | `reference_harmonize.py:29`; models `models.py:203,283` |
| GTF col1 stream-rewriter | `harmonize_gtf` `reference_harmonize.py:110-161` |
| Detector disjoint-only rule (pre-flight refuse) | `reference_check.py:48-64` |
| Launch chokepoint (invoke, scratch path, post-check, thread to finalize) | `cli.py:453-509, 530-551, 571` |
| WARN `reference_harmonized` breadcrumb | `self_heal.py:1005-1019` |
| Reproduce re-derivation (rerun/resume re-enter dispatch with original GTF) | `cli.py:619-640, 1269-1289` |
| Existing tests to extend | `tests/test_reference_harmonize.py`, `tests/test_reference_check.py`, `tests/test_cli.py:582-745`, `tests/test_self_heal.py:363-420` |

## Design decisions / ambiguities (for the PRD interview)

1. **Alias-table scope.** Recommend slice 1 = **the mitochondrial alias `M`↔`MT` only**
   (the canonical, unambiguous pair named in every deferral note). The wider
   UCSC↔Ensembl↔GenBank **scaffold/accession** tables (`GL…`, `KI…`) are
   assembly-specific and ambiguous — no reliable universal source — a real "no source"
   risk like the deferred GTF-version resolution (v0.7.0 deferrals).
   **Defer scaffolds explicitly.** Structure the alias map so extending it later is trivial.

2. **Directional canonicalization rule.** The mito spelling correlates with the naming
   convention: `add_chr` ⇒ FASTA is UCSC-style ⇒ mito is `chrM`; `strip_chr` ⇒ FASTA is
   Ensembl-style ⇒ mito is `MT`. So the transform is: apply the prefix op, then
   canonicalize a bare `{M,MT}` token to `M` (for `add_chr`) or `MT` (for `strip_chr`).
   Then `_apply("MT","add_chr") = "chrM"` and `_apply("chrM","strip_chr") = "MT"`. Verify
   in tests against the canonical UCSC↔Ensembl pairing.

3. **How the plan represents the transform.** Two options — (A) keep `direction` as the
   prefix decision and always apply mito canonicalization as a composed step (smallest
   blast radius; signature stable); (B) generalize the plan to a concrete per-contig
   rename map (cleaner, generalizes to future aliases, but changes `direction` semantics
   and the breadcrumb). Lean (A) for the slice; note (B) as the future shape. Either way
   `direction`/`harmonized_direction` are free-form `str` (`models.py:203,283`) → **no
   schema migration**. The breadcrumb message must make the alias visible.

## ⚠️ Two contradictions between the brief and the shipped v0.9.0 precedent (must resolve)

1. **"Seed a golden corpus case" (brief) vs. v0.9.0 precedent.** The contig-naming
   mismatch is a **pre-flight gate, not a runtime `FailureClass`** — the detector corpus
   (`detector_corpus.jsonl`, `FailureCase` `models.py:358-366`) has **no** reference-
   mismatch class, and v0.9.0 shipped the prefix harmonizer **provenance-only** ("eval
   capture is provenance-only in this slice", CHANGELOG v0.9.0; v0.7.0 explicitly deferred
   "seeding a `reference_mismatch` corpus class"). **Recommendation:** match the v0.9.0
   precedent — **no new detector-corpus case**; eval capture is the provenance breadcrumb.
   Introducing a `reference_mismatch` FailureClass is out of scope (still deferred).

2. **"Record in launch manifest + `ReferenceIdentity`" (brief).** Already done by the
   v0.9.0 plumbing (`cli.py:546,571`; `self_heal.py:1005-1019`) — this slice **reuses** it
   unchanged (`harmonized_reference: bool`, `harmonized_direction: str`), it does not add
   new persistence. The only change is the *direction label* value + breadcrumb wording so
   the alias is visible. No new fields.

## Guardrail check (CLAUDE.md)

Pure **Layer 2** self-heal/verify hardening. No Layer-1 authoring, no wet-lab/clinical,
no raw-read egress (operates on reference contig-name strings on the user's compute),
no correctness over-claiming (a WARN breadcrumb, run still proceeds). Test-first with
synthetic FASTA/GTF fixtures — no real nf-core run. ✅

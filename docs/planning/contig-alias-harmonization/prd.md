# PRD: Per-Contig Alias Harmonization

**Slug:** `contig-alias-harmonization`
**Capability:** C2 — self-heal breadth (reference/build-mismatch repair), follow-on of v0.9.0
**Branch:** `feat/contig-alias-harmonization/aliz`
**Status:** Draft for review gate

---

## Problem Statement

Contig's reference pre-flight (v0.7.0 detector + v0.9.0 harmonizer) resolves the classic
`chr`-prefix mismatch between a FASTA and a GTF (`chr1` vs `1`) by rewriting the GTF into
a run-scoped scratch copy and proceeding. But the prefix rule is **purely lexical** — it
add/strips `chr` and nothing else (`reference_harmonize.py:86-91`). The canonical
real-world reference pairing, a **UCSC FASTA** (`chr1…chr22, chrX, chrY, chrM`) plus an
**Ensembl GTF** (`1…22, X, Y, MT`), breaks it: prefix-add turns the GTF's `MT` into
`chrMT`, which does **not** match the FASTA's `chrM`. The autosomes now intersect, so the
disjoint-only post-check passes (`reference_check.py:51-53`) and **the run proceeds with
the mitochondrial contig silently mismatched** — mito-region features quantify to nothing,
and no verdict surface flags it.

A related shape slips through the same way: a **pure-alias** mismatch with no prefix
difference at all (both bare `MT` vs `M`, or both prefixed `chrMT` vs `chrM`) hits the
harmonizer's "not an unambiguous asymmetry" else-branch (`reference_harmonize.py:65-67`),
returns `None`, and — because the autosomes still share names — is never refused either.

**Who has this problem.** Persona A (lone computational biologist) and Persona B (wet-lab
scientist who can't code) routinely mix a UCSC genome with an Ensembl annotation (or vice
versa) — the single most common reference-wrangling foot-gun in RNA-seq and variant work.
The cost of the status quo is a **silent partial-wrong result** that passes QC: exactly the
"a run succeeds against the wrong reference" silent-failure class the moat exists to kill
(`CAPABILITY_ROADMAP.md` C5/C2 rationale).

**Evidence it's real.** Every prior deferral note names this exact gap:
`chrM`↔`MT` in CHANGELOG v0.9.0 ("Deferred: per-contig name mapping for ambiguous cases
(e.g., `chrM`↔`MT`)"), the C2 deferred list in `CAPABILITY_ROADMAP.md`, and
`docs/planning/self-heal-reference-mismatch/understanding.md` (which flags `MT`/`chrM` and
`GL…`/`KI…` scaffolds as the open predicate edge cases).

---

## Goals & Success Metrics

**Goal:** Auto-harmonize a UCSC↔Ensembl contig-naming mismatch — including the
mitochondrial alias and scaffold aliases where a table entry exists — at pre-flight, so
the run proceeds against a consistently-named reference, while a genuine wrong-assembly is
still refused.

**Success metrics (all test-verified, no real nf-core run):**
1. A UCSC-FASTA + Ensembl-GTF pair (`chrM` / `MT`) harmonizes so the **mito contig
   matches** in the scratch GTF (`chrM`), and the run proceeds. *(Today: produces `chrMT`,
   silently mismatched.)*
2. A **pure-alias** mismatch (no prefix asymmetry: `chrMT`↔`chrM`, or `MT`↔`M`) is detected
   and harmonized, not silently passed through.
3. A **genuine wrong-assembly** pair (disjoint even after prefix + alias resolution — e.g.
   the existing `scaffold_1` vs `chr_scaffold_1` fixture) is still **refused** with
   `typer.Exit(1)` (unless `--allow-reference-mismatch`).
4. The decision is visible: the WARN `reference_harmonized` breadcrumb, the manifest
   `harmonized_reference` flag, and `ReferenceIdentity.harmonized*` all record that an
   alias harmonization occurred, and its human-readable direction/label makes the alias
   explicit.
5. `rerun`/`resume` reproduce the decision by re-deriving from the **original** GTF (no
   scratch path baked into the manifest) — unchanged from v0.9.0.

**Non-metric (honesty) success:** no new false-refusals — any FASTA/GTF that passes today
still passes.

---

## User Personas & Scenarios

- **A — lone computational biologist:** downloads a UCSC hg38 FASTA and an Ensembl GTF for
  an RNA-seq run. Today the mito genes silently drop out; with this feature the run
  harmonizes and a WARN breadcrumb tells them the reference was reconciled.
- **B — wet-lab scientist who can't code:** cannot diagnose a contig-naming mismatch at
  all. Auto-harmonization + a plain-language WARN ("the annotation was harmonized to match
  the genome; confirm the reference was correct") is the only way they get a correct run.

---

## Requirements

### Must-have

- **M1 — General per-contig rename map.** Replace the two-value prefix-only transform with
  a `plan_harmonization` that computes a concrete **GTF-contig → FASTA-convention** rename
  map, composing (a) the existing `chr` add/strip prefix rule and (b) a curated alias
  table. `harmonize_gtf` applies that map to GTF column 1. The FASTA is never rewritten
  (it is ground truth — the reads align to it). *(This is option B from the dig: cleaner,
  and required to support pure-alias + a real alias table.)*
- **M2 — Universal mitochondrial alias.** The alias table must resolve `M`↔`MT` in both
  directions, keyed to the target convention: producing a UCSC-style name yields `chrM`,
  producing an Ensembl-style name yields `MT`. This is the one universally-unambiguous
  alias and the core of the slice.
- **M3 — Residual-mismatch trigger (decoupled from the disjoint-only detector).**
  `plan_harmonization` must trigger when the only difference is an alias, **even when the
  autosomes already match** (e.g. `chr1,chr2,chrM` FASTA vs `chr1,chr2,MT` GTF). The
  current gate early-returns `None` when `check_reference_consistency` (disjoint-**only**)
  finds no problem (`reference_harmonize.py:51`), so it never sees this residual case.
  **Resolution (review gate):** `plan_harmonization` no longer gates on the disjoint-only
  detector; it computes the rename map and triggers whenever the map would change ≥1 GTF
  contig **and** doing so strictly increases FASTA∩GTF overlap (a real, resolvable
  mismatch), while still returning `None` when no aliasable/prefix improvement exists.
  Covers both the fully-disjoint prefix case and the autosomes-already-match residual case.
- **M4 — Refuse-on-wrong-assembly invariant preserved.** After building and applying the
  rename map, if the transformed GTF set and the FASTA set are still **disjoint**, return
  `None` → the CLI refuses (`cli.py:493-509`). The alias table is a **closed curated set**,
  so it can only reconcile a real convention difference; it can never rescue a wrong
  assembly (those contigs are not in the table). The existing `scaffold` genuinely-disjoint
  fixture must still refuse.
- **M5 — Provenance-only eval capture (resolves the brief↔precedent conflict).** No new
  detector-corpus case and **no new `reference_mismatch` FailureClass** — matching the
  v0.9.0 precedent ("eval capture is provenance-only in this slice"). Eval capture is the
  existing WARN `reference_harmonized` breadcrumb + manifest + `ReferenceIdentity`,
  reused unchanged. The breadcrumb message/direction label is updated so an alias
  harmonization is distinguishable from a pure-prefix one.
- **M6 — Reuse existing persistence.** No schema migration. `harmonized_direction` /
  `RunRecord.harmonized_reference_direction` stay free-form `str` (`models.py:203,283`);
  `LaunchManifest.harmonized_reference` stays `bool` (`models.py:338`). The direction
  string's *vocabulary* widens (e.g. it may name the aliases applied) but the fields do not
  change.
- **M7 — Test-first, deterministic, no network.** Every behavior lands with a failing test
  first, over synthetic FASTA/GTF fixtures in `tmp_path`, mirroring
  `tests/test_reference_harmonize.py` and `tests/test_cli.py:582-745`. No real
  nf-core/STAR run in CI.
- **M8 — Partial-harmonization honesty (review-gate resolution of the hard question).**
  When harmonization proceeds but ≥1 GTF contig remains **unmatched** to the FASTA after
  the rename map is applied (a contig we had no prefix rule or alias for), the WARN
  `reference_harmonized` breadcrumb must **enumerate those still-unmatched GTF contigs**.
  This turns partial harmonization from a silent gap into a visible one — the honest
  guarantee is "references match on prefix + tabled contigs," not "references match," and
  the breadcrumb must say so. Uncovers the moved-silent-failure risk instead of hiding it.
- **M9 — Mito resolution by FASTA lookup, not blind convention (R4 resolution).** Resolve a
  GTF mito token (`M`/`MT`, with or without `chr`) to whichever spelling **actually exists
  in the FASTA contig set** (prefer a direct FASTA hit over a convention assumption), so a
  hybrid FASTA (`chrMT`) is handled rather than defeated. Fall back to the convention rule
  only when the FASTA has no recognizable mito contig.

### Should-have

- **S1 — Curated UCSC↔Ensembl scaffold alias table (review-gate: seeded + extensible).**
  Beyond mito, bundle a curated, **extensible data table** of UCSC↔Ensembl contig aliases
  (sourced from UCSC `chromAlias`) for Contig's primary supported assembly (GRCh38), so
  common unplaced/unlocalized scaffolds (`GL000…`↔`chrUn_GL000…v1`,
  `KI270…`↔`chr…_KI270…v1`) also harmonize. Shipped as a static asset under
  `src/contig/data/`, structured so adding an assembly is a data edit, not a code change.
  The **mechanism** (M1–M4) is what the test suite proves; table completeness is **not** a
  test gate (per the review-gate reconciliation of the "full map" choice: ship the
  mechanism now with mito universal + a GRCh38 scaffold seed, and grow the table over
  time). M8 guarantees any contig the table misses is surfaced, not silently dropped.

### Nice-to-have

- **N1 — Multi-assembly tables.** Bundle chromAlias tables for GRCh37, GRCm38/39, etc.
- **N2 — Direction label in the human report** naming exactly which contigs were aliased.

### Out of scope

- Introducing a `reference_mismatch` runtime `FailureClass` / detector-corpus case (M5;
  still deferred, as in v0.7.0).
- Auto-**fetching** UCSC `chromAlias` over the network (bundled static data only; no
  raw-read or network egress).
- Rewriting the **FASTA** to match the GTF (FASTA is ground truth).
- The sample-data-vs-reference **assembly-signature** comparison (no sample-side contig
  signal at pre-flight — a real blocker, deferred since v0.7.0/v0.9.0).
- Exhaustive, guaranteed-complete per-assembly alias coverage (a data-maintenance
  commitment, explicitly not gated on this slice; see Risks).
- BED / known-sites / GTF-version consistency.

---

## Technical Considerations

**Architecture fit.** Pure pre-flight, at the single launch chokepoint `_dispatch_run`
(`cli.py:453-509`), so it protects both the CLI and the dashboard (which spawns the CLI).
The two-module seam is reused: `reference_check.py` (detect) + `reference_harmonize.py`
(plan + rewrite). The change is concentrated in `plan_harmonization` (compute a rename map,
widen the trigger) and `harmonize_gtf`/`_apply` (apply a map, not just a prefix op).

**Rename-map shape.** `plan_harmonization(fasta, gtf)` → a plan carrying a concrete
`{gtf_name: target_name}` map (or `None` to refuse). Build it by: derive the FASTA
convention (all-`chr` vs all-bare, reusing `_all_chr_prefixed`), then for each GTF contig
compute its target via prefix op + alias lookup; keep the post-transform **intersection**
guard as the refuse gate. `harmonize_gtf` applies the map to column 1 with the existing
byte-fidelity streaming (line-ending, comment, blank, and tab-split handling at
`reference_harmonize.py:128-159`) untouched.

**Reproducibility / verification impact.** Reproduce is preserved: the manifest stores the
**original** GTF (`cli.py:541`) and `rerun`/`resume` re-derive harmonization by re-entering
`_dispatch_run` (`cli.py:619-640,1269-1289`). The verdict surface is unchanged in
mechanism — a WARN `reference_harmonized` breadcrumb caps the verdict at WARN
(`self_heal.py:1005-1019`, `models.py:90-91`). No raw-read egress: operates only on contig
**names** parsed from FASTA headers / GTF column 1, on the user's compute.

**Guardrail check (CLAUDE.md).** Layer 2 self-heal hardening; raises unattended-completion
(Phase-1 headline metric) and kills a silent-failure class. No Layer-1 authoring, no
wet-lab/clinical credentials, no proprietary data. ✅

---

## Data Model / Contracts

- **No new persisted fields.** `ReferenceIdentity.harmonized: bool`,
  `.harmonized_direction: str|None` (`models.py:202-203`),
  `RunRecord.harmonized_reference_direction: str|None` (`models.py:283`),
  `LaunchManifest.harmonized_reference: bool` (`models.py:338`) all reused as-is.
- **New static asset (S1):** a bundled alias table under `src/contig/data/` (format TBD in
  tech-plan — likely a small TSV/JSON keyed by assembly and convention). Mito M↔MT may be a
  code constant (universal) with the file reserved for scaffold aliases.
- **Widened `HarmonizationDirection` vocabulary** (`reference_harmonize.py:29`): the plan's
  human-readable direction/label may now encode alias application; the persisted type stays
  free-form `str`.

---

## Risks & Open Questions

| # | Risk / question | Mitigation |
|---|---|---|
| R1 | **"Full map" is a data-maintenance commitment, not code.** Exhaustive per-assembly UCSC↔Ensembl completeness has no single universal source and drifts per assembly. | Ship the **mechanism** as the tested deliverable (M1–M4); the alias **table** is curated, extensible data (S1) seeded with mito (universal) + GRCh38 scaffolds. Table completeness is explicitly **not** a test gate. Flagged to the user at interview; user accepted. |
| R2 | A wrong alias entry could **falsely reconcile** a real wrong-assembly. | Closed curated set only; the post-transform disjoint guard (M4) still refuses; every table entry is a documented UCSC `chromAlias` pair; tests assert the `scaffold` wrong-assembly fixture still refuses. |
| R3 | Widening the trigger (M3) could introduce **false-refusals** or over-harmonization on inputs that pass today. | Regression test: every existing `test_reference_harmonize`/`test_reference_check`/`test_cli` case must stay green; add an explicit "passes today, still passes" assertion set. |
| R4 | Mito canonicalization keyed off prefix direction assumes `chr`⇒UCSC⇒`M` and bare⇒Ensembl⇒`MT`. A hybrid FASTA (`chrMT`) breaks the assumption. | Resolve mito by **alias lookup against the actual FASTA contig set**, not a blind convention assumption where possible; document the residual hybrid case; the disjoint guard still prevents a false pass on the autosomes-only case. Settle exact rule in tech-plan. |
| R5 | Alias-table **format/location** and whether mito is code-constant vs data. | Open for tech-plan; lean mito = universal code constant, scaffolds = data file. |

---

## Acceptance (test-first, roadmap-style)

1. **RED→GREEN:** `plan_harmonization` on a UCSC/Ensembl pair returns a rename map that
   sends GTF `MT`→`chrM` (and the autosomes via prefix); `harmonize_gtf` yields a scratch
   GTF whose contig set shares the mito contig with the FASTA.
2. Pure-alias pair (`chrMT`↔`chrM`, and `MT`↔`M`) harmonizes rather than returning `None`.
3. Genuine wrong-assembly (post-alias disjoint) returns `None`; CLI refuses with exit 1;
   `--allow-reference-mismatch` proceeds and persists the flag.
4. `_finalize` records the alias harmonization in `ReferenceIdentity` + a WARN
   `reference_harmonized` breadcrumb with an alias-aware message; verdict capped at WARN.
5. `rerun`/`resume` re-derive the harmonization from the original GTF.
6. Full existing suite stays green (no false-refusal regressions).

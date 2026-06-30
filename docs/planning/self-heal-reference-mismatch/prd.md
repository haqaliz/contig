# PRD — Reference contig-naming self-heal (harmonize-and-proceed)

- **Slug:** `self-heal-reference-mismatch`
- **Type:** feat · **Owner:** aliz · **Branch:** `feat/self-heal-reference-mismatch/aliz`
- **Capability:** C2 (self-heal breadth) — the reference/build-mismatch *repair* that
  v0.7.0's contig-naming *detector* and v0.6.0's reference-identity *capture* enabled.
- **Source:** inline brief (`docs/planning/_card/issue.md`) + deep-dig
  (`docs/planning/self-heal-reference-mismatch/understanding.md`).

## Problem Statement

A `contig run` whose reference FASTA and annotation GTF use **disjoint contig naming**
(`chr1, chr2, …` in one, `1, 2, …` in the other) otherwise runs to "success" while
silently producing an empty count matrix — the notorious `chr`-prefix silent failure.
v0.7.0 closed the silent-failure hole by **refusing** such a run at pre-flight with a
clear message and a `--allow-reference-mismatch` escape hatch.

But refusal still leaves the **user** to fix it: manually rewrite a GTF's seqnames and
re-launch. For the wet-lab / non-coder ICP that is exactly the kind of toil Contig
exists to remove, and for the lone bioinformatician it is an avoidable interruption.
The fix for the common case is **mechanical and deterministic** — add or strip a `chr`
prefix — so the agent can do it autonomously and keep going.

**Evidence it's real:** the `chr`-vs-`1` mismatch is a well-known recurring failure
class (the reason v0.7.0's detector exists); the detector already names the `chr`-prefix
asymmetry direction in its refusal message (`reference_check.py:55-64`).

## Goals & Success Metrics

- **G1 — Autonomy:** a run blocked *only* by a `chr`-prefix-asymmetric contig-naming
  mismatch completes unattended (raises the unattended-completion rate; ROADMAP Phase-1
  headline metric) instead of exiting 1.
- **G2 — Safety (the hard bar):** the harmonizer **never** fires when it is not certain
  the rewrite makes the contig sets agree. A genuine wrong-assembly mismatch keeps
  refusing exactly as today. Target: zero false harmonizations across the test matrix.
- **G3 — Reproducibility:** a harmonized run reproduces via `rerun`/`resume` with the
  same harmonized intent, and `run_record.json` records that a harmonization occurred
  (which side, the transform applied).
- **Measure:** test-suite assertions (a chr-asymmetric pair auto-harmonizes and the run
  proceeds; a wrong-assembly pair still refuses; rerun/resume reproduce). No real
  nf-core run; deterministic synthetic fixtures only.

## User Personas & Scenarios

- **B — wet-lab scientist who can't code:** downloads a GENCODE GTF (`chr`-prefixed) and
  an Ensembl FASTA (no prefix); today gets refused and is stuck. With this: the run
  self-heals and completes, with a plain-language note that names were harmonized.
- **A — lone computational biologist:** knows the fix but values not having to stop,
  `sed` the GTF, and re-launch; gets an autonomous recovery plus a provenance record
  they can cite.

## Requirements

### Must-have

- **M1 — Pure harmonizer module.** A deterministic, side-effect-free decision function
  that, given the FASTA and GTF contig sets, decides whether a **safe** harmonization
  exists and, if so, which uniform transform to apply to the **GTF**:
  - Fires only when (a) the detector already reports a disjoint mismatch, **and**
    (b) exactly one side is all-`chr`-prefixed and the other is not (the asymmetry), **and**
    (c) applying the uniform `chr` add/strip to the GTF makes its contig set **intersect**
    the FASTA's. If (c) fails (true wrong-assembly), **no safe harmonization** → refuse.
  - Transform is **uniform and mechanical**: add `chr` to every GTF seqname (when FASTA
    is chr-prefixed and GTF is not), or strip a leading `chr` from every GTF seqname
    (the reverse). **No per-contig name mapping** (e.g. no `chrM`→`MT` guess — that is
    fabrication and is out of scope; such residual contigs simply stay unmatched, which
    is acceptable because the rule only requires post-transform *intersection*, the
    detector's own bar).
- **M2 — GTF rewrite to scratch.** Stream-rewrite the GTF's column-1 seqnames applying
  the transform, gzip-transparent (preserve gz-ness), to a **run scratch path** under
  the run dir. **Never mutate the user's original file in place.** Non-seqname lines
  (comments, columns 2+) pass through byte-faithful.
- **M3 — Gate integration (auto-proceed).** At the pre-flight gate (`cli.py:392-408`),
  when a mismatch is detected and the harmonizer says a safe transform exists: write the
  harmonized GTF, repoint `params["gtf"]`, print a plain-language note of what was done,
  and **proceed** (no `Exit(1)`). When no safe transform exists: refuse exactly as today
  (honoring `--allow-reference-mismatch` to override, unchanged).
- **M4 — Reproducible provenance.** Persist the harmonization decision so the run
  reproduces:
  - `LaunchManifest` (`models.py:298`) gains a defaulted field (e.g.
    `harmonized_reference: bool = False`, plus enough to reconstruct intent), set at
    `cli.py:422`, threaded through `rerun` (`cli.py:508/527`) and `resume`
    (`cli.py:1097/1116`) exactly as `allow_reference_mismatch` is.
  - `ReferenceIdentity` (`models.py:186`) records that the run consumed a **harmonized**
    GTF (a `harmonized: bool` and the direction/source), landing in `run_record.json` at
    finalize. The harmonized GTF's `sha256` (not the original's) is what gets hashed,
    since that is what the pipeline actually ran against.
- **M5 — Honesty.** Never claim correctness beyond "names harmonized." The note and
  provenance describe the mechanical transform.
- **M6 — Verdict breadcrumb (review-gate decision).** A harmonized run must surface the
  rewrite on the **verdict surface**, not only in buried provenance — at minimum a
  WARN-level breadcrumb ("reference GTF seqnames were harmonized: GTF `chr`-prefix
  added to match FASTA"). A correctness-adjacent autonomous edit must be visible at the
  moment trust matters. (Reconcile with the existing verdict reduction; this is a
  breadcrumb, not a new FAIL band.)
- **M7 — Closed-loop acceptance (Gap 3).** An acceptance test must feed the **harmonized**
  GTF back through `check_reference_consistency(fasta, harmonized_gtf)` and assert it now
  returns `[]` — proving the transform *resolved* the mismatch rather than moving it.
- **M8 — GTF line contract (Gap 2).** Rewrite **column 1 only**, tokenizing exactly as
  `gtf_contigs` does (`split("\t", 1)`, `reference_check.py:32`); columns 2-9, comment
  (`#`)/`track`/`browser` lines, trailing whitespace, and CRLF/LF pass through
  **byte-faithful**; gzip in → gzip out. A fixture asserts columns 2+ are byte-identical.

### Should-have

- **S1 — Plain-language note** on the harmonization (which side was rewritten, the
  prefix change, and where the harmonized copy lives), mirroring the existing gate's
  `typer.echo(..., err=True)` style.
- **S2 — Rerun/resume parity test** proving a harmonized run reproduces the harmonized
  intent (not a re-detection that could diverge).

### Nice-to-have

- **N1 — Dashboard surfacing** of the harmonization on the provenance panel (the
  dashboard spawns the CLI, so it inherits the behavior; an explicit badge is optional).

## Technical Considerations

- **Hook point (decided):** pre-flight gate, not the runtime self-heal loop. The
  mismatch is a *structural pre-flight* condition; the runtime loop + `detector_corpus`
  key on failed-task log signatures and do not apply. The harmonizer is a pure module
  with the gate as its only side-effecting caller.
- **Direction (decided):** rewrite the **GTF** (annotation, small) — never the FASTA
  (alignment ground truth, large).
- **Default (decided):** **auto-harmonize and proceed**; a harmonized run is strictly
  safer than the already-existing `--allow-reference-mismatch` override.
- **Structured asymmetry signal:** `reference_check.py` currently encodes the asymmetry
  direction only in a message string. The harmonizer needs the raw sets +
  `_all_chr_prefixed` (both already in the module) to decide direction; expose a small
  structured helper rather than parse the message.
- **Reproducibility/verification impact:** additive to `LaunchManifest` and
  `ReferenceIdentity` (both have the `allow_reference_mismatch` defaulted-field
  precedent for legacy-manifest safety). No verdict/exit-code change. The harmonized GTF
  is the reproducible artifact; its hash is recorded.
- **Guardrails (CLAUDE.md):** Layer 2 (repair reference inputs to a *consumed* pipeline,
  not authoring one) ✓; no raw-read egress (local rewrite) ✓; no over-claiming (uniform
  mechanical transform, refuse when unsure) ✓; test-first, synthetic fixtures ✓.

## Artifact / Run Contracts

- New harmonized GTF written under the run dir scratch (path recorded in manifest).
- `LaunchManifest.harmonized_reference` (+ reconstruct fields) — defaulted, legacy-safe.
- `ReferenceIdentity.harmonized` (+ direction/source) in `run_record.json`.

## Risks & Open Questions

- **R1 — Over-eager harmonization (the central risk).** A transform that fires on a true
  wrong-assembly would *manufacture* the silent failure v0.7.0 prevents. Mitigation: the
  M1 post-transform-intersection gate; refuse when intersection is empty; extensive
  test matrix incl. wrong-assembly and partial-overlap (subset) cases.
- **R2 — Edge contigs (chrM/MT, scaffolds `GL…`/`KI…`).** Resolved by design: the
  transform is uniform `chr` add/strip only; non-prefix naming differences (chrM vs MT)
  are *not* mapped and simply remain unmatched, accepted as long as post-transform sets
  intersect. No per-contig guessing.
- **R3 — gz fidelity / large GTF.** Streamed rewrite, gzip-transparent; only column 1 is
  touched. Test on both plain and `.gz` fixtures.
- **OQ1 — RESOLVED (review gate): reproduce the *decision*, not the artifact.**
  `rerun`/`resume` re-enter the same `_dispatch_run`, which re-runs the detector on the
  (unchanged) input paths and re-derives the transform deterministically — matching the
  `--allow-reference-mismatch` precedent. Store the decision bool (+ direction) in the
  manifest for the record and to keep the re-derivation honest if inputs changed; do
  **not** pin/re-verify the harmonized GTF hash as a reproduce gate (a moved scratch dir
  must not break reproduce). Contract: "a harmonized run reproduces the harmonization
  decision," not "byte-identical harmonized artifact."

## Out of Scope (do not drift)

- **Sample-data-vs-reference assembly-signature** comparison/repair — blocked (no
  sample-side contig signal in raw FASTQ / the finished bundle;
  `reference-mismatch-detector/prd.md:130-132`).
- Fabricating, guessing, downloading, or **per-contig mapping** a reference for a true
  wrong-assembly mismatch — no safe repair; refuse.
- A runtime `reference_mismatch` `FailureClass` + `detector_corpus.jsonl` case (the
  downstream empty-count-matrix safety net) — deferred; eval capture is provenance-only
  this slice (per the interview decision).
- Known-sites/BED-vs-reference consistency; GTF annotation-version resolution.
- Rewriting the FASTA; STAR/BWA directory indexes; peak-RSS scaling.

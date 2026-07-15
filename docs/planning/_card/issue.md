# Card: rnaseq-plausibility-ingestion

- **Type:** feat
- **Id / slug:** rnaseq-plausibility-ingestion
- **Branch:** feat/rnaseq-plausibility-ingestion/aliz
- **Owner:** aliz
- **Source:** inline brief (from `contig-next` handoff — no GitHub issue; id is a slug)

## Brief

Wake the dormant `RNASEQ_PLAUSIBILITY_PACK`, which is a **silent no-op on every real
rnaseq run**: its `percent_duplication` / `percent_rRNA` slugs (`rule_pack.py:295-315`,
both already commented `# slug unverified`) are absent from MultiQC general-stats, so
`evaluate_rnaseq_plausibility` emits UNVERIFIED for both checks forever.

Fix it the way the C3 **single-cell ingestion slice** fixed the identical defect: a
dedicated metric parser reading the tool's own artifact, behind an additive
`_discover_qc` gate that keeps rnaseq on its existing MultiQC pack path (rnaseq stays
out of `_DEDICATED_METRIC_ASSAYS`). `verification/rnaseq_metrics.py` (RSeQC
`read_distribution.txt`, shipped in the mapping-composition slice) is the closest
precedent — same assay, same additive-gate shape.

**Critical caveat to resolve in the dig before writing the parser:** `duplication_rate`
has a certain artifact (Picard `*.MarkDuplicates.metrics.txt`) but its native
`PERCENT_DUPLICATION` is a **0–1 fraction** against the pack's **0–100** band, with a bare
`float()` in `qc_ingest.py` and no normalization — fix the unit or the check ships
still-dead (a 0.85 duplication reads as 0.85 against `warn_above: 80.0` and never fires).
`percent_rRNA` has **no confirmed default artifact** (featureCounts biotype QC depends on a
biotype attribute in the user's GTF; SortMeRNA is non-default behind `--remove_ribo_rna`),
so be prepared to ship duplication live and degrade rRNA to an honest UNVERIFIED against a
**named** artifact — or drop it rather than guess a slug a second time.

Both checks stay **WARN-capped**. Test-first per repo discipline; no real nf-core/Picard
run in CI.

## Grounding (the named-deferral trail)

- `docs/technical/CAPABILITY_ROADMAP.md` (C3, somatic empty-call-set FAIL floor slice) —
  the nomination, verbatim: *"**Surfaced, not fixed (a stronger `/contig-next` candidate
  than any FAIL band):** `RNASEQ_PLAUSIBILITY_PACK` is a **silent no-op on every real
  rnaseq run** — the same defect class as the single-cell dormant pack fixed below — and
  carries a live unit ambiguity (the pack declares 0–100 while Picard's native
  `PERCENT_DUPLICATION` is a 0–1 fraction and `qc_ingest.py:5-23` does a bare `float()`
  with no normalization)."*
- `docs/technical/CAPABILITY_ROADMAP.md` (C3, single-cell ingestion slice) — the shipped
  precedent for this exact defect class: a pack that *"**silently no-oped** — its metrics
  were read only from MultiQC general-stats, where the base pipeline does not put
  [the] cell-level QC"*, fixed by `verification/scrnaseq_metrics.py` parsing the aligner's
  own artifact behind a dedicated gate, *"so the single-cell verdict fires for the first
  time."* That slice also removed a **dead check** (`pct_reads_mito`) rather than keep it —
  a precedent for dropping `rrna_contamination` if no artifact backs it.
- `docs/technical/CAPABILITY_ROADMAP.md` (C3, RNA-seq mapping-composition slice) — the
  same-assay additive-gate precedent: composition fractions *"are **not** in Contig's
  MultiQC general-stats ingest (verified against a real `multiqc_data.json`)"*, so a
  dedicated parser reads RSeQC's own artifact while *"`rnaseq` stays out of
  `_DEDICATED_METRIC_ASSAYS`"* and the published `results/` copy is preferred over `work/`.

## The FAIL-severity question is CLOSED — do not reopen it

`CAPABILITY_ROADMAP.md` (C3) records RNA-seq FAIL severity as **declined by design, not
deferred**, for two independent reasons:

1. *Biology:* every RNA-seq metric has a legitimate protocol occupying its extreme —
   deep/high-input libraries legitimately exceed 90% duplication; total-RNA / ribo-depletion
   legitimately retains rRNA. *"'Extreme' and 'unusual protocol' are the same number"*, and
   the pack sees no prep signal separating them.
2. *Engineering:* FAIL severity on a metric that has never once arrived is *"severity on
   dead code."*

**This slice attacks reason 2 only.** Making the metrics arrive does **not** reopen reason 1
— the biological argument is independent of ingestion and still stands. Both checks stay
WARN-capped. If the dig finds this changes the calculus, flag it in the PRD as an open
question; do not silently add a `fail_*` band.

## Why (moat framing, from contig-next)

- CLAUDE.md #2 ("make every verdict harder to fool"): a verdict axis that structurally
  cannot fire is not a verdict axis. RNA-seq is the **one assay exercised end-to-end in CI**
  (CLAUDE.md), which makes a dead pack there the worst place to have one.
- Depth-first on an already-shipped capability's named follow-on, at a chokepoint with a
  proven template (single-cell ingestion), not a new surface.
- No new dependency, model, `FailureClass`, or dashboard card expected.

## Open questions for the dig / interview

1. **Duplication artifact:** does `nf-core/rnaseq@3.26.0` write Picard
   `*.MarkDuplicates.metrics.txt` by default, and at what path (`results/` vs `work/`)?
   Is it per-sample? Does the pipeline's default `--skip_markduplicates` state matter?
2. **Unit fix, and where:** `PERCENT_DUPLICATION` is 0–1; the band is 0–100. Normalize in
   the new parser (local, safe) or in `qc_ingest.py` (shared — would touch methylseq's
   `percent_duplication`, which reportedly uses a 0–100 scale)? **Blast radius matters:**
   the pack comment says the 0–100 scale was chosen *"matching METHYLSEQ_RULE_PACK's
   percent_duplication usage"* — confirm what methylseq actually ingests before touching
   anything shared.
3. **rRNA artifact:** is there a default machine-readable rRNA source at all? Candidates:
   featureCounts biotype QC (`*.biotype_counts_rrna_mqc.tsv`?), SortMeRNA logs
   (non-default), samtools idxstats. If none is default → honest UNVERIFIED against a named
   artifact, or **remove the check** (the single-cell slice's `pct_reads_mito` precedent).
4. **Gate shape:** confirm the additive gate (rnaseq stays out of
   `_DEDICATED_METRIC_ASSAYS`, `runner.py:73`) so the existing MultiQC pack path
   (`runner.py:274`) is undisturbed, exactly as the composition slice did.
5. **Existing call site:** `runner.py:414` feeds `evaluate_rnaseq_plausibility(metrics)` the
   MultiQC dict. Does the new artifact-parsed metric merge into that dict, or does the
   evaluator take a second source? Which keeps the UNVERIFIED-when-absent guarantee intact?
6. **Does any real fixture exist?** `demo/sample-run/results/multiqc/multiqc_data.json` is
   the repo's only real-shaped report. Is there a real MarkDuplicates artifact anywhere in
   the repo, or must the fixture be synthesized from the documented Picard format?

## Acceptance (test-first)

- A real-shaped Picard MarkDuplicates fixture at the documented path drives a
  `duplication_rate:<sample>` result that **actually fires** (PASS inside the band, WARN
  outside) — the check is no longer UNVERIFIED on a run that has the artifact.
- The unit is correct: a 0.85 `PERCENT_DUPLICATION` scores as 85 against `warn_above: 80.0`
  and **WARNs**; a 0.10 scores as 10 and **PASSes**. (Today 0.85 would silently PASS.)
- A located-but-unparseable artifact → one honest **UNVERIFIED**, never a false pass.
- No artifact at all → the current behavior (UNVERIFIED / silent skip per the dig's finding)
  — never a fabricated value.
- Both checks stay **WARN-capped**: no fixture drives `record.verdict` → FAIL, and the
  `verify` exit code is unchanged.
- The existing rnaseq MultiQC pack path (`RNASEQ_RULE_PACK`) and the composition gate are
  **unchanged** — no regression in their results.

## Guardrails (CLAUDE.md)

- Layer 2 only (verify axis) — no Layer-1 workflow authoring. Satisfied by construction.
- No over-claiming: WARN-capped; **UNVERIFIED is never rendered as PASS**; omit-never-guess
  on an uncomputable metric.
- No guessed slugs. The whole defect is an unverified slug; the fix must name its artifact
  and be tested against a real-shaped fixture — otherwise it re-creates the bug.
- No new dependency (stdlib parse, per the sibling parsers); no raw-read egress.
- Test-first (RED → GREEN); no real nf-core/Picard run in CI.

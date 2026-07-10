# Understanding: annotation-concordance (C7 M4) — Phase 2 deep dig

Dig date: 2026-07-10. Validated against the worktree code by three read-only agents
(parser reuse, concordance contract precedent, tools-injection seam).

## What the work really is

Add a **VEP-vs-SnpEff annotation-consequence concordance** check to the verdict for
both variant assays (`variant_calling`, `somatic_variant_calling`). It is the C1
concordance primitive applied to the annotation assay: two independent annotators run
on the same call set, and their per-variant agreement corroborates that annotation
ran sanely. It is C7's M4 milestone — M1/M2/M3 already shipped (v0.25.0 / v0.26.0).

**Path to take:** the **somatic auto-in-verdict** path, NOT the germline flag path.
`somatic_concordance` is the only concordance that auto-runs inside `_discover_qc`
because its second tool comes free from one run; M4 is the same shape (two annotators,
one sarek run, no user input, no CLI flag).

## Affected areas (file:line, confirmed)

- **Enable SnpEff** — widen two registry literals so one run emits both annotation sets:
  - `src/contig/registry.py:53` germline `{"tools": "haplotypecaller,vep"}` → `+,snpeff`
  - `src/contig/registry.py:40` somatic `{"tools": "strelka,mutect2,vep"}` → `+,snpeff`
  - Update the stale narrating comments at `registry.py:29-39` and `:47-52`.
  - Injection is non-destructive already (`_inject_default_params`, `cli.py:295-316`,
    a `setdefault` merge — a user's own `--tools` still wins). Single call site
    `cli.py:555` in `_dispatch_run`, so **rerun** (`assay=manifest.assay`, `cli.py:652`)
    and **resume** (`cli.py:1391`) both re-apply automatically. No merge-logic change.
- **New verifier** — `src/contig/verification/annotation_concordance.py` (new module),
  cloned from `somatic_concordance.py`'s shape.
- **Auto-wire** — inside `_discover_qc`'s existing `if assay in VARIANT_ASSAYS:` block
  (`runner.py:150-163`), which already loops annotated VCFs for both variant assays.
  `VARIANT_ASSAYS` = `("variant_calling","somatic_variant_calling")` at `registry.py:92`.
- **Tests to update (exact-string asserts break when `,snpeff` is appended):**
  `tests/test_run_default_params.py` (`:65,:70,:75,:94,:136,:137,:152,:172,:175-177`),
  `tests/test_somatic_end_to_end.py:102`. Substring `"vep" in …` tests are unaffected.

## Reusable machinery (don't rebuild)

- **Consequence parser primitives** in `verification/annotation_plausibility.py`:
  `_variant_terms(info_value, key, cons_index)` (per-variant term extractor, works for
  CSQ and ANN given the right index), `_consequence_index_csq(header_lines)` (resolves
  CSQ subfield index from the header `Format:` string), `_ANN_CONSEQUENCE_INDEX=1`
  (SnpEff fixed layout), `_resolve_consequence_index`, `_SEVERITY_RANK`/`_UNKNOWN_RANK`,
  `_most_severe_rank`. These collapse a variant's terms to a single most-severe
  consequence exactly as M3 does — reuse them, don't fork the severity ordering.
- **Concordance contract to mirror** (`somatic_concordance.py`): a module-local
  `_concordance(...)` factory tagging `kind="concordance"`; `SiteKey = (CHROM,POS,REF,ALT)`;
  `_MIN_SHARED = 10` UNVERIFIED floor; `_WARN_BELOW = 0.90`; status limited to
  pass/warn/unverified (never fail); path-COMPONENT tool selection (`{part.lower() …}`);
  a run-level entry that returns `[]` on clean absence and one UNVERIFIED on ambiguity.
- **Verdict flow:** `overall_verdict` (`models.py:78`) is kind-blind on status, so a
  concordance disagreement is at most WARN and never changes the `verify` exit code
  (exit is driven only by output drift / signature mismatch, `cli.py:862-904`).
  `report.py:101-109` already groups `kind=="concordance"` for display.

## Key design decisions to resolve in the PRD interview

1. **Two VCFs, not one.** In nf-core/sarek, VEP and SnpEff typically emit **separate**
   annotated VCFs, and the current parser is single-key (prefers CSQ, ignores ANN in
   the same file). So M4 is most naturally a **two-file join on (CHROM,POS,REF,ALT)**:
   locate the VEP-annotated VCF and the SnpEff-annotated VCF (by `vep`/`snpeff` path
   component, mirroring somatic's `mutect2`/`strelka` selection), parse each variant's
   most-severe consequence from each, join on the shared key, agreement = fraction of
   shared variants whose most-severe term matches. **Must confirm the actual sarek
   output layout / file-naming for the two annotators before planning.**
2. **Consequence agreement first; gene-symbol deferred/informational.** Both parsers
   already yield the most-severe consequence. Gene-symbol needs new subfield extraction
   (CSQ `SYMBOL` via header, ANN `Gene_Name` at fixed index 3) *and* carries the real
   vocab-divergence risk (differing symbol sources). Recommend M4 ships **consequence**
   agreement; gene-symbol is a follow-on.
3. **Vocab is less of a problem than feared for consequences.** SnpEff's ANN
   "Annotation" subfield already uses Sequence-Ontology terms, as does VEP `Consequence`
   — so a conservative term-equivalence map for *consequences* is close to identity.
   (Gene symbols are where divergence bites — another reason to defer that half.)
   Still: exact most-severe-SO-term match is the honest, conservative agreement metric.
4. **Provenance of both versions.** `AnnotationProvenance` (`models.py:206`) is singular
   and `compute_annotation_identity` returns the first VCF's provenance only. Recommend
   M4 **reads both tool+version strings for the concordance message** without changing
   the model; extending provenance to a VEP+SnpEff pair is M5 ("DB-version provenance in
   the reproduce bundle").
5. **Threshold honesty.** `_WARN_BELOW = 0.90` and `_MIN_SHARED_VARIANTS = 10` are the
   uncalibrated engineering defaults consistent with the other three concordance slices;
   never FAIL until calibrated on real data.

## Guardrail check (CLAUDE.md)

On-thesis Layer-2: this is verification (corroboration of two annotators), not Layer-1
workflow authoring, and needs no wet-lab/clinical credentials or proprietary data.
Research-use only — concordance is corroboration, never a pathogenicity/clinical
verdict; UNVERIFIED is never rendered as PASS. Compounds moat #2 (a new verification
signal per run) and gets better as base models adjudicate *why* two annotators disagree.
No drift detected.

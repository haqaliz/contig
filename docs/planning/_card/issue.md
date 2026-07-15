# Card: verdict-neutral-informational-checks

- **Type:** feat
- **Id / slug:** verdict-neutral-informational-checks
- **Branch:** feat/verdict-neutral-informational-checks/aliz
- **Owner:** aliz
- **Source:** inline brief (from `contig-next` handoff — no GitHub issue; `gh issue list`
  returns "No Issues"; id is a slug)
- **Capability:** C3 (biological-plausibility verification) follow-on; touches the shared
  verdict reducer that all seven wired assays traverse.

## Brief

Give informational (band-less) QC rules a verdict-neutral outcome so they stop reducing to
an unfalsifiable `pass`.

Today `duplication_rate` is the only band-less rule in the repo and it always reports
`pass` while asserting nothing biological — a report carrying only `PERCENT_DUPLICATION`
reaches verdict `pass` with nothing actually verified.
`docs/technical/CAPABILITY_ROADMAP.md:654-664` names this "the strongest follow-on
candidate here" and sets an explicit deadline: **"Decide before a second band-less rule
lands."**

Settle the design fork explicitly in the dig:

1. add a verdict-neutral `QCStatus`, **or**
2. exclude band-less rules from `overall_verdict`.

Also decide whether `gene_symbol_concordance` and `x_het_ratio` (already informational in
shape) migrate in this slice or a follow-on.

## Caveat (carried in from the pick)

This is a **semantics change to the shared verdict reducer**, which is exactly why the
v0.38.0 slice deliberately did not fold it in:

> "Deliberately *not* folded into this slice: it changes the shared verdict reducer that
> all seven assays run through, which is a semantics change, not a bug fix."
> — `docs/technical/CAPABILITY_ROADMAP.md:663-664`

`QCStatus` is `pass`/`warn`/`fail`/`unverified` today and is **persisted** into
`run_record.json` and the reproduce bundles, so a new enum value needs back-compat for
pre-change bundles. The C7 M5 `db_version` work set the precedent for that kind of
round-trip back-compat.

## Out of scope

- `runner.py:412`'s `multiqc is not None` gate — a run with no MultiQC report makes both
  RNA-seq plausibility checks vanish rather than reporting `unverified`. A real,
  separately-named pre-existing honesty gap (`docs/technical/CAPABILITY_ROADMAP.md:650-653`),
  adjacent but not this slice.
- Re-opening any **declined-by-design** band (RNA-seq FAIL severity, somatic VAF/PON bands,
  the `duplication_rate` band itself). Those are settled, not pending.

## Source quote (the defect, verbatim)

> **Informational checks have no verdict-neutral status** (surfaced by this slice's review;
> the strongest follow-on candidate here). `duplication_rate` is now the **only band-less
> rule in the repo**, and its always-`pass` is *unfalsifiable* — it asserts "the number is a
> number", not "the data is good" — yet it is verdict-eligible through `overall_verdict`
> like any other pass. A report carrying only `PERCENT_DUPLICATION` therefore reduces to
> verdict `pass` with nothing biological actually verified. **Not a regression** (that
> scenario already reduced to `pass` via `min_sample_count`), and the shape is not new
> (`gene_symbol_concordance` and `x_het_ratio` are informational too) — but `QCStatus` is
> `pass`/`warn`/`fail`/`unverified` with no verdict-neutral option, and this is the first
> rule to need one. **Decide before a second band-less rule lands:** either add a
> verdict-neutral status/kind, or exclude band-less rules from `overall_verdict`.

— `docs/technical/CAPABILITY_ROADMAP.md:654-664`

# Blocked items — what to run, what to record

The 13 items below cannot be finished by an agent: 5 need a real pipeline run
(Nextflow, VEP/SnpEff, a third-party repo) and 8 need real-cohort values before a
band can be set. Each entry says what evidence to collect and what to change
once you have it. Nothing here is a code TODO until the evidence exists.

Rule for all of them: **record the evidence in the roadmap paragraph before
changing a band or a baseline.** Synthetic stand-ins are explicitly rejected —
the roadmap already calls its own synthetic labels self-graded, and a band set
on invented numbers is worse than no band.

---

## Manual gates (5)

### C2-23 — real Nextflow/Batch smoke, incl. `-resume` of a SIGKILLed task

Run one real nf-core/rnaseq run on your own compute, kill a task mid-flight
(`SIGKILL` the Nextflow child), and let the loop resume it.

```
contig run <pipeline> --input <sheet.csv> --profile <docker|singularity> ...
# mid-run: kill -9 the task's process group, then
contig resume <run_id>
```

Record: whether `-resume` re-runs only the killed task, the detector class it
lands in, and the terminal outcome. Closes C2#23 and C8-27's cousin.

### C7-3 — real VEP/SnpEff/sarek post-merge smoke (incl. GRCh37 iGenomes)

One real sarek run with `--tools vep,snpeff` against a GRCh37 iGenomes key, then
a GRCh38 run. Record the `AnnotationProvenance` (tool, version, cache build) and
whether `annotation_present` / `annotation_complete` fire, and the
`consequence_concordance` value.

### C8-26 — real-repo reproduce smoke test

```
contig reproduce https://github.com/<cooperative-repo> --allow-fetch --rev <sha> \
  --run --claims <claims.json>
```

Record: `reproduce-guard` outcome, and whether the freshness guard blocks a
legitimate repo (its committed revisit trigger). This is also the first real
exercise of fetch-by-bare-commit (C8-27).

### C8-27 — fetch-by-bare-commit server policy

Depends on C8-26. Record the server's `uploadpack.allowReachableSHA1InWant`
setting and whether `--rev <sha>` fetched. If it refuses, the refusal message is
the accepted outcome — do **not** add a silent full-clone fallback.

### C8-28 — live-LLM `extract_with_llm` seam

Run `contig extract-claims` with the LLM assist enabled against one real paper's
text once: assert the parsed shape matches the seam's declared shape and record
the prompt/response size. CI keeps the stubbed seam.

---

## Calibration (8)

For each: collect ≥20 real runs of that assay, then set the band and record the
distribution (min/p05/median/p95/max) in the roadmap paragraph. Until then the
check stays informational or WARN-capped, never FAIL.

| ID | What to measure | Then |
|----|-----------------|------|
| C1-3 | concordance value distribution per assay (germline genotype/site, RNA-seq spearman, somatic Jaccard, SC spearman) | set `fail_*` bands per assay; keep corroboration ≠ ground truth wording |
| C2-8 | stall durations on real runs (how long "no heartbeat" before a genuine stall) | replace the reasoned 1 h `--stall-timeout` default |
| C2-13 | `realtime` vs `time_limit` on real time-limit kills | calibrate the 1.5× factor and the ceiling |
| C3-7 | Ti/Tv, het/hom, variant count, duplication, mapping rate by capture type (WGS/WES/panel) | capture-type-aware bands + tighten the WES-safe bands |
| C3-8 | inferred sex vs reported sex on real runs with a sex column | FAIL severity for sex-check |
| C4-2 | `normal_median_vaf` on known-clean tumor/normal pairs | FAIL band (currently WARN at 0.30) |
| C6-3 | promote real runs through `contig corpus-promote` / the reproduce pending queue | grows the non-synthetic corpus; the guard baselines move only via `--update-baseline` |
| C9-4 | `runs/triage-ledger.jsonl` confidence vs eventual verdict over ≥50 keyed runs | pick the budget/threshold; shadow mode stays default until then |

---

## Not blocked, but deliberately not built (declined by design)

16 items in `docs/technical/CAPABILITY_ROADMAP.md` are recorded as declined, not
deferred (RNA-seq/somatic FAIL bands, `pon_applied`, BGZF fix target, BAM→CRAM,
AWS Batch diagnosis, etc.). Do not "finish" these; the reasoning is in the
roadmap. `BACKLOG.md` excludes them from the 87.

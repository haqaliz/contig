# Agent design partners (synthetic pre-validation)

Status: **run on 2026-11-08** with four personas; reports are in
`agent-runs/` and the synthesis is `AGENT_VALIDATION_FINDINGS.md`.

Purpose: exercise the research-workbench CLI/docs as different user personas
before spending time on human recruitment. This is **pre-validation**, not a
substitute for real users.

## What agents can and cannot validate

| Agents can validate | Agents cannot validate |
|---|---|
| Task completion on real fixture/data files | Real trust in the result |
| Command discoverability and error messages | Willingness to pay or budget ownership |
| Documentation gaps and confusing output | Messy real-world data/edge cases |
| Reproducibility and exact commands | Clinical/research judgment |
| Missing filters/columns/states | Whether a lab would change its workflow |

Treat agent findings as a bug/UX list, not a market signal.

## Personas

### A — Lone computational biologist
- Can code; is the lab's only pipeline person.
- Has a VCF, a panel BED, and a run bundle.
- Wants a shortlist and a shareable report fast.
- May read `--help` and source code if needed.
- Task: variants → readiness → report → ask; time each step.

### B — Wet-lab scientist who cannot code
- Must use only `docs/USAGE.md` and `--help`.
- Must not read source code or internal JSON shapes.
- Has a VCF + a gene list; no BED, no depth file.
- Wants to know which genes are safe to interpret.
- Task: build a panel → readiness (if depth available) → report.
- Record every point where they need a concept they do not know.

### C — Core facility operator
- Runs many samples; cares about consistency and handoff.
- Has three M1 variant JSONs, a panel BED, and a run bundle.
- Task: panel registry → cohort build/query → report-check → shareable report.
- Record missing batch/cohort operations.

### D — Biotech researcher / auditor
- Cares about provenance, signatures, and reproducibility.
- Task: report → report-check → report-diff → ask about provenance.
- Record any claim that cannot be traced to a file/hash.

## Constraints for all persona agents

- Work only in the repo checkout; do not edit source or docs.
- Use `/tmp/agent-<persona>/` for outputs.
- Record exact commands, exit codes, wall time, and confusing output.
- Do not invent missing data; if an input is absent, note it.
- Do not claim clinical truth; research-use only.
- Stop after the task list; do not “fix” anything.

## Task script

Use the real data already in `data/` and the fixtures in `tests/fixtures/`:

**A — computational biologist**
1. `contig variants tests/fixtures/variants/sample.vcf --clinvar tests/fixtures/variants/clinvar.vcf --iranome tests/fixtures/variants/iranome.tsv --frequencies tests/fixtures/variants/frequencies.tsv --build GRCh37 --gene BRCA1 --out ...`
2. `contig readiness` from the nf-core CRAM/BED.
3. `contig report` on `tests/fixtures/reporting/runs/r1` with the M1/M2 fixture JSON.
4. `contig ask` for verdict and GENE3 readiness.
5. Time each step; note missing columns/filters.

**B — wet-lab scientist (docs only)**
1. Read `docs/USAGE.md` sections for panels/readiness/report.
2. Build a BRCA1/BRCA2 panel with `--genes` and the real GTF/HGNC.
3. Run `contig readiness` using a depth TSV if they can produce one; if not,
   record the exact blocker.
4. Build a report from the fixture run.
5. Report every term they had to guess (`BED`, `CRAM`, `sidecar`, `FASTA`).

**C — core facility**
1. `contig panel-build` and `panel-list`.
2. `contig cohort-build` from `tests/fixtures/cohort/run1.json` etc.
3. `contig cohort-query --gene BRCA1` and `--min-runs 2`.
4. `contig report` + `report-check` + `report-diff`.
5. Note missing batch/export/workspace features.

**D — biotech/auditor**
1. `contig report` + `report-check`.
2. `contig report-diff` against a copy with one changed spec.
3. `contig ask r1 "show me the provenance"`.
4. Verify every claim in the answer has a path + SHA-256.
5. Note any untraceable claim or missing signature explanation.

## Report format

Each agent writes `docs/validation/agent-runs/<persona>.md` (or `/tmp` if not
committing) with:

```
# Persona A — <role>
Date:
Environment: <commit, OS>

## Task results
| Task | Command | Exit | Time | Success? | Notes |
|---|---|---|---|---|---|

## Blockers
1. ...

## Confusing output / docs gaps
1. ...

## Missing features
1. ...

## Quote
"..."

## What I would do next
1. ...
```

## How to run

- Use one subagent per persona in parallel.
- Give each the persona prompt, the task script, and the constraints above.
- Do not give them the source code for persona B.
- After all reports, synthesize into
  `docs/validation/AGENT_VALIDATION_FINDINGS.md` with:
  - blockers (must fix before dashboard),
  - UX/docs fixes,
  - missing features (backlog),
  - false positives/limitations of the synthetic run.
- Update `BACKLOG.md` / `DECISIONS.md` only after synthesis.

## Decision rule

- **Blocker** = a persona cannot complete the task without reading source code
  or inventing data. Fix before the dashboard.
- **Friction** = task completes but takes unnecessary attempts or confusing
  output. Fix in the dashboard/docs slice.
- **Wish** = a missing feature or market signal. Backlog; do not build on agent
  evidence alone.

Agents cannot approve the product. The human gate remains ≥3/5 partners
completing core tasks with trust ≥4 when human validation resumes.

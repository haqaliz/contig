# Agent validation findings

Date: 2026-11-08. Four synthetic personas (A–D) ran the research-workbench CLI on
the downloaded data and fixtures. Full reports: `docs/validation/agent-runs/`.
This is pre-validation: it found concrete bugs/UX gaps, not market evidence.

## What ran

| Persona | Tasks | Result |
|---|---|---|
| A — lone computational biologist | variants → readiness → report → ask | All completed; fast (<1 s each after locating the venv) |
| B — wet-lab scientist (docs only) | panel → readiness → report | Panel/report succeeded; readiness blocked without a BAM/CRAM or depth TSV |
| C — core facility | panel → cohort → report/check/diff | Completed; found registry/cohort integrity bugs |
| D — biotech/auditor | report/check/diff/ask provenance → tamper probes | Completed; found report-artifact binding gaps |

## Blockers fixed in this pass

| Finding | Fix |
|---|---|
| Panel `--version 2` silently overwrote v1 (same id) | Panel id now includes the version; v1/v2 coexist |
| Cohort double-counted duplicate input content | Inputs deduped by SHA-256; duplicates noted and excluded |
| `report-check` ignored the HTML hash; tampering passed | `ReportMeta.html_path` + `report-check` verifies `html_sha256` |
| Sidecar paths were cwd-relative; checks failed from another directory | Report inputs stored absolute |
| Unsigned run labelled “Signed/reproducible run record” | Label is “Run record”; provenance explains unsigned/signing |
| Report variant table dropped rsid/GT/depth/VAF/filter/ClinVar review | Full evidence columns added; unannotated rows now say `unannotated` |
| `ask` suggested commands failed for a custom runs-dir | Actions preserve `--runs-dir` and put the run id first |
| Generic frequency TSV labelled `gnomad_af`/“gnomAD AF” | Renamed public field/column to `population_af`/“Population AF” |
| `panel-list` had no header | Header added |
| Readiness gave only exon rows; no gene-level answer | `--by-gene` aggregates to one row per gene with worst state and weighted metrics |
| `report-diff` always exited 0 on differences | `--fail-on-diff` exits 1 |
| `report` failed when `--out` parent did not exist | Parent directories are created |
| Audit template omitted the repair chain | Audit now includes repairs |
| `report-check` did not print expected/actual hashes | Prints both for stale/missing items |

## Remaining findings (not blockers for the dashboard)

| Area | Finding | Next action |
|---|---|---|
| Report trust | Sidecar is unsigned and editable; HTML hash is checked, but the sidecar itself has no signature | **Fixed (Unreleased):** `contig report` signs the sidecar with `CONTIG_SIGNING_KEY` (detached Ed25519 `<sidecar>.sig.json`); `report-check` verifies it and fails on tampering; `--require-signature` rejects unsigned reports |
| Report trust | `report-check` verifies inputs + HTML, not the run’s declared outputs or the tables’ upstream sources | Add `--outputs` / `--sources` / `--base-dir`; reuse `contig verify` |
| Report trust | No assay/build/gene compatibility preflight between run, variants, and readiness | Warn on assay/gene/build mismatch before rendering |
| Report completeness | Provenance ends at the M1/M2 JSON; upstream VCF/depth/BED paths may be absent or placeholder | Recurse into table `meta.sources` and label missing upstream evidence |
| Report portability | HTML + sidecar do not bundle the attached tables; rows beyond `max_rows` are not in the artifact | Add a portable report bundle (HTML + sidecar + tables) |
| Panel registry | No archival/diff; panel meta lacks GTF/HGNC path+SHA-256 | Add panel archive/diff and source hashes |
| Cohort | No append/list/merge; query does not show contributing run labels | Add cohort lifecycle and opt-in traceability |
| Batch/workspace | `report`/`report-check` are one-at-a-time; defaults are cwd-relative | Add a project manifest and batch commands |
| Readiness | Build/preflight checks and caveat coverage are not explicit; BED3 labels are empty | Add build matching, caveat coverage, and gene annotation guidance |
| Scale | WGS inputs still need a region/gene first | Add a `--region`/`--gene` guard and clear cap |
| M8 | Federation needs consent/privacy/tenancy/legal design | PRD + architecture only; no code |

## Silent/unsafe behaviors to keep fixed

- Never call an unsigned record “signed.”
- Never let `report-check` pass after the HTML changes.
- Never count duplicate cohort inputs twice.
- Never let a panel version overwrite another.
- Never label a generic frequency source as gnomAD.
- Never render an unannotated variant as a blank row.

## Quotes

> “The four commands run in under two seconds once I find the repo's venv … but
> the two artifacts I would hand to a PI are thinner than the evidence I started
> with.” — Persona A

> “I have the VCF … Contig built a clean panel in seven seconds, then stopped:
> to tell me whether the genes are safe to interpret it needs a BAM/CRAM I was
> never told to ask for.” — Persona B

> “A version bump silently replaces the panel I shipped last month, and a
> duplicated run silently doubles its frequency in the cohort.” — Persona C

> “I can change the HTML or the sidecar and `report-check` still says ‘All report
> inputs are current.’ That is not an audit trail.” — Persona D

## Decision

- The blockers listed above are fixed and covered by tests.
- The remaining findings are backlog; they do not block the read-only dashboard.
- Agent validation **cannot** approve trust/WTP. Human validation remains
  ≥3/5 partners completing core tasks with trust ≥4 when recruitment resumes.

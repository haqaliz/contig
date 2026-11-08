# Persona C — Core facility operator
Date: 2026-11-08
Environment: commit `c722aa4`, macOS 26.5.2 (Darwin 25.5.0) arm64, Python 3.12.13. Repo build `contig 1.0.0` run as `uv run contig`. Caveat: `contig` on `$PATH` is Homebrew `0.61.0`, which has no `panel-build`, `cohort-build`, or `report` commands (all exit 2).

## Task results
| Task | Command | Exit | Time | Success? | Notes |
|---|---|---|---|---|---|
| 1 panel-build | `uv run contig panel-build --name "Hereditary cancer BRCA" --genes BRCA1,BRCA2 --gtf data/ensembl/Homo_sapiens.GRCh38.113.gtf.gz --hgnc data/mane/hgnc_complete_set.txt --out-dir /tmp/agent-C/panels` | 0 | 6.99s | yes | Panel `hereditary-cancer-brca-a3d15b1d`; BED 50 rows; transcripts `ENST00000357654`, `ENST00000380152`; SHA-256 `a3d15b1d…`; meta records build, genes, method, created_at |
| 1 panel-list | `uv run contig panel-list --dir /tmp/agent-C/panels` | 0 | 0.16s | yes | Headerless TSV: `id  version  name  source  genes  build` (columns inferred from docs, not output) |
| 1 registry version probe | same `panel-build` with `--version 2`, same name/genes/out-dir | 0 | not timed | destructive | Same id; v1 meta overwritten in place; `panel-list` shows only v2; no warning |
| 2 cohort-build | `uv run contig cohort-build --name "Lab cohort" --variants tests/fixtures/cohort/run1.json,tests/fixtures/cohort/run2.json,tests/fixtures/cohort/run3.json --out /tmp/agent-C/cohort.json` | 0 | 0.17s | yes | 3 variants, 3 genes, 3 runs; input paths + SHA-256 in meta |
| 2 cohort-query gene | `uv run contig cohort-query --cohort /tmp/agent-C/cohort.json --gene BRCA1` | 0 | 0.16s | yes | 1 variant: 17:43057063 C>CT, seen 3/3, frequency 1.0000 |
| 2 cohort-query min-runs | `uv run contig cohort-query --cohort /tmp/agent-C/cohort.json --min-runs 2` | 0 | 0.15s | yes | 3 variants: BRCA1 3/3, EGFR 2/3, GJB2 2/3 |
| 2 duplicate-input probe | `cohort-build` with `run1.json,run1.json,run2.json` | 0 | ~0.2s | **no — wrong counts** | Reports 3 runs / BRCA1 3/3 despite only 2 unique files; label collision becomes `run1-3ca83f` but is still counted |
| 3 report | `uv run contig report r1 --runs-dir tests/fixtures/reporting/runs --variants tests/fixtures/reporting/variants.json --readiness tests/fixtures/reporting/readiness.json --spec tests/fixtures/reporting/spec.json --out /tmp/agent-C/report/r1.html --meta /tmp/agent-C/report/r1.report.json` | 0 | 0.16s | yes | 5.8 KB inline-CSS HTML; sidecar lists 3 inputs + SHA-256 + `html_sha256`; verdict WARN; 2 of 3 variants and 2 of 3 targets shown per `max_rows: 2` |
| 3 report-check current | `uv run contig report-check /tmp/agent-C/report/r1.report.json` | 0 | 0.16s | yes | `All report inputs are current.` |
| 3 report-diff self | `uv run contig report-diff /tmp/agent-C/report/r1.report.json /tmp/agent-C/report/r1.report.json` | 0 | 0.15s | yes | `No differences.` |
| 3 report changed spec | same `report` with `/tmp/agent-C/report/spec-v2.json` (title, `max_rows` 2→3, notes) | 0 | 0.16s | yes | Second HTML + sidecar |
| 3 report-diff changed spec | `uv run contig report-diff /tmp/agent-C/report/r1.report.json /tmp/agent-C/report/r1-v2.report.json` | 0 | ~0.2s | yes | 4 changes: `html_sha256`, `spec.max_rows`, `spec.notes`, `spec.title`; exit 0 despite differences |
| 3 report-check stale | copy of `variants.json` referenced by a report, then one value edited | 1 | ~0.2s | yes (correctly fails) | `stale variants: /tmp/...`; `1 input(s) stale or missing.` |
| 3 report-check missing | same sidecar after moving the variants copy away | 1 | ~0.2s | yes (correctly fails) | `missing variants: /tmp/...` |
| 3 report-check after HTML edit | appended `<!-- tampered -->` to `r1.html`, reran check | 0 | ~0.2s | **no — false all-clear** | All inputs current; sidecar's `html_sha256` is never compared |
| 3 report-check from another cwd | `cd /tmp && uv run --project /Users/aliz/dev/at/contig contig report-check /tmp/agent-C/report/r1.report.json` | 1 | ~0.2s | expected fail, handoff gap | All three inputs `missing`; sidecar stores CLI-relative paths, no base-dir option |
| 3 report to missing dir | `--out /tmp/agent-C/no-such/dir/r1.html` | 1 | ~0.2s | no | `[Errno 2] No such file or directory`; `report` does not create parent dirs, while `panel-build` creates its `--out-dir` |

## Blockers
1. **Panel versioning silently destroys the previous version.** `panel-build` IDs a panel as name-slug + BED hash; `--version` is metadata only. Re-running the same name/genes with `--version 2` into the same registry produced the same id, replaced v1's JSON (`created_at` changed, version `1`→`2`), and `panel-list` showed one row. No warning, no backup, no history. A core facility cannot keep a v1/v2 registry or audit which panel produced an old report. This completed the task but makes the registry unsafe to trust.
2. **Cohort frequencies double-count duplicate input content.** Passing `run1.json` twice, or a byte-identical copy under a different path (same SHA-256), yields `total_runs: 3` and BRCA1 `seen_runs: 3, frequency: 1.0000` when only two unique runs existed. The builder notices the label collision (`run1-3ca83f`) but still counts both. Any directory glob or re-run silently inflates the numbers an operator hands onward. This is wrong data, not a cosmetic issue.
3. **The two primary registry objects have no lifecycle controls.** There is no `panel-update`/`panel-delete`/`panel-diff` and no `cohort-add`/`cohort-list`/`cohort-merge`. A cohort cannot be extended without rebuilding from every input file, and a panel cannot be revised without risking the overwrite in blocker 1. For a facility running many samples, this blocks normal handoff bookkeeping.

## Confusing output / docs gaps
1. **`report-check` does not check the report.** Appending bytes to `r1.html` still printed `All report inputs are current.` and exited 0. The sidecar contains `html_sha256`, so the name invites exactly the wrong assumption. Docs correctly say "inputs", but an operator reads the command name.
2. **"Signed/reproducible run record" vs "Signature: Unsigned" in the same report.** The `run_record` input is always labeled "Signed/reproducible run record" in the sidecar/HTML, while the provenance table says `Signature: Unsigned` and the fixture record has no signature field. Contradictory handoff language; do not call a record signed when it is not.
3. **Report sidecar paths are not portable.** Paths are stored exactly as passed on the command line. From `/tmp`, every input was reported `missing`; there is no `--base-dir`, no bundle root, and no warning. Docs call the HTML shareable but do not explain that `report-check` is cwd-sensitive.
4. **`panel-list` has no header.** The six columns are unlabeled; an operator has to infer that column 2 is version. Fine for a script, poor for a handoff terminal.
5. **Panel provenance is thin.** The meta note says only `HGNC validated against hgnc_complete_set.txt` (basename). It records no GTF path, GTF SHA-256, HGNC path/SHA-256, or source versions. The BED hash identifies the intervals, not the annotation build inputs.
6. **Inconsistent output-dir behavior.** `panel-build` created `/tmp/agent-C/panels`; `report` failed with `[Errno 2]` when the parent of `--out` was absent. Batch generation needs a `mkdir` wrapper.
7. **Blank provenance cells.** `Assay` and `Nextflow version` render as empty table cells with no "not recorded/unknown" marker, which reads as an omission rather than missing source metadata.
8. **Two `contig` binaries on this machine.** `contig` resolves to Homebrew `0.61.0` without the workbench commands; the checkout is `1.0.0` via `uv run contig`. The docs do not say how to invoke the checkout version; a facility following install docs can hit `No such command` on every task.
9. **Cohort query hides the contributing runs.** Output gives `seen_runs` but not labels. The labels are in `cohort.json` meta, so "which sample had this?" requires opening JSON or scripting; docs do not say this.
10. **`report-diff` always exits 0.** `same: false` and a changed spec are visible in text/JSON, but there is no non-zero exit or `--fail-on-diff`, so CI/QC gating must parse output.
11. **"full table is in the attached JSON" is not true of the report artifact.** The sidecar records the variants/readiness paths and hashes but does not embed or bundle the tables. Sharing `report.html` + `r1.report.json` loses the rows beyond `max_rows`.
12. **`cohort-build` says "3 run(s)" when it means 3 input files.** With duplicates, the summary and denominator are both inflated; the message should distinguish total inputs from unique runs.

## Missing features
1. **Batch operations.** `report` accepts one run id (`r2` is rejected as an extra argument), `report-check` accepts one sidecar (a directory errors as "sidecar not found"), and there is no report index/list. A facility with dozens of runs must write its own loop and manifest.
2. **Cohort lifecycle.** No append/add, list, merge, or re-query-without-rebuild. No content-hash dedupe and no `--strict`/`--dedupe` warning. No operator-supplied sample labels (`--labels map.tsv`); labels come from filenames, though `--anonymize` exists.
3. **Panel lifecycle.** No delete/deprecate, diff, history, or side-by-side versions. `panel-build`, `panel-list`, `panel-show` are the entire surface.
4. **Workspace/project manifest.** No `workspace` command or config tying together panel registry, runs dir, cohort path, report output root, and project/sample metadata. Defaults are cwd-relative (`panels/`, `runs/`, `cohort.json`), so every command needs repeated paths and sidecars break when cwd changes.
5. **Portable report bundle/export.** `export` is run-only RO-Crate; there is no report/cohort/panel export. No option to embed full tables or copy inputs alongside the sidecar. PDF remains "open HTML and print" (docs acknowledge this).
6. **Report-sidecar pinning.** No panel id/version/checksum, no cohort id, and no HTML path — only the run record, variants JSON, readiness JSON, and an HTML hash. A report cannot be tied back to the registry entry that defined its targets.
7. **Integrity commands.** No `report-check --html` to verify `html_sha256`, no `report-check --dir`, no `report-diff --fail-on-diff`. No verify path for a report bundle analogous to `contig verify` for run outputs.
8. **Cohort traceability.** No opt-in per-variant run labels or sample mapping, even though labels are already stored in `cohort.json`. Counts alone are not actionable for a facility.
9. **Panel source provenance.** No GTF/HGNC path+SHA-256 in panel meta, so a panel rebuild cannot be audited against its annotation inputs.

## Quote
"Panel build is fast and the report looks professional, but I would not run a facility on this yet: a version bump silently replaces the panel I shipped last month, and a duplicated run silently doubles its frequency in the cohort. Those are the two numbers I hand to PIs, so they have to be right before I trust the registry."

## What I would do next
1. Dedupe cohort inputs by SHA-256 myself and keep a manifest; do not run `cohort-build` on a glob until duplicate handling is fixed.
2. Treat panel IDs as immutable: archive v1 BED+JSON read-only and build revisions under a new name; manually record the panel id/version/checksum in the report spec notes because the sidecar does not.
3. Wrap `report` and `report-check` in a script that uses absolute paths, a per-project output root, and copies HTML + sidecar + input JSONs together; do not rely on `report-check` alone for report integrity.
4. Ask for batch report/check plus a project manifest before scaling past a handful of runs.
5. Test the generated BED end-to-end with `readiness` on a real depth input before handing it to a lab; that path was outside this persona script and is untested here. Research use only — this run does not establish clinical validity.

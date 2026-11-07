# Research Report Builder — M1 Implementation Plan

**Status:** implemented 2026-11-07 — Tasks 1–7; 33 report tests pass.

**Goal:** Add `contig report` and `contig report-check`: a self-contained HTML
research report built from a run bundle plus optional M1/M2 JSON tables, with a
machine-readable sidecar and a staleness check. No clinical claims.

**Architecture:** A new `contig.reporting` package. A small Pydantic spec drives
section selection and narrative; stdlib renderers produce inline-CSS HTML and a
JSON sidecar. The CLI commands are thin Typer wrappers in `src/contig/cli.py`.
No new dependencies, no network, no raw reads.

## Global Constraints

- **Research-use only.** No diagnosis, ACMG adjudication, treatment advice, or
  medical sign-off.
- **Self-contained HTML.** Inline CSS, no external assets, no vendored JS.
- **Escape everything.** Every user-provided or bundle-provided string goes
  through `html.escape`.
- **Traceability.** Sidecar lists input paths + SHA-256; section headers name the
  source. `report-check` recomputes.
- **Caps.** Variant/readiness tables cap at `max_rows` (default 100), with a
  note; full data stays in the attached JSON.
- **No new dependencies.** Stdlib + existing pydantic/typer.
- **Test-first.**

---

### Task 1: Spec and metadata models

**Files:**
- Create: `src/contig/reporting/__init__.py`
- Create: `src/contig/reporting/models.py`
- Create: `tests/test_reporting_models.py`

**Interfaces:**
- `Reviewer` Pydantic: name, role, reviewed_at, statement.
- `ReportSpec` Pydantic: title, subtitle, author, institution, summary, notes,
  limitations, template (`publication|internal|audit`), reviewer, max_rows.
  Defaults are safe and the template is validated.
- `ReportInput` Pydantic: kind, path, sha256, note.
- `ReportMeta` Pydantic: run_id, generated_at, contig_version, spec, inputs,
  html_sha256, notes.

**Tests:** defaults, template validation, max_rows bounds, JSON round-trip.

---

### Task 2: Input loaders

**Files:**
- Create: `src/contig/reporting/inputs.py`
- Create: `tests/test_reporting_inputs.py`

**Interfaces:**
- `load_run_bundle(runs_dir, run_id) -> RunRecord`
- `load_variants_json(path) -> dict` (validate `meta` + `variants`)
- `load_readiness_json(path) -> dict` (validate `meta` + `targets`)
- `input_record(kind, path, note) -> ReportInput` (SHA-256 via `sha256_file`)
- `run_bundle_dir(runs_dir, run_id) -> Path`

**Tests:** real model round-trip for a synthetic run; JSON shape validation;
missing file errors; hash is recorded.

---

### Task 3: Summaries

**Files:**
- Create: `src/contig/reporting/summaries.py`
- Create: `tests/test_reporting_summaries.py`

**Interfaces:**
- `variant_summary(variants_json) -> dict` with total, ClinVar buckets
  (pathogenic/likely/conflicting/VUS/benign/absent), top genes, filter summary.
- `readiness_summary(readiness_json) -> dict` with counts by readiness and a
  list of not-interpretable targets.
- `qc_summary(record) -> dict` with pass/warn/fail/unverified counts and the
  deciding check names.
- `verdict_label(verdict) -> str`.

**Tests:** counts on fixtures, empty inputs, no false "benign" for missing data.

---

### Task 4: HTML renderer

**Files:**
- Create: `src/contig/reporting/render.py`
- Create: `tests/test_reporting_render.py`

**Interfaces:**
- `render_html(record, spec, variants, readiness, inputs, signature) -> str`
- Section helpers for header, banner, verdict, QC, methods, repair chain,
  variants, readiness, provenance, limitations, reviewer.
- `TEMPLATE_SECTIONS`: section order per template.

**Tests:**
- Required sections present for each template.
- Verdict and QC values rendered.
- Variant/readiness tables capped with a note.
- Reviewer block and research-use banner present.
- HTML escaping of `<script>` in narrative.
- No external `http` assets.

---

### Task 5: Build and sidecar

**Files:**
- Create: `src/contig/reporting/build.py`
- Create: `tests/test_reporting_build.py`

**Interfaces:**
- `build_report(runs_dir, run_id, spec, variants_path, readiness_path) -> tuple[str, ReportMeta]`
- `write_report(html, meta, out_path, meta_path)`.
- `check_report(meta_path) -> list[dict]` with current/stale per input.

**Tests:**
- Sidecar inputs include run_record + attached tables with hashes.
- `html_sha256` matches the written HTML.
- `check_report` current, then stale after mutating an input.
- Missing run/input errors.

---

### Task 6: CLI commands

**Files:**
- Modify: `src/contig/cli.py`
- Create: `tests/test_cli_report.py`

**Interfaces:**
- `contig report RUN_ID [--runs-dir] [--variants] [--readiness] [--spec]
  [--template] [--out] [--meta]`
- `contig report-check META_JSON`

**Tests:**
- `--help` lists options.
- A synthetic run builds HTML + sidecar; the research-use notice is on stderr.
- `report-check` current/stale.
- Missing run/input exits non-zero.
- `--template audit` changes the section set.

---

### Task 7: Docs and manual verification

**Files:**
- Modify: `docs/USAGE.md` (report section)
- Modify: `CHANGELOG.md` (Unreleased entry)

**Manual checks:**
- Build a report from the M1/M2 JSON produced on the nf-core chr20 data.
- Open the HTML; confirm it is self-contained and readable when printed.
- Change a table input; `report-check` reports stale.
- Confirm no external asset requests and no raw reads in the HTML.

---

## Verification

```bash
uv run pytest tests/test_reporting_*.py tests/test_cli_report.py -q
uv run contig report --help
uv run contig report-check --help
```

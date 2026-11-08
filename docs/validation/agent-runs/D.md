# Persona D — Biotech researcher / auditor

Date: 2026-11-08
Environment: commit `c722aa4132589e08316561993f5b87f3b8637df2`, macOS 26.5.2 (arm64), Contig 1.0.0, Python venv at `.venv`. Fixture run `tests/fixtures/reporting/runs/r1`; outputs in `/tmp/agent-D/`. Research use only; I did not assess clinical truth.

## Task results

| # | Task | Command | Exit | Time | Success? | Notes |
|---|---|---|---|---|---|---|
| 1 | Build report with fixture variants/readiness/spec | C1 | 0 | 0.15 s | Yes | HTML + sidecar written; spec title/reviewer/max_rows applied; `publication` template. |
| 2 | `report-check` on the sidecar | C2 | 0 | 0.15 s | Yes | 3/3 inputs "current". Does **not** check `html_sha256`, outputs, or upstream sources. |
| 3 | `report-diff` vs a copy with one spec field changed | C3 | 0 | 0.15 s | Yes | Only `spec.title` shown. The edited copy still carried the old `html_sha256`; diff did not flag that. |
| 4 | `report-diff` vs a regenerated report with the same spec change | C4 | 0 | 0.15 s | Yes | `html_sha256` + `spec.title`; `--json` gives `same: false`. |
| 5 | `ask` "show me the provenance" (text + JSON) | C5 | 0 | 0.14 s | Partial | One citation, hash matches the file. All run-level claims except `unsigned` are traceable; see B3. |
| 6 | `ask` "is this run signed and how do I verify the signature?" | C6 | 0 | 0.14 s | No | Same generic provenance answer; no signature explanation, key id, or `keygen` next step. |
| 7 | Tamper the HTML after checking, then `report-check` | C7 | 0 | 0.16 s | **Probe failed (unsafe)** | Appending one comment changed the HTML SHA; check still said "All report inputs are current." |
| 8 | Tamper the sidecar (reviewer statement + zeroed `html_sha256`), then `report-check` | C8 | 0 | 0.15 s | **Probe failed (unsafe)** | Still "All report inputs are current." The sidecar is not signed and is not self-checking. |
| 9 | Run `report-check` from another working directory | C9 | 1 | 0.16 s | Probe (expected fail) | All 3 inputs read "missing"; paths are relative to the generation CWD, no `--base-dir`. |
| 10 | Modify `variants.json`, then `report-check` | C10 | 1 | 0.14 s | Yes | Correctly reported `stale variants` and exit 1. |
| 11 | `contig verify` with the correct runs dir | C11 | 1 | 0.15 s | Yes (tool correct) | Detects `missing: multiqc/multiqc_report.html`; `report-check` passed the same bundle. |
| 12 | Follow the `ask` suggested action as printed | C12 | 1 | 0.15 s | No | `no bundled run 'r1' in runs` — suggested action dropped `--runs-dir`. |

What worked: the three sidecar input hashes match the files; `report-check` correctly exits 1 on a modified input; `report-diff` correctly shows the one changed spec field; the HTML is self-contained (inline CSS, no external assets); every command finished in ~0.15 s.

### Ask claim audit (C5)

The answer cites one file: `tests/fixtures/reporting/runs/r1/run_record.json` with SHA-256 `9634a7f0…e6e84d0`. I recomputed it with `shasum -a 256`; it matches.

| Claim in the answer | Backing field | Traceable? |
|---|---|---|
| `Pipeline: nf-core/rnaseq @ 3.14.0` | `pipeline`, `pipeline_revision` | Yes |
| `Contig 1.0.0` | `contig_version` | Yes |
| `Nextflow unknown` | `nextflow_version: null` | Yes |
| `Input checksums: 1` | `len(input_checksums) == 1` | Yes, but only as a count; the path/value are not shown |
| `Output checksums: 1` | `len(output_checksums) == 1` | Yes, but the one output file is absent from the bundle |
| `Container digests: 0` | `len(container_digests) == 0` | Yes |
| `Signature: unsigned` | No signature field in `run_record.json`; no `signature.json` in the bundle | **No** — inferred from absence, not a hashed field |

Full hashes recomputed during the audit (before the C7 mutation of the HTML):

```text
9634a7f0aab24f9c527c5cc2ca55c472e68c413b9c975d7eb96fad90ce6e84d0  tests/fixtures/reporting/runs/r1/run_record.json
8a227322cf3f5542e28ea17b6f45666e2057ad9d032feab16797f2144881e539  tests/fixtures/reporting/variants.json
8731f2dff4d8dfc2be5ed34ba3748142f37ba5730c1a4501bc15c3d0faf029dc  tests/fixtures/reporting/readiness.json
92bde3282163e5f92a1a43611b5038bdf87b2ac666f156b9d00b0fe75e61ef0e  /tmp/agent-D/report.html
```

Exact commands (from repo root unless noted):

```bash
# C1
/usr/bin/time -p .venv/bin/contig report r1 \
  --runs-dir tests/fixtures/reporting/runs \
  --variants tests/fixtures/reporting/variants.json \
  --readiness tests/fixtures/reporting/readiness.json \
  --spec tests/fixtures/reporting/spec.json \
  --out /tmp/agent-D/report.html --meta /tmp/agent-D/report.json

# C2
/usr/bin/time -p .venv/bin/contig report-check /tmp/agent-D/report.json

# C3  (copy changed spec.title only)
/usr/bin/time -p .venv/bin/contig report-diff /tmp/agent-D/report.json /tmp/agent-D/report-copyspec.json

# C4  (regenerated from /tmp/agent-D/spec-revised.json)
/usr/bin/time -p .venv/bin/contig report-diff /tmp/agent-D/report.json /tmp/agent-D/report-revised.json

# C5
/usr/bin/time -p .venv/bin/contig ask r1 "show me the provenance" \
  --runs-dir tests/fixtures/reporting/runs \
  --variants tests/fixtures/reporting/variants.json \
  --readiness tests/fixtures/reporting/readiness.json
# same command with --json

# C6
/usr/bin/time -p .venv/bin/contig ask r1 "is this run signed and how do I verify the signature?" \
  --runs-dir tests/fixtures/reporting/runs --json

# C7
printf '\n<!-- audit tamper test -->\n' >> /tmp/agent-D/report.html
/usr/bin/time -p .venv/bin/contig report-check /tmp/agent-D/report.json

# C8  (reviewer.statement changed; html_sha256 set to 64 zeros)
/usr/bin/time -p .venv/bin/contig report-check /tmp/agent-D/report-tampered.json

# C9
cd /tmp/agent-D && /usr/bin/time -p /Users/aliz/dev/at/contig/.venv/bin/contig report-check report.json

# C10  (variants.json edited, sidecar unchanged)
cd /tmp/agent-D/rc && /usr/bin/time -p /Users/aliz/dev/at/contig/.venv/bin/contig report-check report.json

# C11
/usr/bin/time -p .venv/bin/contig verify r1 --runs-dir tests/fixtures/reporting/runs

# C12
/usr/bin/time -p .venv/bin/contig verify r1
```

## Blockers

These did not stop the commands from running. They stop me from signing off on the report as audit evidence.

1. **The report artifact is not bound to its sidecar.** `report.json` records `html_sha256 = 92bde328…e61ef0e`, but `report-check` never recomputes it. After appending a comment to the HTML (new SHA `63f097df…02604a2`), `report-check` exited 0 with "All report inputs are current." A report can be modified after the check, or after it is sent, and Contig will not notice.
2. **The sidecar itself is editable and unsigned.** Changing `spec.reviewer.statement` and setting `html_sha256` to `000…0` still produced "All report inputs are current" and exit 0. `report-diff` only compares recorded values; it does not verify either sidecar against an HTML file or a signature. The reviewer attestation is plain text with no signer.
3. **Signature status is untraceable and self-contradictory.**
   - `ask` says `Signature: unsigned` but cites only `run_record.json` (`9634a7f0…e6e84d0`); that file has no signature field. The bundle has no `signature.json`. The statement is consistent with the file set, but no hashed field proves it.
   - The same citation's detail is `"Signed/reproducible run record"`; that exact string is also in the sidecar `inputs[0].note` and in the HTML provenance table, one row below `Signature | Unsigned`.
   - Neither the HTML nor `ask` explains *why* it is unsigned, whether a key was configured, what the signer would be, or how to sign/verify (`contig keygen`, `CONTIG_SIGNING_KEY`, `contig verify`). The `ask` confidence is `"high"`.
4. **Provenance stops at the derived JSON, not the raw evidence.** `report-check` hashes the three attached JSON files, but not what they in turn cite. Those files name `sample.vcf` with SHA-256 `aaaabbbbccccdddd` and `depth.tsv` with `eeeeffff00001111` — both 16 hex characters, neither a SHA-256, and neither file exists under `tests/fixtures/reporting/`. The HTML never mentions them. A ClinVar-reported `Pathogenic` row or a `GENE3` readiness claim is traceable to the M1/M2 JSON, but not to the VCF/depth/BED that produced it. (The placeholders are fixture data; the tool's silence about the broken upstream link is the finding.)
5. **A drifted run is presented as a normal report.** `run_record.json` declares one input (`samplesheet.csv`) and one output (`multiqc/multiqc_report.html`); neither file is present in the run bundle. `contig verify --runs-dir …` correctly exits 1 with `missing: multiqc/multiqc_report.html`; in the same state, `report-check` exits 0 and the report's provenance says only `Input checksums: 1` / `Output checksums: 1`. The docs say "Turn a verified run… into a report"; the report neither verifies outputs nor discloses that they were not verified.
6. **The repair chain is omitted.** The run record has a `repair_history` entry: OOM, root cause "STAR ran out of memory", patch `memory: 32 GB`, outcome `repaired`, `patch_applied: true`. The HTML contains no "repair", "OOM", or patch text. An auditor reading the report cannot know the run was self-healed; only opening `run_record.json` or `contig show` reveals it.

## Confusing output / docs gaps

1. `"Signed/reproducible run record"` is printed unconditionally for an unsigned record. This is the single most damaging label in the output: it appears in the sidecar, the HTML provenance table, and `ask --json`'s citation.
2. `report-check`'s "All report inputs are current." sounds like "the report is current and internally consistent." It only means the three JSON files still match their recorded hashes. It does not cover the HTML hash, run outputs, or the tables' own `meta.sources`.
3. `--template audit` is *less* informative than `publication`: it drops Summary, Methods, Variant evidence, and Coverage readiness, while the sidecar still says `Variant table attached: yes` / `Readiness table attached: yes`. Its provenance section is the same nine rows. "Audit" currently means "shorter", not "more auditable".
4. `ask`'s suggested actions do not preserve `--runs-dir`: `contig verify r1` and `contig methods r1` both exit 1 with `no bundled run 'r1' in runs` for the fixture bundle. Following the tool's own advice produces a misleading failure.
5. `report-diff` exits 0 whether the sidecars are identical or different; there is no `--fail-on-diff`. CI must parse `--json` and read `same`.
6. The sidecar is not portable: paths are stored exactly as passed and resolved against the current directory. With only the sidecar + HTML in `/tmp/agent-D`, `report-check report.json` reported all three inputs missing because the stored paths (`tests/fixtures/...`) are resolved against CWD. There is no `--base-dir` and no report export/bundle command. The sidecar also omits the exact invocation (`--runs-dir`, template override, `--out`/`--meta`), so a recipient cannot reconstruct how the HTML was produced.
7. `report-check` prints only `current`/`stale`/`missing`; it does not print the recomputed hash beside the recorded one, so a manual audit requires a separate `shasum -a 256`.
8. No output says that `sample.vcf`, `depth.tsv`, and the declared MultiQC output are absent. The report looks complete because the missing files are never named.

## Missing features

1. **Signed report manifest.** Sign the sidecar (and/or a manifest covering HTML + inputs) with the existing Ed25519 keypair, expose the signer key id/fingerprint, and have `report-check` verify the signature. Sign reviewer attestations too; plain JSON text is not an approval.
2. **`report-check --html` / `--outputs` / `--sources` / `--base-dir`.** Verify the recorded HTML hash, the run's declared outputs, and optionally recurse into `variants.meta.sources` / `readiness.meta.sources`. Print recorded vs computed for each.
3. **A real audit template.** Include the full run provenance: target backend/runtime, actual input and output checksum paths + values, Nextflow version, parameters, event log, repair history, resource usage, reference/annotation identity, container digests, and an explicit `verified | drifted | not checked` state.
4. **Portable report bundle.** Export HTML + sidecar + referenced inputs with a manifest and relative paths, or make the HTML a signed single-file artifact containing the inputs/hashes.
5. **Diff as a gate.** `report-diff --fail-on-diff` (or documented exit codes) plus a warning when a sidecar's `html_sha256` does not match the HTML on disk.
6. **`ask` citations per claim.** Each sentence (especially checksum counts and signature state) should carry its own path + SHA-256; a signature intent should explain `contig keygen` / `CONTIG_SIGNING_KEY` / `contig verify` instead of returning generic provenance. Suggested actions should preserve the run directory used for the answer.

## Quote

"The report tells me what Contig saw, not what it checked. I can change the HTML or the sidecar and `report-check` still says 'All report inputs are current.' That is not an audit trail."

## What I would do next

1. Do **not** circulate this report as audit evidence yet. Manually `shasum -a 256` every sidecar input and the HTML, and keep the exact directory layout if I need `report-check` to pass.
2. Ask the producing lab for a signed run bundle and the raw `sample.vcf` / `depth.tsv` / BED, then run `contig verify --runs-dir …` myself and compare. The current bundle fails that check on a missing output.
3. Put B1–B6 in front of engineering: artifact binding, signed sidecar, a truthful signature label and explanation, upstream-source verification, drift disclosure, and repair history.
4. Re-test only after those are fixed. If the output is unchanged, treat the report as a narrative summary for research discussion, not as provenance evidence for a regulated, clinical, or partner-facing decision.

Scope note: this is a synthetic fixture with placeholder hashes; B4 and B5 are partly artifacts of that construction. I did not test a signed run, a real lab bundle, `--llm`, or any clinical claim, and I changed nothing in the repo outside this report.

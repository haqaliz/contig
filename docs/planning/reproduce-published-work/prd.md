# PRD — Reproduce & verify published work (C8, first slice)

**Slug:** `reproduce-published-work`
**Branch:** `feat/reproduce-published-work/aliz`
**Capability:** C8 (`docs/technical/CAPABILITY_ROADMAP.md:1047-1097`) — first slice.
**Status:** Interview complete; pending prd-generator critique + review-gate approval.

---

## Problem Statement

Bioinformatics analyses in published papers almost never reproduce: of 27,271 biomedical-paper
notebooks only ~3.2% reproduced the original result (Samuel & Mietchen, *GigaScience* 2024);
Pimentel's 1.4M-notebook study finds ~4%; the best agent scores 21% on CORE-Bench even with
code+data *provided* (`CAPABILITY_ROADMAP.md:1056-1061`). CODECHECK proves the demand but does it
by hand. **No tool takes a third-party repo + its stated numeric claims and reports, per claim,
whether the computation actually regenerates them** — ending in a signed, re-runnable verdict.

Contig already has the Layer-2 engine (run → self-heal → verify → reproduce) for *first-party*
runs. C8 turns that same engine around to face *other people's* published analyses. This first
slice builds the **user-visible surface and the per-claim verdict contract** — the durable,
moat-relevant core — deferring the hard environment-resurrection piece to slice 2.

**Evidence it's real:** the reproducibility-crisis numbers above; CODECHECK's manual practice;
and Contig's own thesis (`CLAUDE.md`: the moat is execution/verification/reproducibility, and it
compounds an evaluation corpus). This is on-thesis Layer 2, not Layer 1.

## Goals & Success Metrics

- **G1 — A working `contig reproduce` surface.** `contig reproduce <repo> --run "<cmd>" --claims
  <file>` runs the repo's script and emits a per-claim verdict. *Measured:* the command exists,
  runs a synthetic repo, and prints per-claim results (CLI test).
- **G2 — Honest per-claim verdict.** Each claim resolves to exactly one of `REPRODUCED` /
  `WITHIN-TOLERANCE` / `DIVERGED` / `UNVERIFIED`, and `UNVERIFIED` is **never** rendered as
  reproduced. *Measured:* fixtures at each of the four outcomes assert the right label; an
  unresolved value (missing key / failed script) is `UNVERIFIED`, never a false pass.
- **G3 — Signed, re-runnable bundle.** A reproduce run writes a signed record (Ed25519 when
  `CONTIG_SIGNING_KEY` is set) plus a manifest sufficient to re-invoke it. *Measured:* the bundle
  round-trips through the existing `verify_signature`; a manifest test re-derives the invocation.
- **G4 — Zero new runtime dependencies, deterministic, no network.** *Measured:* `pyproject.toml`
  runtime deps unchanged; the whole suite runs offline with a scripted executor.

**Non-metric goal:** establish the `ReproduceRecord`/`ClaimResult` contract so slice 2
(env-resurrection) and later slices (paper-parsing, figures) extend it rather than reshape it.

## User Personas & Scenarios

- **A — lone computational biologist / reviewer.** Wants to check whether a paper's headline
  numbers regenerate from its repo before building on them. Runs `contig reproduce` against a
  cloned repo with a hand-written claims file; gets a per-claim verdict and a signed record to
  cite. Primary persona for this slice.
- **D — biotech researcher / core facility.** Wants a defensible, signed artifact recording
  which of a dependency-repo's numbers reproduced. Consumes the same bundle.
- (Community/viral channel — "I ran N papers, here's what reproduced" — is the GTM upside, not a
  slice-1 requirement.)

## Requirements

### Must-have (slice 1)

- **M1 — `contig reproduce` command.** Positional `repo` path (local dir); `--run "<cmd>"` (the
  command to execute inside the repo); `--claims <path>` (the claims file); `--results <path>`
  (default `results.json`, resolved relative to the repo — the JSON the script writes);
  `--runs-dir`/`--tolerance` options mirroring existing commands. Flat `@app.command()` in
  `cli.py`, mirroring `show`/`rerun`. Loads nothing from a prior run — it *creates* one.
- **M2 — Claims file.** JSON list of objects `{"id": str, "value": number, "tolerance"?: number}`;
  `tolerance` defaults to `0.1` (relative, matching `benchmark`'s default). Malformed file → a
  clear error and non-zero exit; an empty list → an honest "no claims" result, not a crash.
- **M3 — Execute the repo script.** Run `--run` inside the repo via the existing injectable
  `Executor` seam (`runner.py:566`), capturing exit code. On non-zero exit, **every claim for
  that run is `UNVERIFIED`** (the computation did not complete) — never `DIVERGED`, never a
  false pass. No env-resurrection this slice.
- **M4 — Bind regenerated values.** Read the repo's `results.json` (a `{claim_id: value}` map the
  script writes). For each claim: value present & numeric → compare; key absent / non-numeric /
  file missing → that claim is `UNVERIFIED`.
- **M5 — Per-claim comparator (reuse `_relative_delta`).** Reuse `benchmark._relative_delta`
  (`benchmark.py:195`) for the relative delta. Classification (tight-epsilon, per the interview):
  `|Δ| ≤ 1e-9` → `REPRODUCED`; else `rel_delta ≤ tolerance` → `WITHIN-TOLERANCE`; else →
  `DIVERGED`; uncomputable → `UNVERIFIED`. A `DIVERGED`/`WITHIN-TOLERANCE` result **names the
  observed-vs-stated values and the delta** in its message.
  **Boundary rules (pin these as acceptance criteria — this is where a false verdict slips in):**
  - **Non-finite** observed or claimed (`NaN`/`inf`) → `UNVERIFIED`, never `DIVERGED`.
  - **Claim value exactly 0:** `_relative_delta` falls back to absolute diff; `|Δ| ≤ 1e-9` still
    gates `REPRODUCED`; an observed `0` vs claimed `0` → `REPRODUCED`; a nonzero observed vs
    claimed `0` uses the absolute delta against `tolerance` (documented, not silently rel-vs-abs
    confused).
  - **Non-numeric** claim value in the claims file → reject the file (M2), not a per-claim
    UNVERIFIED. **Non-numeric** observed value in `results.json` → that claim `UNVERIFIED`.
  - **Duplicate claim ids** in the claims file → reject the file with a clear error (ambiguous).
  - **Extra keys** in `results.json` not named by any claim → ignored (not an error).
  - **Negative/zero tolerance** → reject the file.
- **M6 — `ClaimResult` model + a reduce.** New `ClaimStatus =
  Literal["reproduced","within_tolerance","diverged","unverified"]` and `ClaimResult`
  (id, status, claimed value, observed value|None, tolerance, delta|None, message). A pure
  `reduce_reproduction(results)` derives a one-line summary (counts per status); the honest
  reduction never upgrades unverified/diverged into reproduced. Model lives in `models.py`;
  logic in a new `verification/reproduce.py` (stdlib-only).
- **M7 — Signed, re-runnable bundle.** A new `ReproduceRecord` (repo id/path, run command,
  claims-source sha256, per-claim `ClaimResult` list, tool/interpreter provenance, created_at)
  written to a per-reproduction dir as `reproduce_record.json`, signed via the **existing generic**
  `signing.canonical_record_bytes`/`_maybe_write_signature` path (it is model-agnostic —
  `record.model_dump(mode="json")`), plus a small `reproduce.json` manifest (repo, command,
  claims path + hash) so the invocation is re-runnable. Reuse, do not fork, the signing code.
- **M8 — Render + exit code.** Human-readable per-claim table (id, status, stated, observed,
  delta) + the summary line. Exit `0` on a completed, well-formed invocation regardless of claim
  outcomes by default; an opt-in `--fail-on-diverged` (mirroring `--fail-on-verdict`, deferrable
  to should-have) exits non-zero when any claim `DIVERGED`. Malformed inputs / unrunnable command
  exit non-zero.

### Should-have

- **S1 — `--fail-on-diverged`** exit-code gate (opt-in; default exit unchanged), for CI use.
- **S2 — `contig show`-style rendering** of a stored reproduction by id (read-back), if cheap.

### Nice-to-have (explicitly later slices)

- Environment resurrection (ImportError → install → retry) — **slice 2**, mapped in
  `_card/understanding.md`.
- Paper-parsing to auto-extract claims (take an explicit claims file for now).
- Figure/plot and table-cell claims (blocked on a dependency decision — see Out of Scope).
- Folding reproduction outcomes into the C6 eval corpus.
- `contig reproduce <doi|url>` remote fetch; dashboard card.

## Technical Considerations

- **Reuse, don't rebuild.** Comparator = `benchmark._relative_delta`; execution = the `Executor`
  seam; signing/bundle = `write_bundle`/`_maybe_write_signature`/`signing.py` (generic over any
  pydantic record); verify = `_signature_status`. New code is thin: a CLI command, a
  `verification/reproduce.py`, and two small models.
- **New verdict vocabulary is not `QCStatus`.** `pass|warn|fail|unverified` (`models.py:55`) does
  not carry the exact-vs-within-tolerance distinction, and `QCResult` can't express it. Hence a
  dedicated `ClaimStatus`/`ClaimResult` rather than overloading the QC path. The `overall_verdict`
  reduction (`models.py:85`) is the *template* for `reduce_reproduction`, not a reuse.
- **Do not pollute `RunRecord`.** `RunRecord` is pipeline-shaped (pipeline/target/events/
  qc_results). A reproduce run is not an nf-core pipeline run; a separate `ReproduceRecord` keeps
  both models honest and still gets signing for free.
- **Reproducibility/verification impact:** this *is* a verification surface — it extends the
  signed-record guarantee to third-party reproduction. Honest-degradation (UNVERIFIED) is the
  load-bearing contract.
- **Determinism/CI:** no real repo, no network, no real installs. Tests use a scripted executor
  that writes a canned `results.json`, mirroring `tests/test_cli.py`'s `_fake_run_executor`.

## Data Model / Artifact Contracts

- **Claims file (input):** `[{"id": "mean_cov", "value": 30.4, "tolerance": 0.1}, …]` (JSON).
- **`results.json` (repo-produced):** `{"mean_cov": 30.4, "n_variants": 1204}` (JSON, flat
  claim-id → number).
- **`ClaimResult`:** `{id, status: ClaimStatus, claimed, observed|null, tolerance, delta|null,
  message}`.
- **`ReproduceRecord`:** `{reproduce_id, repo, run_command, claims_sha256, claim_results[],
  interpreter/tool provenance, created_at}` → `reproduce_record.json` (+ `signature.json`,
  `reproduce.json` manifest) under a per-reproduction dir.

## Risks & Open Questions

- **R1 — Bundle home & id scheme.** Where reproductions live (`runs/` vs a new `reproductions/`
  dir) and the id format — settle in tech-plan. Low risk; both reuse existing helpers.
- **R2 — `ReproduceRecord` vs `RunRecord` reuse.** PRD recommends a separate model; if tech-plan
  finds signing/bundle helpers too coupled to `RunRecord`, revisit. Mitigated by the dig: signing
  is generic over `model_dump`.
- **R3 — Re-runnability depth.** Slice-1 "re-runnable" = record the invocation (repo+cmd+claims
  hash) so it can be re-invoked; it does **not** pin the repo's own environment (that's slice 2 /
  C8's env-resurrection). State this honestly so "re-runnable" isn't over-claimed.
- **R4 — Scope creep toward paper-parsing/figures.** Guardrail: explicit claims file + scalar-only
  this slice (see Out of Scope). Flag if a requirement drifts into parsing prose or hashing images.

## Out of Scope (explicit)

- **Environment resurrection / dependency self-heal** — slice 2.
- **Paper/PDF parsing to extract claims** — take an explicit claims file.
- **Figure/plot claims and table-cell extraction.** Hard constraint, not a preference: no
  image-hashing exists in the repo and the runtime dep set is deliberately `pydantic`/`typer`/
  `cryptography` only (`pyproject.toml:30`); perceptual-image-hashing would break the
  no-new-dependency contract. Deferred until a deliberate dependency decision.
- **Any judgement on the paper's *conclusions*.** We report whether the *computation* reproduces
  the stated *numbers* — never whether the science is correct (`CAPABILITY_ROADMAP.md:1095`).
- **Remote fetch (`<doi|url>`), dashboard card, C6 eval fold-in** — later slices.

## Guardrail check (`CLAUDE.md`)

Layer 2 only (verify-and-reproduce; never NL→workflow authoring, never a conclusions verdict) ✅ ·
Moat = verification/reproducibility infra + corpus ✅ · Gets better as base models improve
(claim-extraction & env-resurrection in later slices) ✅ · Founder's edge / stdlib-only ✅ · No
raw-data egress (only hashes + claim diffs) ✅ · Test-first ✅.

---

## Areas to strengthen (self-critique — surfaced at the review gate)

**🟡 G1 — The `results.json` convention reproduces *cooperative* repos, not *uncooperative* ones.**
Requiring the third-party script to emit a Contig-shaped `results.json` means slice 1 works on
repos you modify (or your own synthetic fixtures), not the "uncooperative existing repo" the C8
roadmap emphasizes (`CAPABILITY_ROADMAP.md:1071`). *This is the right call for the walking
skeleton* (deterministic, zero parsing surface, ships the contract), but it is an honest
**limitation**, not a full C8. The deferred path to uncooperative repos is the claim-level
output-locator (interview option C: `{"from": "out/summary.json", "path": "$.coverage.mean"}`) —
name it as the planned slice-1.5 so we don't quietly imply slice 1 handles arbitrary repos.

**🟡 G2 — Success metrics are build-completion, not outcome.** G1–G4 assert "the capability
exists and is honest," which is correct for an infrastructure slice but is a *leading* signal, not
adoption. The one real go/no-go for investing in slice 2 (env-resurrection): **does running it
against ≥1 real cloned public repo with a hand-written claims file produce a sensible per-claim
verdict?** That manual smoke test (outside CI, no network gate) is the honest proof the surface is
worth extending — add it as a post-merge validation step, not a CI test.

**🟡 G3 — Comparator boundary correctness.** Addressed in M5's boundary rules above; called out
here because the tight-epsilon + zero-claim + non-finite interactions are the single most likely
place a *false* `REPRODUCED`/`DIVERGED` hides. TDD must write these boundary cases RED first.

**The question I'd want answered before greenlighting:** *If the honest answer for most real
uncooperative repos in slice 1 is `UNVERIFIED` (no `results.json`, unresolved env), is a
`contig reproduce` that mostly says "I couldn't check" still worth shipping now — or is the
first externally-credible slice actually skeleton + the output-locator (option C) together, so it
can read numbers out of repos as they already are?* This is the scope call that decides whether
slice 1 demos to a real repo or only to fixtures.

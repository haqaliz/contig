# PRD: Self-heal the rest of the single-file index family (`.bai` / `.tbi` / `.csi`)

**Slug:** `self-heal-index-family` · **Branch:** `feat/self-heal-index-family/aliz` ·
**Owner:** aliz
**Origin:** The explicitly-named follow-on of the just-shipped missing-index `.fai`
slice (capability **C2**, self-heal breadth). `docs/technical/CAPABILITY_ROADMAP.md:103-109`
lists "the rest of the missing-index family (`.bai`, `.tbi`/`.csi`, `.dict`, STAR/BWA)
… on the same seam" as deferred next; the `.fai` slice's own Out-of-Scope
(`docs/planning/self-heal-missing-index/prd.md:227`) names "a path-extension→command
table" as the natural extension point. Selected by `contig-next` as the highest-leverage
unblocked feature after the `.fai` slice closed.

---

## Problem Statement

Contig's self-heal can now build a missing **FASTA `.fai`** index and retry, but a
missing **BAM index (`.bai`)**, **tabix VCF index (`.tbi`)**, or **CSI VCF index
(`.csi`)** still ends in an honest FAIL that a human must fix by hand — even though:

- **Detection already covers them.** `detect.py:168` classifies a "not found / missing /
  no such file" line mentioning any of `.fai .bai .tbi .csi` as
  `failure_class="missing_index"` (confidence 0.85). So the engine already *sees* these
  failures; it just can't *act* on them.
- **The repair proposal is already index-agnostic.** `repair.py:56-65` proposes
  `Patch(kind="reference", operation={"build_index": True}, risk="needs_confirmation")`
  for any `missing_index` — no extension is hard-wired.
- **The build machinery exists.** The injectable `IndexBuilder` seam (`runner.py:77`,
  `default_index_builder` at `:107-117`), the gated apply-and-build helper
  (`_apply_patch_and_maybe_build`, `self_heal.py:367-414`), and the honest outcome
  vocabulary (`built_index_and_retried` / `index_build_failed` / `index_unresolvable`)
  are all in place.

The only thing `.fai`-specific — and therefore the only gap — is **three functions**:
the token regex (`self_heal.py:55`), the parse (`_parse_missing_fai`, `:58-68`), and
the command builder (`_fai_build_command`, `:71-78`). They hard-code `.fai` →
`samtools faidx`. A `.bai`/`.tbi`/`.csi` failure parses to `None` (regex misses) →
`index_unresolvable` → honest FAIL, no recovery.

**Evidence it's real.** `missing_index` is a modeled `FailureClass` with a detector rule,
test, and golden corpus case (`detector_corpus.jsonl`). `.bai`/`.tbi`/`.csi` are
everyday index artifacts in nf-core germline/variant flows. Unattended-completion rate
is the Phase-1 headline reliability metric (`CAPABILITY_ROADMAP.md:116-117`); incumbents
do mechanical resubmit only — none builds the missing artifact and retries
(`FEATURES.md` competitive scan).

---

## Goals & Success Metrics

| Goal | Measure |
|---|---|
| A missing `.bai`/`.tbi`/`.csi` is recovered autonomously | For each kind, a test injecting "fail with missing index, then succeed once it exists" heals to a PASS/WARN verdict with no human step (auto-approve), via the injected builder fake. |
| The right tool is invoked per kind | Argv assertions: `.bai` → `["samtools","index","<x.bam>"]`; `.tbi` → `["tabix","-p","vcf","<x.vcf.gz>"]`; `.csi` → `["bcftools","index","<x.vcf.gz>"]`. |
| Each build is a real, auditable repair step | `repair_history` records a `RepairStep` with `outcome="built_index_and_retried"`, the diagnosis, and the patch; appended to `repair_progress.jsonl`. |
| A failed build gives up honestly | A non-zero builder result yields `index_build_failed` (detail naming the index path) + an honest FAIL — never a false PASS; the case is still captured to the pending corpus. |
| CI stays tool-free and deterministic | All tests inject a fake `IndexBuilder` and the existing fake `Executor`; no real samtools/tabix/bcftools/Nextflow/network runs. |
| The corpus compounds (moat #2) | One golden `missing_index` case per new kind (`.bai`, `.tbi`, `.csi`) is seeded into `src/contig/data/detector_corpus.jsonl`; the detector eval stays green. |

This is reliability/quality hardening, not a growth metric; success is the tests above
passing and the existing self-heal/detector suites staying green.

---

## User Personas & Scenarios

- **Persona A (lone computational biologist)** runs a germline analysis unattended
  overnight. A variant step fails because the bgzipped VCF has no `.tbi`. Contig
  diagnoses `missing_index`, runs `tabix -p vcf calls.vcf.gz`, retries, and the morning
  verdict shows the "built the index, then re-ran" chain instead of a dead run.
- **Persona A, the hard case:** the build itself fails (e.g. the VCF is not actually
  bgzipped). Contig reports "Building the index for calls.vcf.gz.tbi failed (exit N)"
  and stops with an honest FAIL — the biologist knows exactly what broke.
- **Core facility (C):** wants throughput and auditable recovery; the built-index repair
  step in the provenance trail is exactly the evidence a non-expert PI can trust.

---

## Requirements

### Must-have

- **M1 — Extension-dispatched index build.** On a `missing_index` diagnosis whose
  `build_index` patch is applied, the loop derives the missing index path **and its
  kind** from `diagnosis.evidence`, builds it with the kind-appropriate command, and
  retries the same pipeline argv. Scope: `.fai` (unchanged), `.bai`, `.tbi`, `.csi`.
- **M2 — The path→command table.** A single source-of-truth mapping from extension to
  (source-derivation, build-argv):
  - `.fai` → strip `.fai` → `<fasta>`; `["samtools","faidx","<fasta>"]` (unchanged).
  - `.bai` → strip `.bai` → `<x.bam>`; `["samtools","index","<x.bam>"]`.
  - `.tbi` → strip `.tbi` → `<x.vcf.gz>`; `["tabix","-p","vcf","<x.vcf.gz>"]` (emit
    `-p` and `vcf` as **separate** tokens — the canonical form the argv assertion pins).
  - `.csi` → strip `.csi` → `<x.vcf.gz>`; `["bcftools","index","<x.vcf.gz>"]`.
- **M3 — Generalize the three `.fai`-specific functions, preserving structure.**
  - The token regex (`self_heal.py:55`) matches any supported extension (longest-match
    so `ref.fasta.fai` is not truncated; same lookahead discipline pinning the token end).
  - `_parse_missing_fai` → a general parser that returns the path **and** the matched
    extension (or `None`), so the build can dispatch. Pure, no I/O.
  - `_fai_build_command` → a general command builder keyed by extension, table-driven.
  - `_apply_patch_and_maybe_build` (`:396`, `:405`, `:411`) consumes the generalized
    parse/build; the `.fai`-only detail strings generalize to name the actual index.
- **M4 — No regression of the `.fai` behavior or the seam contract.** The
  `IndexBuilder` seam, `self_heal_run(index_builder=…)` parameter, the gated
  apply-and-build flow (every gated-apply site, M4a of the prior slice), and all four
  existing `.fai` tests stay green unchanged (or updated only for renamed internals).
- **M5 — Honest outcome vocabulary (unchanged values).** Success →
  `built_index_and_retried` and retry; non-zero build → `index_build_failed` + detail
  naming the index + finalize FAIL (no further retry); unparseable path →
  `index_unresolvable` + finalize FAIL. Never a false PASS. No new outcome strings
  needed.
- **M6 — Bounded.** Reuse the existing `max_attempts`; at most one build per missing
  index path, so a build that "succeeds" but leaves the failure unresolved cannot loop
  the builder.
- **M7 — Corpus seed per kind.** One golden `missing_index` `FailureCase` for each of
  `.bai`, `.tbi`, `.csi` (realistic log signature per tool) added to
  `detector_corpus.jsonl`; the detector eval stays green.

### Should-have

- **S1 — Robust, deterministic path parsing.** Handle absolute and relative evidence
  paths. Selection rule when several tokens appear: scan `diagnosis.evidence` lines in
  order, return the **first** supported-index token found; within a single line, prefer
  the **longest** matching extension so `ref.fasta.fai` is not truncated and a line
  naming both a `.bam` and its `.bai` resolves to the `.bai` (the actual missing index).
  If no supported token parses, give up honestly (`index_unresolvable`), never guess a
  build target. Cover the multi-token line with a test.
- **S2 — The `expected_signal` ("index present") reads coherently** in the recorded step
  so the chain reads as detect→build→retry regardless of kind.

### Nice-to-have (explicitly deferred — see Out of Scope)

- `.dict` (sequence dictionary): needs a `detect.py` keyword addition AND a non-trivial
  source-FASTA resolution (`ref.dict` ↔ `ref.fasta`/`ref.fa`). Its own follow-on slice.
- BAM/CRAM `.csi` (`samtools index -c`): `.csi` maps to the VCF case only this slice.
- STAR/BWA directory indexes (multi-file/dir shape, not a single parsed path).
- Pipeline-regenerate (config-mutation) route; stale-index detection.

---

## Technical Considerations

**Insertion point (unchanged from the `.fai` slice).** The build is invoked from
`_apply_patch_and_maybe_build` (`self_heal.py:367-414`) at the gated-apply sites; only
the parse/dispatch/command internals change. `apply_patch` stays pure.

**The table is the design.** Encode the mapping as one table
(`{ext: (derive_source_fn_or_suffix, build_argv_fn)}`) so adding `.dict` or BAM-`.csi`
later is a one-row change — this is precisely the "path-extension→command table"
extension point the prior PRD named.

**Source derivation per kind.** `.fai`/`.bai`/`.tbi`/`.csi` all derive their source by
stripping exactly the trailing index suffix (`x.bam.bai`→`x.bam`, `x.vcf.gz.tbi`→
`x.vcf.gz`, `x.vcf.gz.csi`→`x.vcf.gz`). This holds for the standard
`<data-file>.<index-ext>` convention nf-core emits; the rarer bare-sibling forms
(`x.bai` without `.bam`) are out of scope and will simply fail to find their source →
the build fails honestly, never a false pass.

**Detector needs no change.** `.bai`/`.tbi`/`.csi` are already in the `detect.py:168`
keyword set; this slice touches `detect.py` only if `.dict` were in scope (it is not).

**Reproducibility/verification impact.** No change to verdict-reduction guarantees: an
unrecovered run is FAIL; the near-zero false-pass guarantee is preserved. Each build is
recorded in `repair_history` and the bundle, strengthening the auditable trail. No
raw-read egress — builds run on the user's compute through the injected seam.

**Testing.** Strict TDD mirroring `tests/test_self_heal.py:1047-1147`. Parameterize the
`_building_builder` fake by the index filename it creates and the expected argv, then add
per-kind build-and-retry + exact-argv tests, plus a failed-build and an unparseable-path
test that still exercise the generalized path. Keep the four `.fai` tests green.
**RED baseline first:** before generalizing, write a test proving a `.bai` (or `.tbi`)
missing-index failure does NOT recover today (parses to `None` → `index_unresolvable`),
so the GREEN step demonstrably changes behavior rather than only adding untested paths.

---

## Data Model / Contracts

- **No model change.** `RepairStep.outcome` stays a free `str` reusing the three existing
  values; `Patch`, `FailureClass`, `apply_patch`'s return contract, and the
  `IndexBuilder` seam type are unchanged.
- **Internal renames** (`_parse_missing_fai`→`_parse_missing_index`,
  `_fai_build_command`→`_index_build_command`, `_FAI_TOKEN_RE`→a general token regex,
  local `fai`→`index_path`) are internal-only; no public surface change.
- **Corpus** gains three `FailureCase` rows with `expected_class="missing_index"`
  (`models.py:314-323`) in `src/contig/data/detector_corpus.jsonl`.

---

## Risks & Open Questions

- **R1 — Evidence-line variety per tool.** `samtools index`, `tabix`, and `bcftools`
  print different "missing index" messages. The token regex keys on the *file extension*,
  not the tool wording, so it is robust to phrasing — but each corpus seed must use a
  realistic line. Cover each kind with a parse test.
- **R2 — Source-derivation edge cases.** The bare-sibling `.bai`/`.csi` forms (index not
  named `<data>.<ext>`) derive a non-existent source and fail the build honestly. Accepted
  this slice; documented as out of scope.
- **R3 — `.csi` ambiguity.** `.csi` indexes both VCF (bcftools) and BAM (`samtools index
  -c`). Decision: map to the VCF case only; BAM-`.csi` is out of scope and would
  build the wrong artifact for a BAM source — acceptable because a wrong build that
  doesn't resolve the failure still terminates honestly within `max_attempts`.
- **R4 — Re-proposal loop.** A build returning 0 that doesn't resolve the failure must not
  re-trigger indefinitely: at most one build per index path + the `max_attempts` bound.
  Cover with a termination test.
- **R5 — Dashboard surface.** Rendering the outcomes is out of scope (data lands in
  `repair_history`/JSONL), matching the `.fai` slice.

### Challenge (pressure-test, for eyes-open approval)

- *What if we don't build this?* Three common index failures keep dead-ending in manual
  fixes, capping unattended-completion exactly where the moat metric is measured.
- *Why is this low-risk?* The whole machine shipped with `.fai`; this is a three-function
  generalization plus a table and per-kind tests — depth-first, no new architecture.
- *What are we NOT building by doing this?* `.dict`, BAM-`.csi`, STAR/BWA dir indexes,
  and the wider C2 catalog (format/reference-mismatch/pin) — all explicitly deferred.

---

## Out of Scope (explicit)

- **`.dict`** (needs a `detect.py` change + non-trivial FASTA resolution) — own follow-on.
- **BAM/CRAM `.csi`** (`samtools index -c`) — `.csi` is VCF-only this slice.
- **STAR/BWA directory indexes** — multi-file/dir shape, not a single parsed path.
- **Pipeline-regenerate (config-mutation) route** for self-buildable indexes.
- **Stale-index detection** (present-but-older-than-source); `detect.py`'s rule unchanged.
- **Risk-tier change** for the `build_index` patch (stays `needs_confirmation`).
- **Dashboard rendering** of the outcomes.

---

## Guardrails check (CLAUDE.md)

Layer 2 only (run + self-heal); no Layer-1 workflow authoring. No raw-read egress — the
index build runs on the user's compute through the injected seam. Self-heal stays bounded
(`max_attempts`) and logged. Gets better as base models improve — a smarter diagnoser
still flows through the same bounded build-and-retry. Test-first; no real
tool/Nextflow execution in tests.

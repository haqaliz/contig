# PRD: somatic empty-call-set FAIL floor (+ declining the rest, by decision)

- **Capability:** C4 follow-on (somatic assay) / C3 follow-on (biological-plausibility FAIL
  severity — the deferral named in `germline-plausibility-fail-severity/prd.md:120-121`).
- **Branch:** `feat/sibling-plausibility-fail-severity/aliz`
- **Slug:** `somatic-empty-callset-fail` (deliberately narrower than the branch name — see
  *Scope decision*).
- **Source:** `docs/planning/_card/issue.md` (brief) + `docs/planning/_card/understanding.md`
  (Phase 2 dig, four parallel agents).

---

## Problem Statement

**v0.36.0 gave the verdict teeth, but only germline can bite.**

`contig run`/`verify --fail-on-verdict` (v0.36.0) makes a reduced **FAIL** verdict exit `1`, so a
researcher can finally gate a shell script or CI step on Contig's verified verdict. But germline
`variant_calling` is the **only** assay whose *biological* plausibility can produce a FAIL: the
germline slice (v0.35.0) shipped gross-implausibility bands on `ts_tv_ratio`, `het_hom_ratio`, and
`variant_count`, while every sibling plausibility pack stayed WARN-only
(`germline-plausibility-fail-severity/prd.md:120-121`).

Concretely: **a somatic (tumor–normal) run that produces an empty call set today renders WARN and
exits `0` even under `--fail-on-verdict`.** A truncated or crashed Mutect2 step that yields a
0-record VCF is indistinguishable, at the exit code, from a healthy run. The germline equivalent
of that exact failure FAILs (`rule_pack.py:84-90`).

**Evidence it's real:**
- `somatic_variant_count` carries `warn_below: 10`, `warn_above: 100000`, **no `fail_*`**
  (`rule_pack.py:318-325`) — structurally identical to germline `variant_count` minus the floor.
- The deferral is named, not accidental: *"FAIL severity for the somatic, RNA-seq,
  RNA-seq-composition, and annotation plausibility packs — they stay WARN-only"*
  (`germline-plausibility-fail-severity/prd.md:120-121`); *"FAIL severity for any somatic
  plausibility check (deferred until bands calibrated)"* (`somatic-vaf-plausibility/prd.md:194`).

**Who has the problem:** the somatic-assay user wiring Contig into automation — Contig's ICP core
facility or biotech running tumor–normal cohorts, where nobody reads a WARN in a log tail.

---

## Scope decision (the honest finding, decided with the user)

The brief proposed FAIL severity across three packs. **The Phase 2 dig reduced it to one line**, and
the user confirmed that scope. This PRD documents both halves:

1. **Ship:** `fail_below: 1` on `somatic_variant_count` — the empty-call-set floor.
2. **Decline, by decision (not deferral):** FAIL bands on the somatic VAF metrics and every RNA-seq
   plausibility/composition metric. The dig proved these are **not** waiting on calibration; they
   are structurally impossible to do honestly. That reasoning is recorded so the item stops being
   re-picked.

The second half is the more durable output: the "FAIL deferred until calibrated" line has now been
re-deferred across the germline (v0.3.0), RNA-seq (v0.6.0), somatic-VAF, composition, and
variant-count slices. This PRD retires it.

---

## Goals & Success Metrics

| Goal | Measure |
|---|---|
| A somatic run with an empty call set FAILs the verdict | `evaluate_somatic_plausibility` on a 0-record VCF → `somatic_variant_count:<t>` `status == "fail"`; `overall_verdict(results) == "fail"` |
| No false FAIL on a legitimate low-count somatic run | A 5-record call set stays `warn`; a 5000-record set stays `pass` |
| No false FAIL on legitimate low-purity/subclonal science | `median_vaf` / `strelka_median_vaf` extremes remain `!= "fail"` — the existing WARN-cap tests **stay green** |
| UNVERIFIED is never converted to FAIL | An uncomputable `median_vaf` stays `unverified`; a real `0` count is `fail` **and explicitly `!= "unverified"`** |
| The declined items stop being re-picked | `/contig-next` reading `CAPABILITY_ROADMAP.md` sees "declined by design", not "pending calibration" |

**Non-metric:** this slice changes no default exit code. It only makes an existing opt-in flag
reach one more real failure.

---

## Requirements

### Must-have

- **M1 — The floor.** Add `"fail_below": 1` to the `somatic_variant_count` rule
  (`rule_pack.py:318-325`). Keep `warn_below: 10` and `warn_above: 100000` **unchanged**.
- **M2 — No `fail_above`.** Mirror germline's explicit decision (`rule_pack.py:77-83`): the
  `100000` ceiling stays a **soft, uncalibrated WARN tripwire**, never a validated ceiling. A
  hypermutator (MSI-high, POLE-mutant) or a WGS tumor legitimately exceeds it.
- **M3 — Nothing else gains a band.** `median_vaf`, `strelka_median_vaf`, `pon_applied`, and every
  RNA-seq plausibility/composition rule are untouched.
- **M4 — Record the will-not-do in three places** (user-confirmed):
  - **Pack docstrings** (`rule_pack.py:302,311,329` and the RNA-seq pack headers `:280-284`,
    `:375-378`): rewrite "WARN-capped … uncalibrated … FAIL deferred" → "WARN-capped **by
    decision**", naming the structural reason.
  - **`CAPABILITY_ROADMAP.md`** (C3 + C4 lines): the file `/contig-next` actually ranks from.
  - **`CHANGELOG.md`**: the shipped floor + the declined-by-design decision and its reasoning.
- **M5 — Test-first (RED→GREEN).** `test_variant_count_out_of_band_warns`
  (`test_somatic_plausibility.py:246-256`) is the RED: it currently asserts the WARN cap and must
  be inverted for the 0 case with a why-comment citing this PRD.

### Should-have

- **S1 — Band-ordering invariant.** Add `test_somatic_bands_are_well_ordered` mirroring
  `test_germline_bands_are_well_ordered` (`test_rule_pack.py:196-206`): for every somatic rule the
  present bounds must satisfy `fail_below <= warn_below <= warn_above <= fail_above`.
- **S2 — A `fail_below`-only declaration test** mirroring `test_variant_count_has_fail_below_only`
  (`test_rule_pack.py:186-192`): assert `fail_below == 1` **and `"fail_above" not in rule`**, so M2
  is enforced by a test rather than a comment.
- **S3 — A WARN-cap guarantee test for the VAF metrics.** The absence of VAF fail bands is now a
  deliberate promise; assert it declaratively (the somatic pack has no `no_fail_keys` guard test
  today — only behavioral WARN assertions).

### Nice-to-have

- **N1 —** A `heal-guard`/corpus case for a truncated somatic run. Out of scope; no failure-class
  change here.

---

## Technical Considerations

**It is a pure data edit — verified, not assumed.**

- `_status_for` (`rule_pack.py:447-466`) reads all four band keys via `.get()`; the docstring
  (`:450-452`) states any subset is legal. **The WARN cap exists *only* because the `fail_*` keys
  are absent — no code clamps FAIL→WARN anywhere** (agent grepped `verification/`, `runner.py`,
  `models.py`; every hit is a hand-built check or a docstring).
- `evaluate_somatic_plausibility` (`somatic_plausibility.py:252`) passes status straight through
  the shared `evaluate()`; its only post-processing is the `None`→`unverified` loop (`:254-276`).
- `overall_verdict` (`models.py:78-96`): a single `fail` dominates. `RunRecord.verdict`
  (`models.py:358-369`) consumes it; `--fail-on-verdict` then exits `1`.

**The floor provably fires** (the property the whole slice rests on): `count` is initialized to `0`
(`somatic_plausibility.py:133`) and incremented at `:155` — **before** the tumor-column guard at
`:156` — so it is always a real `int`, independent of tumor identification. The `computable` filter
is `if value is not None` (`:248-250`), so **`0` survives into `evaluate()` and rides the band**
rather than routing to UNVERIFIED. The docstring already asserts this (`:233-234`): *"variant_count
is always an int, so it is always computable."*

**Verification/reproducibility impact:** none beyond the verdict itself. No new model field, no
`FailureClass`, no provenance change, no signature/reproduce-bundle contract change, no dashboard
card. `record.verdict` is a serialized `@computed_field`, so a re-verified older bundle re-reduces
under the new band — acceptable and consistent with how v0.35.0 shipped.

**Test conventions** (`understanding.md` §5): `uv run pytest`; flat `tests/` + `tests/verification/`;
**no `conftest.py` anywhere** — each file defines local helpers; real files via `tmp_path`, never
mocks; every non-obvious test opens with a 2-4 line why-comment citing a requirement id. Extend the
existing inline tumor–normal VCF helpers at `test_somatic_plausibility.py:22-40`.

**Out of the test scope:** a CLI exit-code test. `--fail-on-verdict` is already proven generically
against `QCResult(status="fail")` (`test_cli.py:217+`); the check that produced the fail is
irrelevant to the gate. The germline slice shipped **zero** CLI tests (commit `69b6385`: 4 files,
2 source + 2 test).

---

## Risks & Open Questions

- **R1 — A legitimate somatic zero (accepted, eyes open).** A small hotspot/targeted panel on a
  tumor with no mutation in the assayed regions genuinely calls zero; the engine has no target-type
  signal (inherited R3, `somatic-vaf-plausibility/prd.md:174-177`, whose mitigation says *"revisit
  when target-type is known to the engine"*).
  *Accepted because:* (a) the escalation is the **narrowest possible** — `warn_below: 10` already
  WARNs on near-zero, so `fail_below: 1` moves **only the exactly-zero case**; 1-9 records stay
  WARN, unchanged. (b) sarek's Mutect2 emits unfiltered-plus-FILTER-annotated records and the count
  is **not** PASS-filtered (`somatic_plausibility.py:81-83,155`), so a genuinely 0-record VCF from a
  real run is a truncation/crash artifact, not a biological result. (c) `--fail-on-verdict` is
  opt-in, so the blast radius is callers who asked for teeth.
  *Revisit trigger:* the first real-world report of a legitimate 0-call panel FAILing.
- **R2 — Re-verifying an old bundle can flip WARN→FAIL, which invalidates its signature.**
  A previously-WARN empty somatic call set re-reduces to FAIL. The verdict flip is the intended
  correction (same as v0.35.0) and only reaches an exit code under the opt-in flag — **but it also
  breaks the bundle's Ed25519 signature**, which is a sharper consequence than "the report reads
  differently."
  *Verified, not assumed:* `canonical_record_bytes` is `record.model_dump(mode="json")`
  (`signing.py:63-64`), and pydantic serializes `@computed_field`, so **`verdict` is inside the
  signed payload** — confirmed empirically (a synthetic WARN record canonicalizes to
  `"verdict":"warn"`). Re-signing/verifying an affected old bundle recomputes `verdict` from the
  stored `qc_results` under the new band, producing different canonical bytes → `verify_signature`
  returns `False` → `contig verify` reports a signature mismatch.
  *Accepted because:* (a) the blast radius is **only** bundles whose verdict actually changes —
  i.e. somatic runs with an empty call set, which are broken runs by definition; every other bundle
  canonicalizes identically. (b) It is a **pre-existing property of any rule-pack edit**, inherited
  unchanged from v0.35.0, which shipped germline FAIL bands with the same characteristic and did
  not treat it as a blocker. (c) Contig is pre-1.0 and signing is opt-in.
  *Required by this PRD:* state this in the CHANGELOG entry (M4) so a signing user is not
  surprised. Do **not** attempt to exclude `verdict` from the canonical payload here — that is a
  cross-cutting signature-contract change and would be its own slice.
- **R3 — The slice is one line.** Accepted: the durable half is M4 (retiring a five-times-deferred
  roadmap item with a proven reason).
- **R4 — The failure mode is hypothesized, not observed.** The somatic assay has **never been
  exercised against real data**: its verification "runs against injected fixtures"
  (`CAPABILITY_ROADMAP.md`, C4 VAF slice), no real nf-core/sarek run happens in CI, and there is no
  somatic corpus case and no field report of an empty somatic call set. So this floor catches a
  failure that is *reasoned* (a truncated/crashed Mutect2 step yields 0 records) rather than *seen*.
  *Accepted because* the germline sibling is the existence proof that the same failure is real on
  a real assay, and the cost is one line. *But it is why the success metrics below are all test
  assertions rather than field signal* — this slice cannot claim a measured improvement.

**Resolved by the dig, recorded so they are not re-litigated:**
- *Why no VAF floor?* Germline Ti/Tv has a physically constrained expectation (~2.0 WGS, ~3.0-3.3
  WES) with noise at a distinguishable ~0.5. **Tumor VAF has no such structure** — its expected
  value is a function of purity and clonality, which the code never observes (no purity, ploidy,
  copy-number, or target type). A low median VAF is legitimate science. Any `fail_below` FAILs a
  real low-purity sample.
- *Why no `fail_above: 1.0` on `strelka_median_vaf`?* It is **arithmetically bounded to [0,1] by
  construction** (`strelka_vaf.py:95-98,121-124` reject `denom <= 0`) — the band is **provably dead
  code**.
- *Why no band on `pon_applied`?* Not a numeric metric: a 3-state string emitted with `value=None`
  (`somatic_plausibility.py:199-221,279-287`) that never enters `evaluate()`; `_status_for` would
  `TypeError`. And PON absence is a legitimate configuration Contig itself does not wire.
- *Why no RNA-seq bands?* Two independent blockers. **Biology:** every metric has a legitimate
  protocol at the extreme (deep/high-input → 90%+ duplication; total-RNA/ribo-depletion → high
  rRNA; nuclear/FFPE/3' → intron-dominated; non-model annotation → high unassigned) — "extreme" and
  "unusual protocol" are the same number. **Engineering:** `percent_duplication`/`percent_rRNA`
  (`rule_pack.py:288,294`, both commented "slug unverified") are **absent from the repo's only
  real-shaped MultiQC** (`demo/sample-run/results/multiqc/multiqc_data.json` has only
  `uniquely_mapped_percent`, `percent_assigned`, `total_reads`) — FAIL severity on code that has
  never once fired.

**Surfaced for a future slice (not this one):** `RNASEQ_PLAUSIBILITY_PACK` is a **silent no-op on
every real rnaseq run** — the same defect class as the single-cell pack fixed in the C3 ingestion
slice (`CAPABILITY_ROADMAP.md:482-497`). There is also a live unit ambiguity: the pack declares
0-100 (`rule_pack.py:283-284`) while Picard's native `PERCENT_DUPLICATION` is a 0-1 fraction and
`qc_ingest.py:5-23` does a bare `float()` with no normalization. **This is the recommended next
`/contig-next` candidate** and is likely higher user value than any FAIL band.

---

## Out of Scope

- FAIL severity for `median_vaf`, `strelka_median_vaf`, `pon_applied` — **declined by design**
  (above), not deferred.
- FAIL severity for `RNASEQ_PLAUSIBILITY_PACK` and `RNASEQ_COMPOSITION_PACK` — **declined by
  design**, not deferred.
- FAIL severity for `ANNOTATION_PLAUSIBILITY_PACK` — separate C7 M-track with its own deferral
  trail; untouched.
- The sex-check axis (`sex_plausibility`) — hand-built from scalar constants
  (`rule_pack.py:417-426`), not a rule pack; unbandable by a data edit.
- Fixing the dormant RNA-seq slugs / the 0-1 vs 0-100 unit ambiguity — a different unit of work
  (see above).
- Capture-type-aware (WGS/WES/panel) bands — Contig does not persist capture type; this is what
  would properly resolve R1.
- Any CLI/exit-code change: `--fail-on-verdict` (v0.36.0) already exists and is untouched.
- Any new `FailureClass`, corpus case, provenance record, or dashboard card.

---

## Guardrail check (`CLAUDE.md`)

- **Layer 2 only** — the verify axis. On-thesis; no NL→workflow surface. ✅
- **No over-claiming** — the floor is an engineering tripwire ("an empty call set is a broken run"),
  the same tier as `mean_coverage fail_below`; **not** a biological or clinical claim. This slice
  actively *refuses* the bands that would have over-claimed. ✅
- **UNVERIFIED never becomes FAIL / never renders as PASS** — preserved, and named in a test. ✅
- **Founder's edge** — no wet-lab/clinical credential, no proprietary dataset, no real cohort
  needed. ✅
- **Test-first**, no new dependency, no raw-read egress, no real nf-core/sarek run in CI. ✅

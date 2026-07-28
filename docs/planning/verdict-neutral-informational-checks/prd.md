# PRD: Verdict-neutral informational checks

- **Slug:** `verdict-neutral-informational-checks`
- **Branch:** `feat/verdict-neutral-informational-checks/aliz`
- **Capability:** C3 (biological-plausibility verification) follow-on; changes the shared
  verdict reducer traversed by all seven wired assays.
- **Source:** `docs/planning/_card/issue.md` (inline brief); dig in
  `docs/planning/_card/understanding.md`.

---

## Problem Statement

**A Contig `pass` can currently mean nothing was verified.**

A QC rule with no bounds is structurally incapable of any status other than `pass`:
`_status_for` (`rule_pack.py:534-553`) reads each bound with `.get()` and falls through
every guard to `return "pass"`. Three further checks are hardcoded to always pass. Those
passes then enter `overall_verdict` (`models.py:78-96`) at full severity, where `pass`
outranks `unverified` — so **one check that asserts nothing is enough to turn a run that
verified nothing into a `pass`.**

The codebase already *claims* the opposite in prose. `count_concordance.py:328` describes
`gene_overlap` as *"informational context, **not a verdict lever**"*; `sex_plausibility.py:297`
names an *"informational-always-PASS convention"*. Both statements are false today: those
results are verdict levers. This work makes the code true to its own docstrings.

**Who has the problem.** The Contig ICP — the lone computational biologist, the wet-lab
scientist who can't code, the core facility running many samples — reads the verdict as the
product's headline claim. PRODUCT_SPEC sets the false-pass rate target at ~0. A `pass` that
can be produced by checks which assert nothing is a false pass by construction.

**Evidence it's real.**
- The mechanism is confirmed end-to-end in code (above).
- `CAPABILITY_ROADMAP.md:654-664` names it *"the strongest follow-on candidate here"* and
  sets a deadline: *"Decide before a second band-less rule lands."*
- **The dig found the deadline is already missed by three.** The roadmap counted only the
  band-less-config mechanism and undercounted its own problem (see Requirements R2).
- A **live, user-visible instance ships today** in the dashboard (see R5).

**Honest scope of the pain.** This is **not a regression** and no design partner has
reported it. The case for building is not a live incident but the integrity of the
product's cardinal claim — plus the dashboard bug in R5, which *is* live and visible.

### ⚠️ The roadmap's motivating example does NOT flip — verified

The roadmap's headline scenario is *"a report carrying only `PERCENT_DUPLICATION`
therefore reduces to verdict `pass` with nothing biological actually verified."*
**This slice will not change that run's verdict, and the PRD must not claim it does.**

`evaluate_run_qc` is called with `cross_sample=(assay == "rnaseq")` (`runner.py:276`), and
`evaluate_cross_sample` (`cross_sample.py:108-119`) **unconditionally** emits
`min_sample_count` (`cross_sample.py:113`). That check is asserting, not informational — it
`fail`s below `min_samples` and otherwise passes (`cross_sample.py:61-73`). It therefore
survives R3's filter, `"pass"` remains in `severe`, and the run still reduces to `pass`.

The roadmap half-knew this — its own parenthetical says *"(that scenario already reduced to
`pass` via `min_sample_count`)"* — but it stated the defect in terms of an example its own
caveat neutralises.

**Where the fix DOES bite:** `cross_sample` is **RNA-seq only**, so the other six wired
assays have no `min_sample_count` floor. A germline run whose only evidence is
`x_het_ratio`, or a single-cell run whose only evidence is `gene_overlap`, genuinely flips
`pass → unverified`. That is the real, narrower value of this slice.

**Consequence for scoping.** The honest headline is *"a `pass` must be backed by at least
one check that could have failed"* — not *"the duplication-only RNA-seq run stops
passing."* Whether `min_sample_count` ("≥2 samples exist") should itself count as evidence
that a **biological** result was verified is a **real open question this PRD does not
settle** (see Open Questions #5). It can fail, so it is not informational under R1's
definition — but it asserts nothing about the data's biology, which is what the roadmap
actually cared about.

---

## Goals & Success Metrics

| Goal | Metric |
|---|---|
| A `pass` implies something was actually asserted | A result set of only informational + unverified checks reduces to `unverified`, never `pass`. Enforced by test. |
| Both informational mechanisms covered | All 4 known informational checks are verdict-neutral; a test enumerates them so a 5th cannot land silently. |
| No false-pass text in the UI | An all-unverified run never renders "PASS: all N checks passed". Enforced by test. |
| Zero back-compat breakage | Pre-change bundles deserialize and reduce to the same verdict as before. Enforced by test. |
| Nothing regresses | `uv run pytest` green; `npm run build` + dashboard tests green. |

**Non-goal:** changing any run's verdict *that had a real check in it*. A run with even one
asserting check reduces exactly as it does today.

**The one non-binary metric — and the honesty test for this whole slice.** Every metric
above is a test passing, which measures completion, not value. The real question is *how
many runs actually change verdict*. Tech-plan MUST produce this number by re-reducing the
existing test-fixture/bundle corpus before and after, and report it:

- **Zero flips** → the slice is cosmetic; say so plainly in the CHANGELOG rather than
  implying a false-pass class was closed. The dashboard fix (R5) would then be the only
  user-visible value, and the honest move is to consider shipping R5 alone.
- **Non-zero flips** → each one is a run that previously claimed a `pass` it had not
  earned. Enumerate them; they are the slice's evidence and its CHANGELOG.

Given the `min_sample_count` finding below, the expected answer for RNA-seq is **zero**, and
non-zero only for the other six assays. This number decides how the work is described.

---

## User Personas & Scenarios

- **A, lone computational biologist** runs RNA-seq where MultiQC yields only
  `PERCENT_DUPLICATION`. Today: verdict `pass` — she believes the data was checked.
  After: `unverified` — she knows nothing was asserted and looks closer.
- **B, core facility** runs many samples and reads verdicts in bulk. A `pass` that can be
  manufactured by informational checks makes the whole column untrustworthy. After, `pass`
  carries a guarantee.
- **C, wet-lab scientist who can't code** reads only the dashboard card. Today it can print
  "PASS: all 3 checks passed" beside an "Unverified" badge (R5) — a self-contradicting card
  and a literal false claim.

---

## Requirements

### R1 — `informational` marker on `QCResult` (MUST)

Add an orthogonal, additive field: `informational: bool = False`.

- Follows the `QCKind` precedent verbatim (`models.py:59-64`: *"defaults to `metric` so
  older records that predate the field deserialize unchanged"*).
- **Rejected alternatives** (decided, not open):
  - *New `QCStatus` value* (`"info"`) — rejected: widest blast radius, changes a persisted
    vocabulary mirrored in two unlinked TS unions and keyed by five exhaustive `Record<>`
    maps, for no added expressiveness.
  - *Reuse `unverified`* — rejected: it means "could not corroborate anything", but an
    informational check *did* produce a real value. Rendering `0.707214` as `unverified`
    trades one dishonesty for another.
  - *Exclude band-less rules from `overall_verdict`* (the brief's option 2) — rejected as
    stated: `QCResult` carries **no band information**, so the reducer cannot identify a
    band-less rule. It is not the cheap option; it needs a new field regardless.
- `informational` is **orthogonal to `kind`**. An informational check is still
  `kind="metric"`; overloading `kind` would conflate two axes.

### R2 — Mark all four informational checks (MUST)

The dig refuted the brief's "only `duplication_rate`" framing. Two distinct mechanisms:

| Check | Mechanism | Location |
|---|---|---|
| `duplication_rate` | band-less rule-pack config | `rule_pack.py:327` |
| `gene_symbol_concordance` | hardcoded pass | `verification/annotation_concordance.py` |
| `x_het_ratio` | hardcoded pass | `verification/sex_plausibility.py:306,317` |
| `gene_overlap` | hardcoded pass | `verification/count_concordance.py:326` |

`gene_overlap` appears **nowhere** in the brief or roadmap — found by the dig.

**Out:** `pon_applied` — 3-state but genuinely warns
(`tests/verification/test_somatic_plausibility.py:339`), so it asserts something.

**The band-less test is the absence of all four bound keys** (`fail_below`, `fail_above`,
`warn_below`, `warn_above`).
**MUST NOT** key off `expected_range is None`: `_expected_range` (`rule_pack.py:556-566`)
inspects only the two `warn_*` keys, so a rule with only `fail_below` also returns `None`
yet can FAIL. Keying off it would make a can-fail rule unfalsifiable — strictly worse than
the bug being fixed.

### R3 — Reducer skips informational results for positive severity (MUST)

```python
def overall_verdict(results):
    severe = [r for r in results if not r.informational]
    ...  # fail > warn > pass over `severe`; else "unverified"
```

**The invariant:** a set containing only informational and/or unverified checks reduces to
`unverified`, never `pass`.

Open sub-decision for tech-plan: whether an informational check may still carry `fail`/`warn`
(today none can). Simplest honest rule — informational results contribute **no severity at
all** — is the default unless the plan finds a reason otherwise. `overall_verdict`'s
existing empty-list `ValueError` must be preserved: an all-informational list is not empty,
it reduces to `unverified`.

### R4 — Rendering (SHOULD)

Informational results must be visually distinguishable from an asserting `pass` in the text
report, HTML report, `contig methods`, and the dashboard. Exact treatment is for tech-plan.

Known divergence to resolve: `dashboard/e2e/fixtures/corroboration-fixture/run_record.json:56-63`
stores `"expected_range": "informational"` while the Python-side helpers use `None`.

### R5 — Fix the dashboard's divergent reducer (MUST)

`dashboard/lib/derive.ts:51-56` is a **second copy** of the reducer with **no `unverified`
arm**:

```ts
if (statuses.has("fail")) return "fail";
if (statuses.has("warn")) return "warn";
return "pass";        // all-unverified lands HERE
```

Its docstring (`derive.ts:83-91`) claims it mirrors `models.py`; `VerdictExplanation`
(`derive.ts:72-76`) asserts *"We never re-derive trust"*. It does re-derive, and wrongly.

**Live reproduction, no change needed:** a run whose tasks succeeded and whose QC results
are all `unverified` → Python returns `"unverified"`, but `explainVerdict` returns
`verdict: "pass"`, reason **`"PASS: all N checks passed"`**, `decidingChecks` empty. That
string renders at `verdict-card.tsx:95` beside an "Unverified" badge from `record.verdict`.

Pre-existing and not caused by this work, but **in scope by decision**: it is the same
defect class, it is the only *live* instance, and any new neutral concept falls into the
same silent `return "pass"`.

### R6 — Back-compat (MUST)

Pre-change bundles must deserialize and reduce to **the same verdict as before**.

Mechanically this is free and needs **no versioning concept**: `informational` is set at
*evaluation* time and serialized per-result. An old bundle's stored `qc_results` carries no
such field → defaults to `False` → reduces exactly as today. `RunRecord.verdict` is a
`@computed_field` (`models.py:357-369`) re-derived from **stored results**, not by re-running
checks — so re-reading an old bundle does not re-mark anything and **history is stable**.

A verdict changes only for a new run, or when `contig verify` genuinely re-evaluates — which
is the honest path and the intended effect.

### R7 — Guard against a fifth informational check landing silently (SHOULD)

A test enumerating the informational set, so the next one is a deliberate act. This is the
durable form of the roadmap's *"decide before a second band-less rule lands"* — a deadline
prose already failed to hold.

---

## Technical Considerations

**Architecture fit.** Layer 2 (verify). Deepens the verdict; no Layer-1 drift; no wet-lab,
clinical, or proprietary-data dependency. Consistent with the C3 framing: *make every
verdict harder to fool*.

**Call sites.** `overall_verdict` has few: `models.py:369` (the `verdict` computed field)
and `report.py:50`.

**Reproducibility impact.** No manifest/pin change; no re-run behaviour change. The
reproduce bundle gains one additive per-result boolean.

**Dashboard.** Under R1 the `QCStatus`/`Verdict` TS unions are **untouched**, so none of the
five exhaustive `Record<>` maps break — a decisive practical advantage over the "new status"
option. New work is confined to R5's reducer fix plus R4 rendering. Note `dashboard/lib/runs.ts:58`
does `JSON.parse(...) as RunRecord` with **no runtime validation** (no zod anywhere), so the
new field is simply ignored by an un-updated dashboard — additive and safe.

**`--fail-on-verdict` (v0.36.0).** Unchanged: the verdict vocabulary does not grow, so the
exit-code mapping is untouched. A run that previously exited 0 on a manufactured `pass` may
now report `unverified` — the intended correction. *(To be confirmed in tech-plan.)*

**Tests that pin the bug** (must change deliberately, each is an assertion that an
informational check yields `pass`): `tests/verification/test_rnaseq_plausibility.py:36,52,59,188`;
`tests/verification/test_rule_pack.py:663`; `tests/verification/test_run_qc.py:146`;
`tests/verification/test_annotation_concordance.py:283,303,326`;
`tests/verification/test_sex_plausibility.py:392,435,456`;
`tests/verification/test_count_concordance.py:171,184,221`.
Golden-fixture helpers pinning `status="pass"` for `gene_symbol_concordance`:
`tests/verification/test_annotation_surface.py:50-62`, `tests/test_report.py:396-408`,
`tests/test_annotation_lifecycle.py:31-43`.
CLI text assertions coupling `gene_overlap` to `"pass"`:
`tests/test_cli.py:1710-1712,1892-1894,2285-2287,2546-2548`.
Reducer contract: `tests/test_models.py:29-43`.

---

## Risks & Open Questions

| Risk | Severity | Mitigation |
|---|---|---|
| Rewriting ~20 test assertions could mask a real regression | **High** | Each edited test must be justified as "this pinned the bug". Never weaken an assertion — replace `== "pass"` with the new intended outcome, don't delete. |
| Some run legitimately loses its `pass` and a user notices | Medium | Intended. Only affects runs whose *entire* evidence was informational. Old bundles unaffected (R6). |
| A can-fail rule accidentally marked informational | **High** | Never key off `expected_range`; test all four bound keys. R7's enumeration test guards the set. |
| `QC_RANK`/`STATUS_RANK` duplication (`derive.ts:44`, `qc-panel.tsx:61`) drifts | Low | Out of scope; note only. |
| Scope creep into the `multiqc is not None` gate | Medium | Explicitly out of scope (below). |

**Open questions for tech-plan:**
1. May an informational check ever carry `fail`/`warn`, or is it always no-severity? (R3)
2. Exact rendering treatment across four surfaces. (R4)
3. Does `contig methods` need an informational marker in its prose?
4. Confirm `--fail-on-verdict` needs no change.
5. **Does `min_sample_count` count as real evidence?** It can fail, so it is not
   informational under R1 — but it asserts only "≥2 samples exist", nothing biological. It
   is RNA-seq-only (`runner.py:276`) and is the reason the roadmap's motivating example does
   not flip. Leaving it as-is is the conservative choice this PRD takes; a follow-on could
   introduce an "asserts something biological" distinction. **Do not silently widen R1 to
   catch it** — it can fail, and R1's definition must stay mechanical.
6. **`x_het_ratio` conflates two states.** `tests/verification/test_sex_plausibility.py:435`
   is literally named `test_evaluate_indeterminate_is_unverified_with_none_value` yet asserts
   `status == "pass"` with `value is None`. A check that could not compute a value is
   `unverified`, not informational-pass. Tech-plan must decide whether `value is None` cases
   become `unverified` while real values become informational — this is a semantic
   distinction the current always-pass convention erases, and the test name shows the author
   already felt the tension.

---

## Out of Scope

- **`runner.py:412`'s `multiqc is not None` gate** — a run with no MultiQC makes both RNA-seq
  plausibility checks vanish rather than report `unverified`. A real, separately-named
  pre-existing honesty gap (`CAPABILITY_ROADMAP.md:650-653`).
- **Re-opening any declined-by-design band** — RNA-seq FAIL severity, somatic VAF/PON bands,
  and the `duplication_rate` band itself are settled, not pending. This slice does **not**
  add a band to `duplication_rate`; it changes how band-less rules *reduce*.
- **`pon_applied`** — it warns; not informational.
- **De-duplicating `QC_RANK`/`STATUS_RANK`.**
- **Adding runtime (zod) validation to the dashboard.**
- **`percent_rRNA`'s guessed slug** — separate named follow-on.

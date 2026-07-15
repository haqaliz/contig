# Phase 2 — Understanding: verdict-neutral-informational-checks

Dug by parallel read-only agents (reducer, persistence/dashboard blast radius, rule +
test inventory) plus direct verification from the main thread. Every claim is grounded in
a file:line read in this worktree. Where the brief (inherited from
`CAPABILITY_ROADMAP.md:654-664`) is wrong, it is marked **REFUTED** rather than papered
over.

---

## 1. What the work is really asking

The verdict currently lets a check that **asserts nothing** count as evidence that
**something was verified**. The ask: give such checks an outcome carrying no positive
severity, so a run whose only checks are informational cannot reduce to `pass`.

Layer-2 verify-layer change (CLAUDE.md wedge). No Layer-1 drift, no wet-lab/clinical
dependency. On-thesis.

---

## 2. The defect mechanism — CONFIRMED

`_status_for` (`src/contig/verification/rule_pack.py:534-553`) reads every bound with
`.get()`:

```python
fail_below = check.get("fail_below")
fail_above = check.get("fail_above")
if (fail_below is not None and value < fail_below) or (...):
    return "fail"
warn_below = check.get("warn_below")
warn_above = check.get("warn_above")
if (warn_below is not None and value < warn_below) or (...):
    return "warn"
return "pass"
```

A rule declaring **none** of the four bound keys falls through every guard to
`return "pass"` — structurally incapable of any other status.

That `pass` enters `overall_verdict` (`src/contig/models.py:78-96`) at full severity:

```python
if "fail" in statuses: return "fail"
if "warn" in statuses: return "warn"
if "pass" in statuses: return "pass"
return "unverified"
```

`pass` outranks `unverified`, so **one informational check is enough** to convert a run
that verified nothing into a `pass`. Confirmed end-to-end.

---

## 3. The brief's claims, tested

### 3a. "`duplication_rate` is the only band-less rule" — TRUE but MISLEADING

True in the narrow *rule-pack-config* sense; pinned by an existing test
(`tests/verification/test_rule_pack.py:622-632` asserts none of the four bound keys are
present). But it is **not** the only informational check — see 3b.

### 3b. "`gene_symbol_concordance` and `x_het_ratio` are informational too" — TRUE, but by a DIFFERENT MECHANISM, and the list is longer — **REFUTED as stated**

They are **not** band-less rules and never traverse `rule_pack._status_for`. They are
**hardcoded always-pass** in bespoke verification modules. The full informational set:

| Check | Mechanism | Location |
|---|---|---|
| `duplication_rate` | band-less rule-pack config | `rule_pack.py:327` (RNASEQ_PLAUSIBILITY_PACK) |
| `gene_symbol_concordance` | hardcoded pass | `verification/annotation_concordance.py` |
| `x_het_ratio` | hardcoded pass ("informational-always-PASS convention") | `verification/sex_plausibility.py:306,317` |
| `gene_overlap` | hardcoded pass, "informational never warns" | `verification/count_concordance.py:326` |

`gene_overlap` **is mentioned nowhere in the brief or the roadmap** — found by the dig.
`pon_applied` is **out**: 3-state but genuinely warns
(`tests/verification/test_somatic_plausibility.py:339`), so it asserts something.

### 3c. The roadmap's deadline has ALREADY PASSED — **the framing is stale**

`CAPABILITY_ROADMAP.md:663` says **"Decide before a second band-less rule lands."** In the
sense that matters — checks that always pass and assert nothing — **three more already
landed**. The roadmap counted only the rule-pack-config mechanism and so under-counted its
own problem. This *raises* priority, and means the fix must address the hardcoded-pass
mechanism, not just the band-less config path.

### 3d. A trap to avoid — do NOT use `expected_range is None` as the band-less test

The v0.38.0 slice made `_expected_range` return `None` for a band-less rule
(`rule_pack.py:556-566`), which tempts using `expected_range is None` as the signal. **It
is not.** That function inspects only `warn_below`/`warn_above`, so a rule with only
`fail_below` and no warn bands *also* returns `None` — yet can FAIL. Keying
verdict-neutrality off it would silently make a can-fail rule unfalsifiable: strictly
worse than the bug being fixed. Correct test: absence of **all four** bound keys.

---

## 4. The design fork — reframed

The brief inherits a two-option fork: (1) new verdict-neutral `QCStatus`, or (2) exclude
band-less rules from `overall_verdict`. **The fork is drawn on the wrong axis.**

`QCResult` (`models.py:67-75`) carries `check`/`status`/`message`/`value`/
`expected_range`/`kind` — and **no band information**. At reduce time `overall_verdict`
sees only `QCResult`s. So option 2 is *not* the cheap option: it cannot be implemented
without adding a field anyway. Both are schema changes. The real question is **which axis
carries the signal**:

- **(a) New `QCStatus` value** (e.g. `"info"`). Widest blast radius: persisted vocabulary,
  mirrored in TS, keyed by five exhaustive `Record<>` maps.
- **(b) New orthogonal marker on `QCResult`** (e.g. `informational: bool = False`), with
  `overall_verdict` skipping informational results for the positive-severity decision.
  Additive; defaults to today's behaviour; old records deserialize unchanged.
- **(c) Reuse `unverified`.** Semantically close — its docstring (`models.py:51-55`)
  already says it "carries no severity, so it neither passes nor fails". But it means
  "could not corroborate anything", and an informational check *did* produce a value;
  rendering a real number as `unverified` trades one dishonesty for another.

**Precedent favours (b):** `QCKind` (`models.py:59-64`) is exactly this pattern, with the
rationale verbatim — *"defaults to `metric` so older records that predate the field
deserialize unchanged."* Note `QCKind` is orthogonal (metric/structural/concordance); an
informational check is still kind `metric`, so overloading `kind` would conflate two axes.
PRD decision, not settled here.

**Whatever is chosen, the invariant to encode:** a result set containing only
informational + unverified checks MUST NOT reduce to `pass`.

---

## 5. Blast radius

**Python.** `overall_verdict` call sites are few: `models.py:369` (via the `verdict`
computed field) and `report.py:50`. Current reduction pinned by `tests/test_models.py:29-43`.

**`RunRecord.verdict` is a `@computed_field`** (`models.py:357-369`) — re-derived from
`qc_results` on every deserialization, never read back from stored JSON:
- **Good for back-compat:** old bundles carry no informational marker; with a
  `False`/absent default they reduce exactly as today.
- **But the change is retroactive:** re-reading an existing bundle under new code can
  change its displayed verdict once results are re-marked. Explicit PRD decision needed.

**Tests pinning informational→pass** (they encode the bug; must change deliberately):
`tests/verification/test_rnaseq_plausibility.py:36,52,59,188`;
`tests/verification/test_rule_pack.py:663`; `tests/verification/test_run_qc.py:146`;
`tests/verification/test_annotation_concordance.py:283,303,326`;
`tests/verification/test_sex_plausibility.py:392,435,456`;
`tests/verification/test_count_concordance.py:171,184,221`. Golden-fixture helpers pinning
`status="pass"` for `gene_symbol_concordance`:
`tests/verification/test_annotation_surface.py:50-62`, `tests/test_report.py:396-408`,
`tests/test_annotation_lifecycle.py:31-43`. CLI text assertions coupling `gene_overlap` to
`"pass"`: `tests/test_cli.py:1710-1712,1892-1894,2285-2287,2546-2548`.

**Dashboard (TS).** `dashboard/lib/types.ts:6,11` mirror `Verdict` and `QCStatus` as two
separate, unlinked literal unions. Five **exhaustive** `Record<>` maps fail the build until
updated (the good case — compiler catches them): `components/status-badge.tsx:18-39`,
`lib/derive.ts:31-36` (`VERDICT_ORDER`), `lib/derive.ts:44-49` (`QC_RANK`),
`components/run/qc-panel.tsx:61-66` (`STATUS_RANK`, a duplicate of `QC_RANK`),
`components/run/verdict-card.tsx:16-22` (`VERDICT_HEADLINE`).
**Non-exhaustive, silently wrong:** `app/runs/runs-table.tsx:36-42` `VERDICT_FILTERS` is an
array, not a `Record` → a new value silently gets no filter button;
`runs-table.tsx:123` casts unchecked.
**No runtime validation exists:** `dashboard/lib/runs.ts:58` does
`JSON.parse(...) as RunRecord` — compile-time-only cast; no zod anywhere in the tree.

---

## 6. Contradiction found: a LIVE false-pass bug in the dashboard (pre-existing)

`dashboard/lib/derive.ts:51-56` is a **second, divergent copy** of the reducer:

```ts
function overallQc(results: QCResult[]): QCStatus {
  const statuses = new Set(results.map((r) => r.status));
  if (statuses.has("fail")) return "fail";
  if (statuses.has("warn")) return "warn";
  return "pass";        // <-- all-unverified lands HERE
}
```

It has **no `unverified` arm**. Its docstring (`derive.ts:83-91`) claims it mirrors
`models.py` "in the same order the engine decides it" and lists only `fail > warn > pass`;
`VerdictExplanation` (`derive.ts:72-76`) asserts *"We never re-derive trust"* — but it does
re-derive, and re-derives **wrongly**.

**Reproduction (today, no change needed):** a run whose tasks all succeeded and whose QC
results are all `unverified` → Python `overall_verdict` returns `"unverified"`, but
`explainVerdict` returns `verdict: "pass"` with reason **`"PASS: all N checks passed"`**
(`derive.ts:116-121`) and `decidingChecks` empty (it filters for status `"pass"`, of which
there are none). That reason string renders at `components/run/verdict-card.tsx:95`, beside
an "Unverified" badge driven by `record.verdict` (`verdict-card.tsx:69,75`). The card
contradicts itself and prints a literal false-pass sentence.

Same defect class as this card (something that verified nothing rendering as a pass), in a
duplicated reducer. Pre-existing, not caused by this work — but this slice makes it worse:
any new neutral status also falls into that `return "pass"` with no compiler signal.
**PRD must decide:** fix here or file separately. Recommend fixing here — the card's thesis
is "a pass must mean something was verified", and shipping the Python fix while the
dashboard still prints "all N checks passed" leaves the headline claim false in the UI.

---

## 7. Open questions for the PRD

1. **Which axis** carries verdict-neutrality: new `QCStatus` value, new orthogonal
   `QCResult` field, or reuse `unverified`? (Dig favours the orthogonal field; `QCKind` is
   the precedent.)
2. **Migration scope:** all four informational checks in this slice, or `duplication_rate`
   only with the three hardcoded-pass ones as a follow-on? (Dig favours all four — the
   roadmap's "before a second lands" deadline is already missed by three, and
   `gene_overlap` is undocumented.)
3. **Retroactivity:** should re-reading an old bundle change its displayed verdict?
4. **Dashboard `overallQc`:** fix the live false-pass here, or file separately?
5. **Rendering:** how does an informational result display in text/HTML/`contig methods`/
   dashboard, and does `expected_range` show `"informational"`? Note a fixture/production
   divergence: `dashboard/e2e/fixtures/corroboration-fixture/run_record.json:56-63` stores
   `"expected_range": "informational"` while Python-side helpers use `None`.
6. **`--fail-on-verdict` (v0.36.0):** does a neutral status reach the exit code safely?
7. **Does an all-informational run reduce to `unverified`?** Dig says it must. Confirm the
   invariant and its acceptance test.

---

## 8. Guardrail check

- **Layer 2 only** — yes: hardens the verdict.
- **Moat** — yes: "make every verdict harder to fool" (C3 framing). Removes a false-pass
  path; PRODUCT_SPEC treats false-pass as the cardinal sin (target ~0).
- **Founder's edge** — yes: pure engineering, no credentials/data dependency.
- **Not re-opening a declined band** — correct: this does not add a band to
  `duplication_rate` (declined by design); it changes how band-less rules *reduce*, the
  explicitly named follow-on.

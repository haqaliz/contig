# PRD: RNA-seq duplication plausibility — make the metric arrive, correctly

- **Slug:** `rnaseq-plausibility-ingestion`
- **Branch:** `feat/rnaseq-plausibility-ingestion/aliz`
- **Capability:** C3 (biological-plausibility verification), RNA-seq follow-on slice
- **Status:** ready for tech-plan
- **Severity contract:** **informational-only** (always PASS + value reported). No WARN band, no
  FAIL. See "The band: declined" below — this is a decision, not an omission.

---

## Problem Statement

`RNASEQ_PLAUSIBILITY_PACK` (`rule_pack.py:295-315`) has never scored a metric on a real
`nf-core/rnaseq` run. Its `duplication_rate` check asks MultiQC for a key named
`percent_duplication` and bands it `warn_above: 80.0` on a declared 0–100 scale. Both are wrong:

1. **Wrong case.** MultiQC's Picard module publishes the key as **`PERCENT_DUPLICATION`**
   (uppercase). `qc_ingest.py:5-23` does an exact-key merge, so the lookup misses on every run.
2. **Wrong scale.** MultiQC stores the **raw 0–1 fraction** (`0.85`), not a percentage. The
   `×100` in the module's header is a **display-only** render hook.

The metric was never missing from MultiQC — Contig has been asking for it by the wrong name, in
the wrong unit, for six releases.

### Evidence

| Claim | Source |
|---|---|
| MultiQC's Picard module adds duplication to General Statistics | MultiQC `modules/picard/MarkDuplicates.py`: `module.general_stats_addcols(data_by_sample, headers, namespace="Mark Duplicates")` |
| The key is `PERCENT_DUPLICATION` (uppercase) | same file: `headers = {"PERCENT_DUPLICATION": {...}}` |
| The stored value is the raw 0–1 fraction | same file: parsed `float(v)` straight into `data_by_sample`, which is what `general_stats_addcols` stores |
| The `×100` is display-only | same file: `"modify": lambda x: util.multiply_hundred(x)` — a header hook, not applied to stored data |
| The key is **bare, not namespaced**, in the data | same file: `namespace="Mark Duplicates"` is a *display* grouping; the `picard_mqc-generalstats-*` forms are HTML column IDs, not JSON keys |
| **Picard's own source agrees the value is a fraction** (independent 2nd source) | `picard/sam/DuplicationMetrics.java` javadoc: *"The fraction of mapped sequence that is marked as duplicate"*; and `PERCENT_DUPLICATION = (UNPAIRED_READ_DUPLICATES + READ_PAIR_DUPLICATES * 2) / (double)(UNPAIRED_READS_EXAMINED + READ_PAIRS_EXAMINED * 2)` — **no `×100` in the formula**. A 70%-duplicated sample reads `0.707214`. **The metric's name lies.** |
| MarkDuplicates is **auto-skipped** under `--with_umi` | nf-core/rnaseq output docs: *"The pipeline automatically skips this step when using `--with_umi` or when explicitly specifying `--skip_markduplicates`."* → a legitimate no-key path |
| **The repo already documented this defect** | `rule_pack.py:290-294`: *"both slugs below are unverified AND absent from the repo's only real-shaped MultiQC report ... These rules have never once fired on a real report, so FAIL severity here would be severity on dead code."* |
| nf-core/rnaseq runs MarkDuplicates **by default** | `nextflow.config@3.26.0`: `skip_markduplicates = false` |
| Contig pins that revision | `src/contig/cli.py:242`, `src/contig/heal.py:116` |
| Contig sees neither key today | `demo/sample-run/results/multiqc/multiqc_data.json` carries only `uniquely_mapped_percent`, `percent_assigned`, `total_reads` |
| That demo report is **synthetic** | `demo/make_sample_run.py:59,105` writes a hardcoded `_GOOD_MQC` literal — it is not an observed run |

### Two corrections to the record (this PR must fix them)

The originating nomination in `CAPABILITY_ROADMAP.md` (C3, somatic FAIL-floor slice) is
**materially wrong on two counts**, and a wrong map costs more than a missing check:

1. **"Silent no-op" is false.** The pack does not score, but it is not silent:
   `evaluate_rnaseq_plausibility` (`rnaseq_plausibility.py:69-79`) emits an explicit
   `unverified` result per absent metric per sample — four on the repo's own demo fixture. The
   pack is **dormant but honest**.
2. **"Same defect class as the single-cell dormant pack" is false for duplication.**
   methylseq/scrnaseq were *true* silent no-ops — their packs ran through the bare `evaluate()`,
   which *skips* absent metrics (`rule_pack.py:543-544`) — and their metrics genuinely never
   reached MultiQC, so a dedicated artifact parser was the only fix. **Duplication is in
   MultiQC.** It needs no parser. (The claim remains true for `percent_rRNA` — see Out of Scope.)

**We are therefore not fixing a false-pass bug. The current code is honest.** The false pass is
one this slice would *introduce* if it fixed the slug without the scale.

### Why now / what it costs to skip

Honest framing: nobody has asked for this, and after the decision below it produces **no
severity at all**. The case for doing it is **not** the check's judgement — it is that:
(a) `CAPABILITY_ROADMAP.md` currently asserts something **false** about our own engine;
(b) the pack sits one plausible "just fix the slug" commit away from **silently passing**
96%-duplicated libraries; and
(c) a real library-complexity number reaches the verdict for the first time, on the one assay
exercised end-to-end in CI (`CLAUDE.md`).

---

## The band: declined (the core design decision)

**`duplication_rate` ships informational-only: the value is reported, no band, always PASS.**

This is not laziness or missing calibration. It follows from the pack's own docstring
(`rule_pack.py:287-288`): *"A deep/high-input library **legitimately exceeds 90% duplication**."*

- `warn_above: 80.0` (today's dormant band) would WARN on a large share of legitimate libraries.
- `warn_above: 0.90` would fire on `> 0.90` — **precisely the population that sentence calls
  legitimate**. It relocates the line to the boundary of the legitimate range rather than above it.
- Any band ≥ 0.95 is an **invented number**: no calibration data exists in the repo, and any
  "typical value" claim would be fabricated.

This is the **same argument** that got FAIL severity declined for this pack in
`CAPABILITY_ROADMAP.md` (C3): *"'Extreme' and 'unusual protocol' are the same number"*, and the
pack sees **no library-prep signal** that separates them. That argument was never actually about
severity — it is about the **number**. It applies with undiminished force to a WARN band.

So the honest act is to **report the metric and decline to judge it**. A tripwire that fires on
protocols the same file calls legitimate is noise, and noise is how a verdict axis gets
ignored — a softer version of the very failure this slice exists to fix.

**Precedent (this is an established shape, not a new concept):** `gene_symbol_concordance` is
informational-only/always-PASS (*"VEP/SnpEff symbol sources diverge too much for an honest
WARN"*), `gene_overlap` is informational and never WARNs, and `x_het_ratio` is informational
alongside the banded `sex_plausibility`.

**Revisit trigger (committed):** a band becomes justifiable if either (a) real duplication
distributions per protocol are collected, or (b) the pack gains a library-prep/input-amount
signal that separates "deep library" from "broken library". Until then, no band.

---

## The unit: report the raw fraction (a recorded dissent)

**Decision: report `0.707` as-is. Do NOT `×100` it.**

A dig agent recommended the opposite — *"convert at ingest, don't move the band"*, i.e. scale
`×100` so rnaseq's duplication matches methylseq's 0–100 `duplication_rate`. That advice was
**sound for a banded check** (its stakes argument is exactly right: `0.85` against
`warn_above: 80.0` passes silently). But it was written before the band was declined, and once
there is **no band**, its premise is gone:

- The only reason to rescale was to make the value meet a 0–100 band. **There is no band.**
- A transform that exists solely for cross-assay display consistency is a **pure bug surface**
  with no verification value. Not rescaling cannot be wrong.
- `RNASEQ_COMPOSITION_PACK` already reports 0–1 fractions on this same assay
  (`rule_pack.py:421-422`), and this rule's own message already says *"**fraction** of
  alignments flagged as duplicates"*. The raw fraction is the locally consistent choice.
- The guard (M5) is expressed naturally against the documented `[0.0, 1.0]` contract.

**Known cost, accepted:** the check name `duplication_rate` now means a **0–1 fraction** for
rnaseq and a **0–100 percent** for methylseq (`rule_pack.py:181`, asserted at
`test_run_qc.py:918-920`). The two never co-occur — each is gated to its own assay, and methylseq
is in `_DEDICATED_METRIC_ASSAYS` (`runner.py:73`) while rnaseq is not — so **no run can emit
both**. But a reader comparing packs will see one name with two units. M8 must state this
explicitly at both sites. **Open question for tech-plan:** is renaming rnaseq's check to
`duplication_fraction` worth the user-visible check-name change? Recorded, not decided here.

---

## Goals & Success Metrics

| Goal | Measure |
|---|---|
| The metric arrives | A realistic `multiqc_data.json` fixture (uppercase key, 0–1 value) drives a `duplication_rate:<sample>` result with the **value reported** — not `unverified` |
| **The unit is right** | A `0.96` run reports **`0.96`**, not `96.0` and not a rescale. This is the whole point: the number must mean what it says |
| No false pass is introduced | The slug fix never lands without the scale fix (M2) |
| No fabricated judgement | The result is **always PASS** — the verdict never claims duplication is good or bad |
| The guarantee survives | Absent metric → still exactly one `unverified`, never PASS |
| Severity unchanged | No fixture drives `record.verdict` → WARN or FAIL from this check; `verify` exit code unchanged |
| No regressions | `RNASEQ_RULE_PACK` and `RNASEQ_COMPOSITION_PACK` results byte-identical |
| The record is true | The two false claims above corrected in `CAPABILITY_ROADMAP.md` |

---

## Users & Scenario

Contig's ICP running bulk RNA-seq (lone computational biologist; core facility). Today every run
reports `duplication_rate: unverified` — no signal at all. After this slice the verdict reports a
real library-complexity number they can read, attributed to Picard via MultiQC, with Contig
explicitly **not** judging it. They never touch a flag; the check is auto-wired.

---

## Requirements

### Must-have

- **M1 — Fix the key.** `percent_duplication` → `PERCENT_DUPLICATION`, with the MultiQC module
  cited in a comment. **The `# slug unverified` comment must go** — it is now verified.
- **M2 — Fix the scale.** The value is a 0–1 fraction; the pack must stop declaring 0–100 for it.
  **M1 and M2 MUST land in the same commit.** M1 alone, with today's `warn_above: 80.0` still in
  place, converts a safe dormant check into a **false pass** (`0.96` < `80.0` → PASS).
- **M3 — No band; informational-only.** Remove `warn_above` from `duplication_rate`. The rule
  reports the value and always PASSes. Record the full rationale + revisit trigger in the pack
  comment (see "The band: declined") so the reason travels with the code.
- **M4 — Support band-less rules in the scorer.** `_status_for` (`rule_pack.py:504-523`) already
  returns `"pass"` when no bounds are declared — **no change needed**. But `_expected_range`
  (`rule_pack.py:526-535`) falls through to `f">= {warn_below}"` and would render the string
  **`">= None"`** for a band-less rule. It must render something honest (e.g. `None`, or an
  explicit informational marker). **This is the one genuine code change in the slice** and it is
  shared machinery — regression-test the other packs' `expected_range` rendering.
- **M5 — The assumption guard.** A `PERCENT_DUPLICATION` value **outside `[0.0, 1.0]`** violates
  MultiQC's documented contract → emit **`unverified`**, never a result.
  - **Not** the sniff-and-convert heuristic (unsound: `0.5` is ambiguous between 50% and 0.5%).
    It **never rescales**; it only **refuses**.
  - **Why it matters more now, not less:** with no band, a wrongly-scaled `95.0` would otherwise
    be reported as a PASS with `value=95.0` — a **wrong number surfaced as fact**. Informational
    reporting removes the false-*pass* risk but not the false-*number* risk. The guard covers it.
  - `1.0` is **valid** (a fully-duplicated library) — the guard is strict `> 1.0` / `< 0.0`.
  - Home: `rnaseq_plausibility.py` — the module that already owns the per-metric honesty branch.
- **M6 — Re-point the fabricated tests.** `test_run_qc.py:118`
  (`DUP_HIGH_MQC = '{"report_general_stats_data":[{"S1":{"percent_duplication":95.0}}]}'`) and
  `test_rnaseq_plausibility.py:21` (`{"percent_duplication": 30.0}`) assert against a report
  shape real nf-core/rnaseq **never emits** — wrong case *and* wrong scale. **This is how a green
  suite masked a dead check for six releases: the tests prove the *wiring*, never the
  *ingestion*.** Fixtures must become realistic or we re-ship the blindness. Note their WARN
  assertions die with the band — replace with value-reported assertions.
- **M7 — Fix the two misleading comments.**
  - `rule_pack.py:298-299` — *"Scale 0-100, matching METHYLSEQ_RULE_PACK's percent_duplication
    usage."* Methylseq's 0–100 is **earned** (its parser reads an already-percent Bismark
    artifact; `methylseq_metrics.py:81-84` captures digits inside a literal `%`). RNA-seq's
    0–100 was **declared and enforced by nothing**. The two slugs share a name, never a code
    path. **That sentence is what made this ambiguity look resolved.**
  - `runner.py:420-422` — *"the MultiQC pack above still owns alignment/duplication/rRNA"* is a
    fiction: no pack scores duplication today. This slice makes it true for duplication.
- **M8 — The pack becomes internally mixed-unit; the comment must go per-metric.** After M2,
  `duplication_rate` is **0–1** while `rrna_contamination` is still declared **0–100**
  (`warn_above: 10.0`). The **pack-level** header comment (`rule_pack.py:295-299`) declares one
  scale for the whole pack and becomes false. Rewrite it **per-metric**, naming each metric's
  unit and source. Mixed units across packs are already the repo's design
  (`rule_pack.py:421-422`); mixed units *within* one pack are new, and this ambiguity is exactly
  what caused the bug — state it, don't leave it implicit.
- **M9 — Correct `CAPABILITY_ROADMAP.md`**: the "silent no-op" and "same defect class" claims,
  and the C3 FAIL-severity record's *"never once resolved against a real MultiQC report"*
  reasoning (see Out of Scope).

### Should-have

- **S1** — A comment at the metric naming the observed-vs-reasoned limit, so the next reader
  knows the key/scale came from MultiQC's source, not an observed run.

### Out of scope (explicit)

- **`rrna_contamination` / `percent_rRNA`.** Deliberately untouched, and it **remains a guessed
  slug** — a known, accepted debt of this slice, not an oversight. It is genuinely the
  single-cell defect class. **Independently researched: the answer is a clean "none".** No
  default artifact in 3.26.0 yields an rRNA *fraction* as a general-stats metric, and
  `percent_rRNA` is not a real key anywhere:
  - **SortMeRNA** — off by default (`remove_ribo_rna = false`). Not a source.
  - **featureCounts biotype QC** — depends **entirely** on the user's GTF
    (`featurecounts_group_type = 'gene_biotype'`); when the attribute is absent (**common for
    NCBI GTFs**) the pipeline warns *"Biotype attribute 'gene_biotype' not found... Biotype QC
    will be skipped"* and continues non-fatally (nf-core/rnaseq issues #1086, #460). Even when it
    runs it emits per-biotype **counts** as custom content, not a percentage or a general-stats
    key. **⚠ Unconfirmed for 3.26.0:** the workflow appears **refactored** (a `use_rustqc` path;
    no `skip_biotype_qc` / `SUBREAD_FEATURECOUNTS` / `MULTIQC_CUSTOM_BIOTYPE` found in
    `workflows/rnaseq/main.nf`), so the older `*.biotype_counts_mqc.tsv` name **must not be
    assumed to still hold**. Any follow-on must re-establish this from 3.26.0 itself.
  - **samtools idxstats** — per-contig counts needing rRNA-named contigs. Not a biotype fraction.
  **Recommended follow-on: drop the check** (precedent: the single-cell slice *deleted* its dead
  `pct_reads_mito`). Deriving it from biotype counts would stay UNVERIFIED for a large share of
  real runs, and **guessing a second slug is literally the bug we are fixing.**
- **FAIL severity. Declined by design, not deferred** — and now, so is WARN (see "The band").
  `CAPABILITY_ROADMAP.md` (C3) declined FAIL for two reasons: *biology* ("extreme" and "unusual
  protocol" are the same number) and *engineering* (severity on a metric that never arrives is
  severity on dead code). **This slice removes only the engineering half.** The biological half
  stands untouched and now also carries the WARN band. Honest note for M9: this slice makes one
  sentence of that record false (duplication *will* now resolve against a real report). **The
  conclusion is unchanged; the stated reasoning needs the correction.**
- **The `multiqc is not None` gate bug** (`runner.py:412`): with no MultiQC report the two checks
  **vanish** rather than reporting UNVERIFIED (the composition gate at `:428` correctly gates on
  assay alone). Real, pre-existing honesty gap. Recorded, deferred — see Open Questions.
- Band calibration; capture/protocol-aware bands; a dashboard card; the C6 eval fold-in; any new
  module, model, `FailureClass`, or dependency.

---

## Technical Considerations

**Shape: a data edit, one shared-machinery fix (M4), and one guard (M5).** No new module,
locator, `_discover_qc` gate, parser, or unit-normalization layer. Because the value rides the
**existing** MultiQC dict:

- **Sample-naming risk is void** — we reuse MultiQC's own sample keys. (A dedicated Picard parser
  *would* have had one: the artifact is `<SAMPLE>.markdup.sorted.MarkDuplicates.metrics.txt`, so a
  naive suffix-strip keys a phantom `WT_REP1.markdup.sorted`.)
- **Merge/unit-collision risk is void** — there is no second source to merge.
- **`qc_ingest.py` must NOT change.** It is assay-blind and feeds `VARIANT_RULE_PACK`
  (`ts_tv` ≈ 2.0) and `SCRNASEQ_RULE_PACK` (`fraction_reads_in_cells` banded at 0.7) on the same
  path. Any value-sniffing normalization there is wrong in **both directions at once** — it
  would rewrite `ts_tv = 0.9` → `90.0` and flip `fraction_reads_in_cells = 0.65` from a correct
  WARN into a **false PASS**. Local-to-the-consumer is the unanimous repo pattern
  (`scrnaseq_metrics.py:88-102` normalizes per-field *"so its unit matches the pack band"*;
  `ampliseq_metrics.py:99-101` converts the other way).
- The scorer is scale-agnostic: `_status_for` is pure numeric comparison with no unit metadata.
  **It trusts its input's unit absolutely** — which is why a wrong unit is silent rather than
  loud, and why M5's guard belongs in the wrapper.
- **`_expected_range` is shared by every pack** — M4 touches machinery all seven assays render
  through. Smallest safe change; regression-test the others.

**Reproducibility/verification impact:** `verdict` is a `@computed_field` in the signed canonical
payload, so re-verifying an affected old bundle re-reduces it and its Ed25519 signature no longer
matches. Blast radius here is **unusually small**: the check moves from `unverified` to an
always-PASS informational result, and `unverified` carries no severity — so the reduced verdict
should not flip. **Pre-existing property of any rule-pack edit**, inherited from v0.35.0/v0.37.0.
Confirm in the plan; note in the changelog.

---

## Risks & Open Questions

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R1 | **The key/scale are read from source, not an observed artifact.** No real `multiqc_data.json` exists in-repo (the demo one is **synthetic** — `make_sample_run.py:59,105`). **Narrowed by the dig:** Picard's *native* unit is now airtight from **two independent sources** (Picard's javadoc + formula; MultiQC's module). What remains un-observed is only whether MultiQC's **JSON export** stores the raw or the `modify`-applied value — the code path says raw (the lambda lives in `headers`, and no scaling touches `data_by_sample` before `general_stats_addcols`). Status: **strongly corroborated, not observed.** | Med (was Top) | **M5's guard** makes a wrong scale degrade to UNVERIFIED; a wrong key was already safe. **Every known way to be wrong now degrades to honest.** Precedent: the somatic FAIL floor shipped a failure *"reasoned rather than observed"*. One real run closes it outright. |
| R2 | **The residual R1 hole:** "the check silently never fires and we *believe* it does." No guard covers this — it is the same blindness that let the bug live six releases. | Med | Only a real report closes it. **The re-pointed tests must assert against a realistic shape**, and the roadmap entry must state the limit rather than claim victory. |
| R3 | MultiQC version coupling: key/scale read from MultiQC `main`, not the MultiQC pinned inside nf-core/rnaseq 3.26.0. | Med | Confirm during implementation; M5 absorbs a scale change; a key change → UNVERIFIED (honest). |
| R4 | The `PERCENT_DUPLICATION` column could be namespaced in `report_general_stats_data` (module-keyed schema). | Med | `qc_ingest.py:11-14` already merges the module-keyed schema, so the inner key should survive. Failure mode is UNVERIFIED (safe). |
| R5 | nf-core/rnaseq may not enable MultiQC's picard module even though MarkDuplicates runs. | Med | Failure mode is UNVERIFIED (safe, = today). Worth confirming. |
| R6 | M4 touches `_expected_range`, shared by all seven assays' rendering. | Low | Smallest possible change; regression-test every pack's `expected_range`. |

**Open questions**

1. **Can we get a real `multiqc_data.json`?** (nf-core test-datasets / a CI artifact.) The single
   highest-value follow-up: converts R1–R5 from reasoned to observed and yields a real fixture.
   Not a blocker given M5.
2. **The `multiqc is not None` gate** (`runner.py:412`) — file as a follow-on.
3. **`rrna_contamination`'s fate** — build the biotype parser, or drop it? Needs the biotype TSV
   column layout confirmed first.
4. Should `demo/make_sample_run.py`'s `_GOOD_MQC` gain a realistic `PERCENT_DUPLICATION` key, so
   the demo stops teaching the wrong report shape? (Cosmetic, but it is the artifact that made
   the wrong shape look canonical.)

---

## Acceptance (test-first)

1. **Realistic fixture** `{"report_general_stats_data":[{"S1":{"PERCENT_DUPLICATION":0.96}}]}` →
   `duplication_rate:S1` exists, `status == "pass"`, **`value == 0.96`** (not `96.0`, not
   rescaled, not `unverified`).
2. `0.30` → same shape, `value == 0.30`, `status == "pass"`. **No input value produces WARN or
   FAIL from this check** — assert across a sweep (e.g. `0.0, 0.3, 0.9, 0.95, 1.0`).
3. `expected_range` renders honestly for the band-less rule — **never the string `">= None"`**
   (M4). Assert the exact rendered value.
4. **Regression lock:** the *old* fixture shape (`percent_duplication: 95.0`) → `unverified`
   (wrong key) — proving the old test could never have caught this.
5. **Guard:** `PERCENT_DUPLICATION: 95.0` (contract violated, > 1.0) → **`unverified`**, never a
   reported value, with a message naming the violated 0–1 contract.
6. **Guard:** a negative value → `unverified`. **Boundary:** `1.0` is **valid** → reported, not
   guarded away.
7. Metric absent → exactly one `unverified` (unchanged). **This is a real production path, not a
   hypothetical:** `--with_umi` and `--skip_markduplicates` both auto-skip MarkDuplicates, so a
   legitimate run emits no key at all. Name that case in the test.
8. No fixture drives `record.verdict` → WARN/FAIL from this check; `verify` exit code unchanged.
9. `RNASEQ_RULE_PACK` + `RNASEQ_COMPOSITION_PACK` results unchanged, **and every other pack's
   `expected_range` rendering unchanged** (M4 regression).
10. Non-rnaseq assay → no rnaseq plausibility results (strict gate, unchanged).
11. `rrna_contamination` behavior unchanged (still `unverified`).

Deterministic, stdlib-only, no network, **no real nf-core/Picard/MultiQC run in CI**.

**Test conventions to follow (verified against the suite):** plain pytest functions, `tmp_path`,
`pytest.approx`; **there is no `conftest.py` anywhere** — helpers are local per file and
deliberately duplicated (each suite defines its own 4-line `_write`). The gate convention is a
**fired + skipped pair** (`test_run_qc.py:121-144`): the positive test asserts the check and
status, the negative runs the *same* fixture under a different assay. Docstrings carry
*reasoning*, not description — e.g. `test_scrnaseq_metrics.py:98-105` is titled *"The unit
collision that would silently mis-verdict: 92.3% -> 0.923, NOT 92.3."* — which is this slice's
bug exactly, one assay over. **Baseline: `uv run pytest` → 1579 passed, 1 skipped (1580 tests,
76 files) at HEAD.**

**Which existing tests change, precisely** (do not over-delete):
- `test_run_qc.py:118` `DUP_HIGH_MQC` — **the only MultiQC fabrication of these slugs in the
  entire suite**. Re-point it; its `status == "warn"` assertion dies with the band.
- `test_rnaseq_plausibility.py:21,32,58,69,113` — synthetic **dicts** fed straight to the
  evaluator, no MultiQC involved. They test the evaluator contract, which survives. **Do not
  delete**; only the duplication ones need their band expectations updated.
- `test_rnaseq_plausibility.py:40-48,77-85` (missing → unverified) — still correct after the
  change; only the *feeding* differs.
- `test_rule_pack.py:340,349,376` and `test_methylseq_metrics.py:89,173` — **methylseq**, not
  rnaseq. Must remain untouched and green (the M8 naming/unit split).

---

## Guardrails (CLAUDE.md)

- **Layer 2 only** — verify-axis hardening. No Layer-1 drift.
- **No over-claiming** — the check now reports a number and **explicitly declines to judge it**;
  UNVERIFIED-never-PASS preserved; the false pass the scale bug would create is never introduced.
- **No guessed slugs** — the whole defect. Every slug here is cited to upstream source.
  `percent_rRNA` stays guessed **and is explicitly recorded as such**, not quietly tolerated.
- **No new dependency**; no raw-read egress; **test-first** (RED → GREEN).

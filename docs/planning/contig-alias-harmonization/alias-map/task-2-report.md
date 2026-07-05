# Task 2 report: `plan_harmonization` rewritten as a FASTA-driven rename map (Phase 2)

## What changed

`src/contig/reference_harmonize.py`:

- **`HarmonizationPlan`** (frozen dataclass) gained two fields and changed one:
  - `rename_map: dict[str, str]` — GTF seqname -> chosen FASTA seqname, renames only (entries where the GTF name already matches the FASTA are omitted).
  - `direction: str` — widened from the `Literal["add_chr","strip_chr"]` alias to plain `str`, since it can now also be `"alias"`.
  - `unmatched: tuple[str, ...]` — GTF seqnames with zero FASTA candidates (sorted, immutable).
  - `fasta_sample` / `gtf_sample` — unchanged.
- **`plan_harmonization(fasta_path, gtf_path)`** — fully rewritten per the spec's 8-step algorithm:
  1. Parse `F = fasta_contigs(...)`, `G = gtf_contigs(...)`; either empty → `None`.
  2. New helper `_prefix_variants(name)` = `{name, "chr"+name} ∪ ({name[3:]} if chr-prefixed and len>3)`.
  3. New helper `_candidate_names(g)` — the FASTA-driven closure: for every prefix-variant `v` of `g`, for every alias `a` in `alias_group(v)`, union in `_prefix_variants(a)`. This double expansion (prefix → alias → prefix) is what lets a chr-prefixed spelling like `chrMT` reach the bare mito alias-table entry `MT`↔`M` and then re-expand `M`/`MT` back through their own prefix variants (`chrM`) — see "algorithm nuance" below, this is the one place the implementation had to go beyond a literal reading of the brief's formula.
  4. For each `g in G`: `cands = _candidate_names(g) & F`. If empty → `unmatched`. Else `chosen = g if g in F else sorted(cands)[0]`; if `chosen != g`, record `rename_map[g] = chosen`.
  5. `overlap_before = |F ∩ G|`, `mapped = {rename_map.get(g,g) for g in G}`, `overlap_after = |F ∩ mapped|`.
  6. Refuse: `rename_map` empty OR `overlap_after <= overlap_before` → `None`.
  7. Explicit (redundant but commented per spec) disjoint guard: `F ∩ mapped` empty → `None`.
  8. Direction label: `"add_chr"` if every rename is exactly `chosen == "chr"+g`; `"strip_chr"` if every rename is exactly `chosen == g[3:]`; else `"alias"`.
  9. Return the plan with `unmatched` sorted into a tuple.
- Removed now-unused imports (`_all_chr_prefixed`, `check_reference_consistency` from `reference_check`); added `from contig.contig_aliases import alias_group`.
- `harmonize_gtf`, `_apply`, `_open_input`, `_open_output` — **untouched**, exactly per the Phase-3-not-now instruction.

## Algorithm nuance vs. the literal brief formula

The brief's formula was `cands = (⋃_{a ∈ alias_group(g)} prefix_variants(a)) ∩ F`. Applied literally to `g = "chrMT"` against `F = {chr1, chrM}` this produces an **empty** `cands`, because `alias_group("chrMT")` does not match anything in the alias table (the table's mito entry is bare `{"M","MT"}` only — `contig_aliases.py` intentionally has no chr-prefixed keys, per its own Phase-1 docstring). That would fail the "Pure-alias both prefixed" test case (`F={chr1,chrM}`, `G={chr1,chrMT}` → expected `rename_map=={"chrMT":"chrM"}`).

To satisfy that test (and the "Hybrid FASTA" test, which the literal formula does handle since its `g="MT"` is already a bare alias-table key), the implementation expands over `_prefix_variants(g)` **first** (so `chrMT` yields the bare form `MT` as one candidate), looks up `alias_group` on **each** of those variants, and then re-expands **each** alias through `_prefix_variants` again (so the alias `M`/`MT` also yields `chrM`/`chrMT`). This is a strict superset of the literal single-level formula (since `g ∈ _prefix_variants(g)`, the literal formula's results are always included) and was verified by hand against every listed test case before writing code.

## New/updated tests (`tests/test_reference_harmonize.py`, `TestPlanHarmonization`)

All 12 pre-existing tests in this class needed **no modification** — the new fields are additive and none of the old assertions touch `rename_map` or `unmatched`. Added 8 new tests:

- `test_ucsc_ensembl_full_alias_and_prefix_mix` — mixed prefix+alias, `direction=="alias"`, `unmatched==()`.
- `test_residual_mito_only_rename` — autosomes already match, only `MT`→`chrM` renamed.
- `test_pure_alias_both_chr_prefixed` — `chrMT`→`chrM` (the nuance case above).
- `test_hybrid_fasta_lookup_wins` — hybrid FASTA `chrMT`; bare GTF `MT` resolves to it (FASTA-lookup wins).
- `test_pure_prefix_add_still_labeled_add_chr` — legacy label preserved.
- `test_pure_prefix_strip_still_labeled_strip_chr` — legacy label preserved.
- `test_unmatched_contig_enumerated_rest_still_harmonized` — `weirdcontig` lands in `unmatched`, rest still harmonized.
- `test_wrong_assembly_no_candidates_refuses` — scaffold-only disjoint GTF → `None`.

## TDD evidence

**RED** (tests added, before touching `reference_harmonize.py`):

```
FAILED ...::test_ucsc_ensembl_full_alias_and_prefix_mix - assert None is not None
FAILED ...::test_residual_mito_only_rename
FAILED ...::test_pure_alias_both_chr_prefixed
FAILED ...::test_hybrid_fasta_lookup_wins - assert None is not None
FAILED ...::test_pure_prefix_add_still_labeled_add_chr - AttributeError: 'HarmonizationPlan' object has no attribute 'rename_map'
FAILED ...::test_unmatched_contig_enumerated_rest_still_harmonized - AttributeError: ...no attribute 'unmatched'
```
(2 of the 8 new tests — `test_pure_prefix_strip_still_labeled_strip_chr` and `test_wrong_assembly_no_candidates_refuses` — happened to pass against the old code by coincidence of old semantics; the other 6 failed as expected, confirming the tests actually exercise new behavior.)

**GREEN** — after the rewrite:

```
$ uv run pytest tests/test_reference_harmonize.py -q
..................................                                       [100%]
34 passed
```

## Full-suite result

```
$ uv run pytest
1113 passed, 1 skipped in 11.06s
```

No failures anywhere, including `test_cli.py`. Confirmed why: the existing `test_cli.py` reference-harmonization scenarios (`_write_disjoint_reference` — pure `chr1,chr2` vs `1,2`; `_write_wrong_assembly_reference` — `scaffold_1,scaffold_2` disjoint) only exercise the pure add_chr and genuine-refuse paths, both of which the rewritten `plan_harmonization` still produces identically to before (same `direction` value, same `None`). None of the cli tests hit an `"alias"`-direction scenario, so `cli.py`'s `harmonize_gtf(params["gtf"], hplan.direction, ...)` call — which only understands `"add_chr"`/`"strip_chr"` — was never exercised against the new label. This is a latent integration gap (Phase 4's job per the task brief), not a test failure.

## Commit

`feat(reference): rewrite plan_harmonization as a FASTA-driven rename map` — see git log for hash.

## Concerns

1. **cli.py latent gap (expected, not fixed here):** `cli.py` line ~465 calls `harmonize_gtf(params["gtf"], hplan.direction, harmonized_path)`. `harmonize_gtf`'s `_apply` only branches on `"add_chr"` vs. else-treated-as-`"strip_chr"`. If `plan_harmonization` ever returns `direction == "alias"` in production, `cli.py` will silently apply a `strip_chr` transform instead of the real rename map — producing wrong output, not a clean failure. No test currently exercises this path (all cli fixtures are pure-prefix), so the full suite is green, but this is a real correctness gap until Phase 3 (apply the rename map in `harmonize_gtf`) and Phase 4 (wire `cli.py` to the new shape) land. Flagging per the task brief's explicit instruction not to fix `cli.py` in this phase.
2. The `_candidate_names` double-expansion (prefix → alias → prefix) is a generalization beyond the brief's literal single-level formula; documented in code and above so Phase 3/4 authors aren't surprised by it. Verified by hand against every listed test case, not just asserted — worth a second pair of eyes given it's the trickiest part of this phase.

## Fix — injectivity guard

**Defect (from review):** `plan_harmonization`'s rename map was not guaranteed injective. Concrete repro: FASTA `{chrM, chr1}` + GTF `{M, MT}` → both `M` and `MT` resolved to `chrM`, so `rename_map == {"M": "chrM", "MT": "chrM"}`. The overlap-improvement check computed `mapped` as a *set* comprehension (`{rename_map.get(g, g) for g in gt}`), which silently collapsed the collision before it could be detected — the function happily returned a plan, and a downstream rewriter applying that map literally would silently merge two distinct contigs. Per CLAUDE.md's no-silent-failure stance, this must refuse instead of corrupt.

**Change:** in `src/contig/reference_harmonize.py::plan_harmonization`, `mapped` is now built as a list first (`mapped_list = [rename_map.get(g, g) for g in gt]`) so duplicates stay visible, with `mapped = set(mapped_list)` derived from it for the existing overlap arithmetic (unchanged). A new **Step 6b** injectivity guard, placed after the existing overlap/refuse and disjoint gates and before direction-label derivation, refuses (`return None`) whenever `len(mapped_list) != len(mapped)` — i.e. whenever two distinct source GTF seqnames would land on the same post-harmonization name. This applies uniformly: it catches both two-freshly-renamed-siblings colliding (`M`/`MT` → `chrM`) and a renamed contig colliding with one that stays unchanged (`1`→`chr1` colliding with GTF's own already-present `chr1`).

**New tests** (`tests/test_reference_harmonize.py`, class `TestPlanHarmonization`):
- `test_colliding_targets_refuse` — FASTA `{chrM, chr1}`, GTF `{M, MT}` → `plan_harmonization(...) is None`.
- `test_renamed_collides_with_staying_contig_refuses` — FASTA `{chr1}`, GTF `{1, chr1}` → `None` (this one was already refused by the pre-existing no-strict-improvement gate at Step 5, so it passed immediately, but stays as an explicit regression test for that collision shape).
- `test_distinct_targets_still_harmonize` — positive control: FASTA `{chr1, chr2, chrM}`, GTF `{1, 2, MT}` → valid plan with `rename_map == {"1": "chr1", "2": "chr2", "MT": "chrM"}` (all targets distinct; guard does not over-refuse ordinary input).

**Test-hygiene fix (also this commit):** `test_unmatched_contig_enumerated_rest_still_harmonized` tightened from `assert "weirdcontig" in plan.unmatched` to `assert plan.unmatched == ("weirdcontig",)`, asserting the exact tuple; its other assertions (`plan is not None`, exact `rename_map`) are unchanged.

**RED** (new tests against pre-fix code):

```
$ uv run pytest tests/test_reference_harmonize.py -k "colliding_targets_refuse or renamed_collides_with_staying or distinct_targets_still_harmonize or unmatched_contig_enumerated" -v
FAILED tests/test_reference_harmonize.py::TestPlanHarmonization::test_colliding_targets_refuse
  AssertionError: assert HarmonizationPlan(rename_map={'MT': 'chrM', 'M': 'chrM'}, direction='alias', ...) is None
3 passed, 1 failed
```
(`test_renamed_collides_with_staying_contig_refuses`, `test_distinct_targets_still_harmonize`, and the tightened `test_unmatched_contig_enumerated_rest_still_harmonized` already passed pre-fix; `test_colliding_targets_refuse` was the true RED, confirming the defect.)

**GREEN** (after adding the Step 6b guard):

```
$ uv run pytest tests/test_reference_harmonize.py -v
37 passed
```

**Full suite:**

```
$ uv run pytest
1116 passed, 1 skipped in 10.88s
```

(1113 baseline + 3 new tests = 1116; no regressions.)

**Commit:** `fix(reference): refuse a non-injective rename map (no silent contig merge)` — see git log for hash.

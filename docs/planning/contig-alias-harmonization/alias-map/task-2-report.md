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

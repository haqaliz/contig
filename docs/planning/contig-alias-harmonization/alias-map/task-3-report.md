# Task 3 report: `harmonize_gtf` applies the rename map (Phase 3)

## What changed

`src/contig/reference_harmonize.py`:

- **`harmonize_gtf(gtf_path, rename_map, out_path)`** — signature changed from
  `(gtf_path, direction: HarmonizationDirection, out_path)`. The streaming loop
  (gzip-transparent open/close, line-ending detection, blank/`#`-comment/no-tab
  passthrough, `line.split("\t", 1)` boundary) is **untouched**. Only the
  per-line column-1 transform changed:
  - before: `new_col1 = _apply(col1.strip(), direction)` (uniform add/strip `chr`).
  - after: `stripped_col1 = col1.strip(); new_col1 = rename_map.get(stripped_col1, stripped_col1)`
    — a direct dict lookup with identity fallback, so any contig absent from
    the map passes through unchanged.
- **`_apply`** deleted. Confirmed via `grep -rn "_apply\b" src/ tests/` (excluding
  `__pycache__`) that nothing else referenced it before deletion; grep is clean
  after deletion too.
- Docstrings (module header + `harmonize_gtf`) updated to describe the
  rename-map semantics instead of the old uniform direction.
- `HarmonizationDirection` (`Literal["add_chr","strip_chr"]`) and the
  `HarmonizationDirection` import of `Literal` are left in place — the alias
  is now otherwise unused (only self-referenced in its own definition) but
  wasn't in the required change list, so it was left rather than pulled out
  as an unrequested cleanup.

`src/contig/cli.py` — the **one** call site (was line 465):

```python
harmonize_gtf(params["gtf"], hplan.direction, harmonized_path)
```
became
```python
harmonize_gtf(params["gtf"], hplan.rename_map, harmonized_path)
```

No other line in `cli.py` changed. The suite stayed green with only this
one-line change — see "Forced cli.py changes" below.

## Tests (`tests/test_reference_harmonize.py`, `TestHarmonizeGtf`)

Reworked every existing call site from `harmonize_gtf(gtf, "add_chr"/"strip_chr", out)`
to `harmonize_gtf(gtf, {...rename_map...}, out)`, preserving every byte-fidelity
assertion (CRLF/LF preservation, comment/blank/track/browser passthrough,
gz-in→gz-out, whitespace-padded seqname parity with `gtf_contigs`, returns-Path).

New tests added:

- `test_closed_loop_alias_rename_mito` — `{"1":"chr1","MT":"chrM"}` rewrites
  the mito line's col1 to `chrM` (an alias rename, not a uniform prefix op);
  asserts the closed loop via `check_reference_consistency` and asserts the
  exact resulting col1 set.
- `test_contig_not_in_map_passes_through_unchanged` — map `{"MT":"chrM"}`
  applied to a GTF with rows `MT` and `chr1`; asserts `chr1` (absent from the
  map) is left unchanged while `MT`→`chrM`.
- `test_empty_rename_map_is_pure_passthrough` — `rename_map={}` leaves file
  contents byte-identical (`out.read_text() == content`).

Existing tests renamed in spirit only (docstrings say "rename map" instead of
"direction") but kept their original names/assertions; `test_add_chr_already_prefixed_is_idempotent`
and `test_strip_chr_already_bare_is_idempotent` now express "unmapped seqname
stays unchanged" using a single-entry rename_map that doesn't include the
input seqname, which is the closest faithful translation of the old
idempotence claim into rename-map semantics.

## TDD evidence

**RED** (tests rewritten to the new 3-arg call before touching the implementation):

```
FAILED ...::test_closed_loop_add_chr_resolves_mismatch
FAILED ...::test_closed_loop_alias_rename_mito
FAILED ...::test_contig_not_in_map_passes_through_unchanged
FAILED ...::test_empty_rename_map_is_pure_passthrough
FAILED ...::test_column_fidelity_add_chr
FAILED ...::test_gz_in_gz_out
FAILED ...::test_add_chr_already_prefixed_is_idempotent
FAILED ...::test_closed_loop_add_chr_whitespace_seqname
```
(Failures came from `check_reference_consistency` still finding a mismatch —
the old `_apply(col1, direction)` call ignored the dict passed as `direction`
and treated it as neither `"add_chr"` nor a recognized value, falling into the
`else` (strip) branch, so several tests failed on assertion rather than on a
`TypeError`; this is consistent with dict-as-direction being silently
misinterpreted, exactly the RED signal expected before the fix.)

**GREEN** — after the rewrite:

```
$ uv run pytest tests/test_reference_harmonize.py
40 passed in 0.19s
```

**Full suite:**

```
$ uv run pytest
1119 passed, 1 skipped in 10.88s
```
(was 1116 passed, 1 skipped before this task; +3 net new tests added here)

## Forced cli.py changes: none beyond the one call site

Updating only the call site at (now) line 465 —
`harmonize_gtf(params["gtf"], hplan.rename_map, harmonized_path)` — was
sufficient to keep the full suite green. No other line in `cli.py` needed to
change:

- `tests/test_cli.py::test_run_harmonize_post_check_fails_refuses` monkeypatches
  `contig.cli.harmonize_gtf` with `def broken_harmonize(gtf_path, direction, out_path)`
  — a purely positional stub that never inspects its second argument, so it is
  unaffected by the second positional argument now being a `dict` instead of a
  `str`.
- No other test or call site referenced `hplan.direction` in a way coupled to
  `harmonize_gtf`'s signature; `hplan.direction` itself (the label used for
  the user-facing "harmonized ... to match the FASTA" message and
  `harmonized_direction`/manifest persistence a few lines below the call
  site) is untouched, per the Phase-4 boundary in the brief.

# Task 4 report: drive the harmonization pre-flight from the plan, not the disjoint detector (Phase 4)

## The bug this phase kills

`check_reference_consistency` (`reference_check.py`) only flags a **fully
disjoint** FASTA/GTF pair (`fasta & gtf == set()`). It returns `[]` (no
problems) the moment the two share even one contig name. The old pre-flight
in `_dispatch_run` gated the whole harmonize attempt behind `if problems:`,
so a pair whose autosomes already match — FASTA `chr1,chr2,chrM` vs GTF
`chr1,chr2,MT` — was never even offered to `plan_harmonization`. `problems`
is `[]` (autosomes overlap), so the mito seqname (`MT` vs `chrM`) silently
stayed mismatched and Nextflow would run with a partially-broken reference.
This is the residual-mito case named in the brief.

## Control-flow restructure (`src/contig/cli.py`, in `_dispatch_run`)

Old shape (trigger = `problems`):

```python
if "fasta" in params and "gtf" in params:
    problems = check_reference_consistency(params["fasta"], params["gtf"])
    if problems:
        hplan = plan_harmonization(params["fasta"], params["gtf"])
        if hplan is not None:
            ... harmonize ...
        if hplan is None:
            ... refuse/allow using `problems` ...
```

New shape (trigger = `hplan`):

```python
if "fasta" in params and "gtf" in params:
    problems = check_reference_consistency(params["fasta"], params["gtf"])
    hplan = plan_harmonization(params["fasta"], params["gtf"])   # <- always computed
    if hplan is not None:
        ... harmonize + strengthened post-check (below) ...
        # on post-check failure: hplan = None (fall through)
    if hplan is None and problems:
        ... refuse/allow using `problems`, unchanged ...
```

`plan_harmonization` is now called unconditionally (not nested inside
`if problems:`), so the residual-mito case — `problems == []` but
`hplan is not None` — reaches the harmonize branch. The refuse/allow branch
is now gated on `hplan is None and problems`, so it still only fires for a
genuinely non-harmonizable, disjoint pair (e.g. the `scaffold_*` fixture),
exactly as before.

## Strengthened post-condition guard

The old post-check re-ran `check_reference_consistency` on the harmonized
file, which — for the same reason as above — cannot detect a no-op
harmonization when the pair already shared some contigs. Replaced with a
direct **overlap-increase** comparison:

```python
orig_overlap = len(fasta_contigs(params["fasta"]) & gtf_contigs(params["gtf"]))
post_overlap = len(fasta_contigs(params["fasta"]) & gtf_contigs(str(harmonized_path.resolve())))
if post_overlap > orig_overlap:
    # proceed with the harmonized file
else:
    # revert: discard scratch, hplan = None, fall through to refuse/allow
```

`fasta_contigs`/`gtf_contigs` are imported from `reference_check` (added to
the existing `from contig.reference_check import ...` line alongside
`check_reference_consistency`). Everything else in the harmonize branch
(scratch path `<runs_dir>/<run_id>/harmonized/<name>`, the "harmonized"
echo, `harmonized_direction = hplan.direction`, swapping `params["gtf"]` to
the harmonized path, never calling `typer.Exit` on success, the revert echo
on failure) is unchanged from Phase 3/pre-Phase-4.

`--allow-reference-mismatch` semantics are unchanged: harmonize is always
attempted first regardless of the flag; the flag only changes what happens
in the `hplan is None and problems` refuse/allow branch. Reproduce/rerun
paths (`launch.json` stores the ORIGINAL gtf, `harmonized_reference =
bool(harmonized_direction)`) were not touched.

## Tests added (`tests/test_cli.py`)

Two new fixtures:
- `_write_ucsc_ensembl_reference` — FASTA `chr1,chr2,chrM` / GTF `1,2,MT`,
  fully disjoint (`check_reference_consistency` flags it) but harmonizable
  via chr-prefix + the mito alias table.
- `_write_residual_mito_reference` — FASTA `chr1,chr2,chrM` / GTF
  `chr1,chr2,MT`; autosomes already share names so
  `check_reference_consistency` returns `[]`, but the mito seqname is still
  mismatched.

New tests:
- `test_run_ucsc_ensembl_reference_harmonizes_and_proceeds` — exit 0,
  "harmonized" in stderr, `harmonized_reference is True`, harmonized dir
  populated, `run_record.json` written.
- `test_run_residual_mito_reference_harmonizes_and_proceeds` — the case that
  proves the fix. Asserts `check_reference_consistency(fasta, gtf) == []`
  up front (proving the old gate would never have fired), then asserts the
  run exits 0, `harmonized_reference is True`, and reads the actual
  harmonized GTF file off disk to confirm the mito line changed from
  `MT\tsource\tgene\t...` (before) to `chrM\tsource\tgene\t...` (after), and
  that no `MT\tsource\tgene` line remains.

Existing tests reconciled/left as-is:
- `test_run_refuses_disjoint_reference_without_launching` and
  `test_run_allow_reference_mismatch_proceeds_and_persists_flag`
  (genuinely-disjoint `scaffold_*` fixture) — unchanged, still green: for
  that fixture `plan_harmonization` returns `None` (no candidate rename
  yields overlap), so `hplan is None and problems` still gates the
  refuse/allow path exactly as before.
- `test_run_chr_asymmetric_harmonizes_and_proceeds` and
  `test_run_chr_asymmetric_with_allow_flag_still_harmonizes` — unchanged,
  still green.
- `test_run_harmonize_post_check_fails_refuses` — **not modified**. Its
  `broken_harmonize` stub copies the ORIGINAL (unmodified) GTF content to
  `out_path`, so under the new overlap-based guard: `orig_overlap == 0`
  (the `_write_disjoint_reference` fixture is fully disjoint) and
  `post_overlap == 0` (the "harmonized" file has the same unrenamed
  seqnames). `post_overlap > orig_overlap` is `False`, so the guard still
  triggers exactly as intended — the test's assertions (non-zero exit,
  "mismatch" in output, `harmonized_reference` not persisted as `True`)
  hold unchanged. The test's intent (a harmonization attempt that doesn't
  actually resolve the mismatch must not silently proceed) is preserved by
  construction, not by adjusting the test.

## TDD evidence

RED (new tests added against the pre-restructure `if problems:` gate,
confirmed failing before the `cli.py` edit — the residual-mito test in
particular exits non-zero-or-proceeds-without-harmonizing since the old gate
never calls `plan_harmonization` when `problems == []`):

```
FAILED tests/test_cli.py::test_run_residual_mito_reference_harmonizes_and_proceeds
```

GREEN after the restructure:

```
$ uv run pytest tests/test_cli.py
130 passed in 3.46s

$ uv run pytest
1121 passed, 1 skipped in 10.87s
```
(was 1119 passed, 1 skipped before this task; +2 net new tests)

## Files touched

- `src/contig/cli.py` — pre-flight restructure in `_dispatch_run`; added
  `fasta_contigs, gtf_contigs` to the `reference_check` import.
- `tests/test_cli.py` — added `check_reference_consistency` import, two new
  fixtures, two new tests.

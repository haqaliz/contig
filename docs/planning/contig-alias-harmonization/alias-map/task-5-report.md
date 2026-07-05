# Task 5 report: enumerate still-unmatched GTF contigs in the harmonization breadcrumb (M8)

## The gap this phase closes

When Contig auto-harmonizes a FASTA/GTF contig-naming mismatch,
`plan_harmonization` already computes the ground-truth unmatched set
(`HarmonizationPlan.unmatched`: GTF seqnames with no FASTA candidate at all,
e.g. an assembly-specific scaffold or a typo'd contig). `harmonize_gtf`
passes those seqnames through **unchanged** — they are silently left
mismatched in the harmonized GTF. Before this task, the `reference_harmonized`
WARN breadcrumb said only "Reference GTF seqnames were harmonized (add_chr)
... Confirm the reference was correct." — identical wording whether 0 or 40
contigs were left unmatched. That is a relocated silent failure: the run
looks "harmonized" and merely "warn", but some genes on unmatched contigs may
never show up in the counts, with no trace of which ones.

## CRITICAL correctness decision: recompute vs. thread

Per the task brief, resolved empirically with a RED test **before** touching
`_finalize`'s logic:

`test_finalize_receives_the_harmonized_gtf_path_in_parameters` builds a real
FASTA (`chr1,chr2`) and GTF (`1,2`), runs them through the actual
`plan_harmonization` + `harmonize_gtf` (exactly as `cli.py`'s pre-flight
block does), passes `params={"fasta": ..., "gtf": str(harmonized_path)}`
into `self_heal_run`, and asserts:

```python
assert record.parameters["gtf"] == str(harmonized_path)
assert record.parameters["gtf"] != str(orig_gtf_path)
```

This test passed immediately (no code change needed) — confirming empirically
that `record.parameters["gtf"]` holds the **HARMONIZED** scratch path, not the
original. Trace: `cli.py` (`_dispatch_run`, line 497) overwrites
`params["gtf"] = str(harmonized_path.resolve())` **before** calling
`self_heal_run`; `self_heal_run` seeds `current_params = dict(params or {})`
and passes it straight through to `run_pipeline`; `runner.py` line 338 sets
`RunRecord(parameters=params or {}, ...)`. No original-path fallback exists
anywhere in that chain.

**Decision: RECOMPUTE in `_finalize`**, per the brief's licensed option —
because the harmonized GTF has already renamed every matchable contig to its
FASTA spelling, whatever GTF seqname remains outside the FASTA contig set
*is* exactly `HarmonizationPlan.unmatched`. Threading `hplan.unmatched`
through the ~10 pass-through call sites of `harmonized_reference_direction`
in `self_heal.py` would have been pure duplication of information already
recoverable from data already in hand. No changes to `cli.py` were needed
(mirrors the brief's "touch cli.py only if the threading fallback is
needed").

## Implementation (`src/contig/self_heal.py`)

New pure helper, adjacent to `_finalize`:

```python
def _unmatched_harmonized_contigs(params: dict[str, object]) -> list[str]:
    fasta = params.get("fasta")
    gtf = params.get("gtf")
    if not fasta or not gtf:
        return []
    try:
        return sorted(gtf_contigs(gtf) - fasta_contigs(fasta))
    except OSError:
        return []
```

`fasta_contigs`/`gtf_contigs` imported from `contig.reference_check`
(alphabetically slotted between the existing `notify` and `repair` imports).
Degrades to `[]` on missing/unreadable paths — same "never crash, never
fabricate" posture as `compute_reference_identity`'s `_hash` helper; this is
what keeps the pre-existing fake-path tests
(`params={"fasta": "/fake/ref.fa", "gtf": "/fake/ref.gtf"}`) green.

`_finalize`'s WARN-breadcrumb branch now builds the message conditionally:

```python
unmatched = _unmatched_harmonized_contigs(record.parameters)
message = (
    f"Reference harmonized ({harmonized_reference_direction}) to match "
    f"the FASTA before the run. "
)
if unmatched:
    names = ", ".join(unmatched)
    message += (
        f"Note: {len(unmatched)} GTF contig(s) could not be matched to "
        f"the FASTA and were left as-is: {names}. "
    )
message += "Confirm the reference was correct."
```

Message shape now matches the brief's example exactly when unmatched
contigs exist, e.g.: `"Reference harmonized (add_chr) to match the FASTA
before the run. Note: 1 GTF contig(s) could not be matched to the FASTA and
were left as-is: weirdcontig. Confirm the reference was correct."` — and
collapses to the clean, pre-existing-style sentence when `unmatched == []`.

The wording changed slightly from "Reference GTF seqnames were harmonized"
to "Reference harmonized" (plain-language per M8); grepped the repo first —
no other code or test hard-codes the old exact string, only
`check == "reference_harmonized"` and substring checks like `"add_chr" in
message`, both still satisfied.

## Tests added (`tests/test_self_heal.py`)

New fixture helpers: `_write_fasta(path, names)`, `_write_gtf(path, names)` —
minimal real FASTA/GTF files (not fakes) so `plan_harmonization` /
`harmonize_gtf` run for real, mirroring what `cli.py` actually produces.

- `test_finalize_receives_the_harmonized_gtf_path_in_parameters` — the
  decision test described above (passed immediately; confirms the ground
  truth that licensed the recompute approach).
- `test_finalize_harmonized_warn_message_lists_unmatched_contig` — FASTA
  `chr1,chr2` / GTF `1,2,weirdcontig`; asserts `hplan.unmatched ==
  ("weirdcontig",)`, then asserts the WARN message contains `"weirdcontig"`,
  `"could not be matched"`, and the count `"1"`. Also re-asserts the
  pre-existing invariants (`reference_identity.harmonized is True`,
  `harmonized_direction` recorded, `verdict == "warn"`).
- `test_finalize_harmonized_warn_message_omits_clause_when_fully_matched` —
  FASTA/GTF where every contig matches (`hplan.unmatched == ()`); asserts
  `"could not be matched" not in message` and the direction label is still
  present.

## TDD evidence

RED (before the `self_heal.py` edit):

```
$ uv run pytest tests/test_self_heal.py -k "finalize_receives_the_harmonized or finalize_harmonized_warn_message" -v
tests/test_self_heal.py .F.
FAILED tests/test_self_heal.py::test_finalize_harmonized_warn_message_lists_unmatched_contig
AssertionError: assert 'weirdcontig' in 'Reference GTF seqnames were harmonized (add_chr) to match the FASTA before the run. Confirm the reference was correct.'
1 failed, 2 passed
```

(The "receives the harmonized path" and "omits clause when fully matched"
tests passed pre-edit, as expected — they assert pre-existing behavior /
the decision, not the new feature.)

GREEN after the `self_heal.py` edit:

```
$ uv run pytest tests/test_self_heal.py
120 passed in 0.25s

$ uv run pytest
1124 passed, 1 skipped in 10.89s
```

(was 1121 passed, 1 skipped before this task; +3 net new tests, all existing
tests — including both pre-existing `_finalize` breadcrumb tests — still
green unchanged.)

## Files touched

- `src/contig/self_heal.py` — added `_unmatched_harmonized_contigs` helper;
  added `fasta_contigs, gtf_contigs` import from `contig.reference_check`;
  updated the `reference_harmonized` WARN message construction in
  `_finalize`.
- `tests/test_self_heal.py` — added `_write_fasta`/`_write_gtf` fixture
  helpers and three new tests (see above).
- `cli.py` — **not touched**: the recompute approach needed no threading.

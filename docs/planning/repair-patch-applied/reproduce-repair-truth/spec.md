# Aspect spec — `reproduce-repair-truth`

## Problem slice

`ReproduceRecord.repair_history` (`models.py:684`) holds the **same** `RepairStep` type as
`RunRecord`. The `contig reproduce --allow-install` env-resurrection loop constructs three of
them (`verification/reproduce.py:1236-1268`) with literals the filed follow-up never listed.
If this aspect is skipped, those three steps silently take the `False` default — inventing a
**new** dishonesty inside the surface this feature exists to fix.

## In scope (R3)

Set `patch_applied` truthfully at the three sites. The truth is `install_rc == 0` — did the
patch's operation (`{"install": module}`) actually run:

| Site | outcome | value | why |
|---|---|---|---|
| `:1236` | `install_failed` | `False` | `pip install` exited non-zero; nothing was installed |
| `:1251` | `retry_failed` | **`True`** | the install **succeeded**; the retried run then failed |
| `:1261` | `installed_and_retried` | `True` | installed, retry exited 0 |

`retry_failed` is the canonical demonstration of the D2 semantics: **applied ≠ successful.**
A test on it is mandatory, not optional — it is the case a careless reading gets wrong.

## Out of scope

The `missing_dependency` literal stays reproduce-local (it is deliberately not wired into the
shared `diagnose_failure`, so the C6 eval-guard baseline stays unmoved — do not change that).
No change to `classify`, `ClaimResult`, the bundle, signing, `--fail-on-diverged`, or any exit
code. No new locator, flag, or dependency.

## Acceptance criteria (testable)

1. A scripted installer returning non-zero → the recorded step has `outcome="install_failed"`
   and `patch_applied is False`, with `patch` still non-null.
2. A scripted installer returning 0 + a scripted executor whose retry still fails → the step
   has `outcome="retry_failed"` and `patch_applied is True`.
3. Installer 0 + retry 0 → `installed_and_retried`, `True`.
4. The value round-trips through the signed reproduce bundle and `reproduce.json`.
5. `report.py:95-97`'s `env-repair:` line still renders (no regression); whether it *shows*
   the new distinction is R11 and belongs to the dashboard aspect.
6. `uv run pytest tests/test_reproduce.py` and the full suite green. No real pip, network, or
   repo in CI — use the existing scripted `Installer`/executor seams.

## Dependencies and sequencing

Depends on `patch-applied-field` (the model field must exist). Independent of the other two
siblings; can run in parallel with them.

## Risks specific to this aspect

- Getting `retry_failed` backwards is the single most likely error, and it would encode the
  exact confusion (applied vs successful) the feature exists to remove.
- `ReproduceRecord`'s signature already broke in the field aspect (shared model); do not add a
  second break test here — one is enough, and it lives with the field.

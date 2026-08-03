---

## ⚠️ The design decision this plan turns on — read before Phase 1

`patch_applied` is sourced **solely** from `_apply_patch_and_maybe_build`'s `continue_`, at its
three call sites in `self_heal.py::self_heal_run` (auto-approve `:1244-1262`, choice-gate approve
`:1292-1307`, single-gate approve `:1348-1367`). That was v0.49.0's whole point: correct by
construction, not by review.

But this feature needs **`patch_applied=False` AND a retry** on an approved advisory — and
today those are the same boolean. `cont=False` would correctly mark nothing-enacted but would
also skip the retry the human just approved; `cont=True` would retry but re-assert enactment.

**Resolution: an advisory never enters the applier at all.**

- Handle advisories on their own branch in `self_heal_run`, **before** the auto-approve and
  gate logic, so `_apply_patch_and_maybe_build` is never called and there is no `cont` to
  mis-source. Its 5-tuple is unchanged.
- `apply_patch` gains a defensive advisory branch that **raises** (never silently no-ops), so
  an advisory reaching the applier is a loud bug, not a quiet re-enactment.
- Structural guarantee is preserved by a different mechanism than v0.49.0's, so it must be
  pinned by its own test (Phase 1 RED #4): **no code path can produce
  `patch_applied=True` for a `kind="advisory"` patch.**

Rejected alternative: widening the tuple to 6 (`cont`, `applied`). It decouples cleanly but
touches all 11 `_record_attempt` sites and every build/recompress return, for four classes
that never fire. Revisit only if a second advisory-like kind appears.

---

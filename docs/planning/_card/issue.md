# Card: feat / inert-repair-honesty

- **Type:** feat
- **Id/slug:** `inert-repair-honesty`
- **Owner:** aliz
- **Branch:** `feat/inert-repair-honesty/aliz`
- **Source:** inline brief (no GitHub issue — the tracker returns "No Issues", confirmed on
  the two prior cards) — carried from the `/contig-next` recommendation (2026-08-03), the
  next slice after `heal-scenarios-catalog-coverage` merged.

## Brief

Resolve the five **INERT** repair strategies that C2 names as its highest-value outstanding
item (`docs/technical/CAPABILITY_ROADMAP.md:453-479`, `FEATURES.md:251`):

| Class | Patch operation | Kind | Site |
|---|---|---|---|
| `disk_full` | `{"clean_work_dir": True}` | `env` | `repair.py:145` |
| `permission_denied` | `{"fix_permissions": True}` | `env` | `repair.py:169` |
| `conda_solve_failed` | `{"relax_or_pin_env": True}` | `env` | `repair.py:123` |
| `platform_unsupported` | `{"use_native_arch_backend": True}` | `env` | `repair.py:109` |
| `container_unavailable` | `{"retry": True, "wait_seconds": 15}` | **`retry`** | `repair.py:50` |

The four `kind="env"` operations are string-merged into `target.backend_options`
(`self_heal.py:583-586`), out of which `nfconfig.py:71-98` reads only
`queue`/`region`/`partition`/`account`/`qos`/`time` — so they are consumed by **nothing**.
The fifth is inert for a **different reason, kept distinct rather than flattened**:
`apply_patch` is a *documented* no-op for `kind="retry"` patches, so the promised
`wait_seconds: 15` never reaches `backend_options` at all.

Today each records propose → "apply" → `patch_applied=True` → retry → **`Repaired`** while
its stated operation is performed by nothing. That is **one layer below** the bug v0.49.0's
`patch_applied` slice fixed: the flag is now honest about *enactment*, but enacting a no-op
still renders as a repair on every surface.

### The first question is propose-vs-don't, NOT how-to-implement

This is the brief's explicit framing, not a detail to settle during implementation:

- `repair.py:166-168` already says of `permission_denied` that *"only a human can decide and
  do that safely"*.
- `platform_unsupported`'s own rationale says re-running here won't help — so the approved
  retry re-runs on the same host the patch itself calls hopeless.
- `container_unavailable` likely **splits** from the other four: a bare retry is a legitimate
  fix for a transient runtime outage, so only its *decorative field* (`wait_seconds`) is
  dishonest, not its premise. It may collapse into what `container_pull_failed` already does.

For several of these the honest fix may be to **stop proposing** and give up cleanly, not to
build the operation.

### Expected CI signal — the trigger firing as designed

`tests/test_repair.py:230::test_five_inert_patch_operations_are_still_consumed_by_nothing`
asserts each operation is still emitted by `repair.py` **and** referenced nowhere else in
`src/contig/`. It turns **red** the moment any of the five is implemented or withdrawn. That
is the committed revisit trigger firing **as designed**
(`docs/technical/CAPABILITY_ROADMAP.md:1281-1286`) — its failure message names this trigger.
It must be updated in the **same commit**, with the deferral reason revisited there.

### Downstream unlock

Once behavior is corrected, the five classes become coverable by `heal-guard` **for free**
against the corrected behavior — which is precisely why the C6 catalog-coverage slice
deliberately left them uncovered rather than freezing five suspect expectations into CI
(`docs/technical/CAPABILITY_ROADMAP.md:474-476`).

## Grounding gathered at pick time (`/contig-next`)

- `FEATURES.md:251` — verbatim: *"**five repair strategies are INERT and are the
  highest-value C2 item outstanding**"*, with propose-vs-don't named as the first question.
- `docs/technical/CAPABILITY_ROADMAP.md:453` — C2's deferral list opens with *"Deferred, and
  the highest-value of these — the five INERT repair strategies (filed by the C6
  catalog-coverage slice against C2)."*
- `docs/planning/heal-scenarios-catalog-coverage/understanding.md` — the dig that **found**
  this, with the per-class inertness table and the scriptability analysis. Two findings carry
  forward: (a) `disk_full`/`permission_denied` need **no** filesystem fixture because nothing
  measures disk or touches permissions — *"a fixture there would be theater"*; (b)
  `platform_unsupported` is unreachable through the `heal-guard` driver because
  `detect.py:355` needs a failed event with `exit is None` while `AttemptSpec.exit` is a
  required `int` (`models.py:543`) — reaching it needs an additive model/driver change.
- Verified live at pick time: `clean_work_dir`, `fix_permissions`, `relax_or_pin_env`,
  `use_native_arch_backend` appear in `src/contig/` **only** at their `repair.py` emit site
  plus the `cli.py:2696-2704` honest-scope docstring. Nothing consumes them.
- `docs/planning/repair-patch-applied/` — v0.49.0, the layer directly above this bug.

## Honest framing carried from the handoff

- **Push, not demand-pull.** No user asked; the organic frequency of these five classes is
  **unmeasured**. Revisit trigger (b) at `docs/technical/CAPABILITY_ROADMAP.md:1287-1291`
  says to group the pending corpus by `failure_class` over the next 20 runs rather than
  adding breadth on push alone — so **check the pending corpus before assuming these are
  common**. Precedent for that discipline: the `qc_anomaly` slice's honest "0 of 17 recorded
  runs".
- Guardrails: squarely **Layer 2** (self-heal), no wet-lab/clinical dependency, nothing that
  authors pipelines from English. See `CLAUDE.md`.

## Open questions for the dig

1. Which of the five should **stop proposing** vs. be **genuinely enacted**? (Per-class, with
   a stated reason each — not one undifferentiated verdict.)
2. Where would an enacted operation actually belong? `backend_options` is demonstrably the
   wrong seam for all four `env` ops.
3. What is the honest terminal outcome for a withdrawn class — a new outcome literal, or the
   existing `gave_up`? What do the surfaces (`Repaired` badge, reports, `heal-guard`
   `recovered`) then render?
4. Does `container_unavailable` collapse into `container_pull_failed`, or keep a distinct
   identity with a real wait?
5. What does the pending corpus actually say about organic frequency?
6. Is a `FailureClass`/outcome-literal change a **signature break**? (v0.49.0 was the fourth
   disclosed one — this must be checked, not assumed.)

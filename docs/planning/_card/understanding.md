# Understanding — reproduce-locator-inference (Phase-2 dig)

Grounded in the Phase-1 card (`docs/planning/_card/issue.md`) and a two-agent code map.
Every claim below carries a verified `file:line`. Baseline: worktree suite green (exit 0).

---

## What the work is really asking

`contig extract-claims` (`cli.py:1398`) turns a paper into a **locator-less** draft —
`{"id","value","tolerance"}` per claim (`cli.py:1574`) — and a `.review.md` sidecar telling
the human to hand-add a locator. `contig reproduce` then binds each claim through one of
five shipped resolvers. **The hand-add step is the only manual link in the paper → verdict
chain**, and this slice automates it: given a repo, search its output artifacts for each
claim's stated value and propose the locator that would bind it.

It is the **inverse** of the resolvers, and it reuses them rather than adding parsers.

---

## The contradiction this slice must answer (do not paper over)

`CHANGELOG.md:1618-1622` records locator-lessness as a **principled** choice, not only a
deferral:

> "the paper gives the *value*, not *where it lives in the repo's output*, so **inventing a
> `from`/`path` locator would be dishonest**; the user adds the locator during review."

That objection is correct **as stated** and this slice does not overturn it. It sidesteps it:
we never infer a locator *from the paper* (that would be invention). We search the repo's
**actual artifacts** for the claim's value and propose a binding site only on unambiguous
evidence — 0 or >1 candidates ⇒ emit nothing. **Evidence-gated search, not guessing.**
The PRD must state this in these terms, because the shipped CHANGELOG is on record against
the naive reading.

---

## The freshness "tension" dissolves on inspection — a finding, not a mitigation

The card worried that inference reads mtime-stale artifacts the freshness guard refuses to
bind. The dig shows the two **cannot** interact:

**`_require_fresh` is a closure nested inside `run_reproduction` (`reproduce.py:890`), not a
module-level function. It is not importable.** It closes over `run_started_at`
(`reproduce.py:853`), compares `st_mtime < run_started_at` (mtime *equal* passes), raises
`ValueError` rather than degrading when the stamp is `None` (`:920-921` — a None meaning
"guard off" would silently disable a false-pass guard), and returns FRESH on `stat()` OSError
(`:925-926`) so the caller owns the missing/unreadable message. Five call sites, all inside
`run_reproduction`: `:948` `:1011` `:1080` (file mode only) `:1180` `:1333`.

So inference — a pre-run, out-of-engine pass — **structurally cannot touch the guard, even by
accident.** The honest framing: inference proposes a *binding site*; the value it matched
during inference is never evidence and never reaches a verdict; a locator only becomes a
verdict when a fresh run rebinds it under the wholly unchanged guard. This should be pinned
by a test (inferred locator over a stale artifact ⇒ still UNVERIFIED at reproduce time).

---

## THE scope decision: the four families do not invert equally

| family | inverse | tractable? |
|---|---|---|
| JSON `path` | walk structure, enumerate `(path_expr, numeric)` | **Yes** — coordinate enumeration |
| table `column`+`row` | enumerate cells → `(column,row)` | **Yes** — coordinate enumeration |
| `pattern` | **synthesize a regex** | **Hard** |
| notebook `cell`+`pattern` | cell index is enumerable, but still needs a regex | **Hard** |

The coordinate for JSON/table is *read off the artifact*. For `pattern`/notebook there is no
coordinate — a regex must be **authored**, and it collides with `resolve_match`'s strict
exactly-one rule (`reproduce.py:368`, `!= 1` at `:408`): a synthesized regex that matches
twice binds to nothing, and busy log files are exactly where double matches live.

**Recommendation: v1 infers JSON + table only; `pattern`/notebook deferred with the blocker
named.** The card's brief listed four families as one job — that was my error and is
corrected here. Decision belongs to the user at the PRD gate.

---

## Percentage scale — a real honesty problem, not a detail

`ExtractedClaim.value` holds the **raw** percentage (`87`, never `0.87`,
`claim_extraction.py:32-52`); a repo's `results.json` may store `0.87`. The shipped sidecar
punts this to the human ("reconcile any `%` scale"); inference has no human in that loop, so
a naive match **silently binds nothing for every percentage claim** — indistinguishable from
"no candidate found", which is the worst failure mode available.
Proposed rule: try both `v` and `v/100`, and **report which matched** in the sidecar. Never
silently rescale. Needs a decision.

Related trap: `_DEFAULT_TOLERANCE` is defined **twice** — `claim_extraction.py:29` and
`reproduce.py:42` — two independent constants that merely agree at `0.1`. Matching tolerance
must pick one deliberately.

---

## What inference must not break

**`load_claims` validation is stricter than the brief assumed** (`reproduce.py:538`, ten xor
rejections `:590-:787`). Traps for emitted locators:
- `header`/`delimiter` count as table fields **on their own** → a partial table locator trips
  `:703`/`:590` and the round-trip invariant then kills the **whole** draft
  (`cli.py:1592-1597`, exit 1). **Emit complete locators or none.**
- `column` xor `row` rejected `:703`; `cell` requires both `from` and `pattern` `:609/:613`.
- `pattern` **with** `from` = file mode; **without** = stdout mode (`PatternLocator.source=None`).
- `re.compile` runs **at load time** (`:658-663`, `:682-687`) — any synthesized regex must
  compile or nothing loads.
- Unknown keys are ignored unless one of the eight locator keys — but keep provenance in the
  **sidecar**, per the shipped schema-minimal design.

**No `models.py` change — confirmed by construction.** All five types are frozen dataclasses
local to `verification/reproduce.py`: `Locator` `:157`, `TableLocator` `:170`,
`PatternLocator` `:189`, `NotebookLocator` `:204`, `Claim` `:519`.

**Two dispatch chains exist** — engine `reproduce.py:1343-1355` and
`reproduce_guard.py:88-95` (`claim_family`). We add no family, but anything inference emits
must classify correctly in both; cheap test, easy to miss.

---

## Security: the containment guard is not importable either

There is **no named containment function**. It is an inline four-line idiom duplicated at two
layers with *different* wording:
- **CLI pre-run** `cli.py:1219-1231` → stderr + `typer.Exit(1)`: **no run, no record.**
  (Sibling `--results` check `:1175-1179`. Intent documented `:1213-1220`.)
- **Engine observe-time**, verbatim ×4: `:939-943` `:1005-1009` `:1074-1078` `:1159-1163`
  → `(None, msg)` ⇒ claim `unverified`, run still happens.

Inference **walks a repo** to enumerate candidates, so it needs the same discipline and
cannot import it. Two options for the tech plan:
- **(a)** copy the idiom a third time — minimal blast radius, consistent with the repo, but
  triples duplication of a security check;
- **(b)** extract one pure helper and route all three through it — cleaner, but refactors
  shipped, verified code paths.
There **is** an importable precedent for safe walking: `compute_tree_sha256`'s discipline
(`os.walk(followlinks=False)`, prune `.git` at any depth, skip symlinks) — inference's file
enumeration should mirror it.

---

## Ambiguity rule (inherited, non-negotiable)

Mirror `resolve_match`: 0 and >1 collapse into **one branch that names the count**
(`reproduce.py:408`). Inference emits **no** locator in both cases and records the count in
the sidecar. Never an arbitrary pick. Also mirror the repo-wide `bool`-rejection idiom
(`isinstance(x,int) and not isinstance(x,bool)`) and never-raise discipline.

---

## Open questions for the requirements interview

1. **Surface.** `extract-claims` has exactly one positional, `paper` (`cli.py:1398`) — **no
   repo argument**. So: new `--repo` flag, or a separate `contig infer-locators <repo>
   <claims.json>`? Recommend the latter: keeps extraction paper-only, re-runnable against a
   repo fetched later, composes with hand-written drafts.
2. **Family scope.** JSON + table only in v1? (Recommend yes.)
3. **Percentage scale.** Try-both-and-report, or refuse to guess?
4. **Containment guard.** Copy the idiom (a) or extract a shared helper (b)?
5. **Match tolerance.** Exact float equality, or the claim's own `tolerance`? (Exact-ish
   matching risks missing rounded paper values; tolerant matching risks ambiguity.)

## Guardrail check (CLAUDE.md)

Layer 2 throughout (reproduce/verify), no Layer-1 authoring, no wet-lab/clinical dependency,
no new runtime dependency (stdlib only), no raw-read egress (local filesystem only).
**Clean.**

## Output surfaces (dig complete)

**Draft JSON writer** `cli.py:1572-1578` — top-level list, exactly three keys in insertion
order `{"id","value","tolerance"}`, `indent=2`, one trailing `\n`.

> **A deliberate tripwire guards it.** `tests/test_cli_extract_claims.py:104` asserts
> `set(entry.keys()) == {"id","value","tolerance"}` — an **exact-set** assert whose stated
> purpose is that adding a key breaks it. So **writing locator keys into the shipped draft
> is a disclosed contract change**, not a free extension. This is independent evidence for
> the separate-command surface (Q1): `contig infer-locators` writing its **own** output
> leaves the extract-claims contract and its tripwire untouched.

**Review sidecar** — `_review_sidecar(claims, source=None) -> str` `cli.py:1340`, body
`:1354-1394`, `lines: list[str]` + `"\n".join`. Filename rule `:1603-1606` (`.json` →
`.review.md`, else append). **Two templates, not one**: the empty-extraction note `:1608-1615`
is a separate inline string.
- Natural insertion point for inference results: inside `for claim in claims:`, after
  `- source:` and before the trailing `lines.append("")`.
- **Latent shadowing bug at `cli.py:1391`**: the loop rebinds the `source` *parameter*.
  Harmless today (the `Source:` header is emitted before the loop) but anything added
  **after** the loop that reads `source` silently gets the last claim's sentence. Rename the
  loop-local if this function is touched.
- Fixed per-claim order: `### <id>[flag]`, `- value:`, `- unit:`, `- origin:`, `- source:`.
  Placeholder is `—` (U+2014); prose uses ASCII `--`.

**The `%` problem is already documented in the shipped sidecar** (`cli.py:1354-1394`), which
devotes a paragraph to telling the human to reconcile `87` against a repo's `0.87`. That
raises the stakes on Q3 rather than lowering them: the shipped design **explicitly delegated
scale reconciliation to the human**, and inference removes the human from that step.

## Test conventions (dig complete)

**No fixture repo tree exists anywhere.** `tests/fixtures/` holds nine nf-core QC report
files only — no `results.json`, no `.csv`, no `.ipynb`, no `.log`. **Every** reproduce/locator
test builds its tree inline in `tmp_path`:
- `tests/test_reproduce.py:109` `_write(tmp_path, name, content)`; JSON/TSV/CSV inline
  `:306-600`, incl. `.tsv.gz`/`.csv.gz` variants `:358`/`:368`.
- `tests/test_reproduce_notebook_locator.py:28-60` — cleanest builder set to imitate
  (`_stdout`/`_stderr`/`_result`/`_display`/`_error`/`_code`/`_doc`).

So the brief's "real fixture repos in CI" is satisfied either way (inline builders write real
files). **Q6 (new):** inline builders — the house idiom, 100% of existing reproduce tests — or
the repo's **first** `tests/fixtures/<repo>/` tree? Inline is consistent; a fixture tree buys
one realistic multi-file repo for a single inference *sweep*, which inline builders make
verbose. Inference is the first feature that walks a whole repo, so this is a genuine question
rather than a style preference.

Standing rules inference tests must observe: never-raises tested with wild inputs
(`test_claim_extraction.py:187`); CLI flags asserted by **introspecting Click params**, never
by scraping `--help` (`test_cli_extract_claims.py:285-295` — the repo's anti-flake rule).

**Id stability caveat:** `merge_claims` re-uniquifies ids across the merged set
(`claim_extraction.py:445-457`), so draft ids are **not** stable across toggling the LLM
assist. Inference keyed by claim id is fine against a *fixed* draft file, but the sidecar
should not imply ids are durable across regeneration.

Other pinned assertions any edit must not break: `test_cli_extract_claims.py:91`, `:137`,
`:281-282`.

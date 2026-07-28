# Understanding — reproduce-checkout-hash (C8 slice 8)

Phase-2 dig note. Grounds the PRD interview. All file:line refs are in this worktree.

## What the work is really asking

Close slice 6's disclosed gap (`CAPABILITY_ROADMAP.md:1373-1376`): the fetched
`source/` checkout is recorded by commit SHA but is itself **unhashed and
unsigned**, so it "can be modified afterwards with nothing detecting it." Slice 8
records a deterministic content hash of the checkout tree on the reproduce bundle
so the bytes are attested/tamper-evident, not just the nominal commit.

This is pure Layer-2 reproducibility-integrity work (moat #1), stdlib-only
(`hashlib`), and — unusually for C8 — **CI-observable** (fixture tree → hash →
mutate → detect; no real git/network needed).

## Affected code (map from the dig)

- **CLI** `cli.py:716-994` — `reproduce` command. Preamble validation
  `:817-934`; `fetch_repo(...)` at `:944-952` (clone or `--rev` targeted fetch, the
  first disk write); `claims_sha256`/`created_at` `:954-955`; **run-start stamp
  `run_started_at = time.time()` at `:962`**; `run_reproduction(...)` `:964-976`;
  remote-only `model_copy(update={repo, source_url, source_commit})` `:977-987`;
  `write_reproduce_bundle(record, ..., requested_rev=rev)` `:989`.
- **Engine** `verification/reproduce.py:838-1435` — `run_reproduction`; the
  `--allow-install` retry-once is **inside** the engine at `:1217-1270` (second
  executor call `:1248`), i.e. strictly **after** the CLI's `:962` stamp.
- **Freshness guard** `reproduce.py:880-919` — `_require_fresh`; stamp threaded as
  the `run_started_at` param, captured by closures, not re-stamped on retry.
- **Model** `models.py:662-680` — `ReproduceRecord`; additive back-compat fields
  end at `source_url`/`source_commit` (`:679-680`, both `str | None = None`).
- **Bundle** `bundle.py:72-112` — `write_reproduce_bundle(record, dest, *,
  requested_rev=None)`; writes the **signed** `reproduce_record.json` (`:96-98`)
  then the **unsigned** `reproduce.json` manifest (`:100-110`). `requested_rev`
  (slice 7) lives **only** in the unsigned manifest.
- **Signing** `signing.py:55-64` — `canonical_record_bytes` = `model_dump(mode=
  "json")` with **no field exclusion**, so *any* new signed field changes the
  canonical bytes and breaks every prior signature.
- **Reuse target** `bundle.py:303-318` — `compute_output_checksums`: `rglob("*")` →
  filter `is_file()` → **sorted** → key `path.relative_to(root).as_posix()` → value
  `sha256_file(path)` (`models.py:17-23`). The tree-hash walk should mirror this and
  fold per-file digests into one top-level digest. `.git/` exclusion, symlink
  handling, and unreadable-file degradation (`None`, never fabricate — cf.
  `compute_reference_identity`) are the sub-decisions.
- **Tests** `tests/test_reproduce_rev_pin.py` (esp. `:517`
  `test_requested_rev_does_not_change_the_signature`) and
  `tests/test_reproduce_env_resurrection.py:235-254` (retry binds post-retry output,
  not the stale file) are the two templates to mirror.

## The three open questions (with recommendations)

### Q1 — Signed vs unsigned placement  ⟵ the load-bearing decision, needs the user

The tension the card flags, sharpened by the dig:

- **Signed** (`source_tree_sha256` on `ReproduceRecord`, `models.py:680`): genuinely
  **tamper-evident** — an editor who changes `source/` cannot silently change a
  signed hash. This matches the slice-6 **precedent**, which put
  `source_url`/`source_commit` on the *signed* record precisely because provenance
  should be attested, accepting the break. Cost: a **third consecutive** signature
  break — every pre-slice-8 *signed* reproduce bundle stops verifying (still loads).
  Bounded: signing is opt-in via `CONTIG_SIGNING_KEY`.
- **Unsigned** (`reproduce.json` only, mirroring slice 7's `requested_rev`): **zero**
  signature break. Cost: the hash is a content-address for third-party
  recomputation but is **not itself attested** — a malicious bundle editor can
  rewrite both `source/` and the unsigned hash. slice 7 chose this for
  `requested_rev` because that is "what you asked for," not "what you got."

The distinction that decides it: a tree hash is like `source_commit` ("what
actually was") — attestation-worthy — **not** like `requested_rev`. By the slice-6
precedent that argues **signed**. Against it: three breaks in three releases is a
real smell, and there is no escape (an `exclude_none` canonicalization would break
`RunRecord` too — strictly worse). **This is a genuine product call — take it to the
user.** Provisional lean: **signed**, because an unsigned "tamper-evidence" field is
close to self-defeating; but the user may prefer to stop the signature-break streak.

### Q2 — What tree, and when hashed  (recommend, confirm in interview)

**Recommend: hash the checkout tree right after `fetch_repo` succeeds and before the
`:962` run-start stamp**, over `repo_path` (the `source/` checkout).

- Captures the source **as checked out** — the cleanest attestation that the tree
  matches `source_commit` — and **sidesteps the `--allow-install` retry mutation
  entirely** (the retry is inside `run_reproduction`, after `:962`).
- A post-run hash would fold in run-generated outputs + retry effects, muddying
  "attest the source." Pin the pre-run choice with a retry-mutation test modeled on
  `test_reproduce_env_resurrection.py:235`.

### Q3 — Scope: remote-only vs also local  (recommend, confirm in interview)

**Recommend: remote/fetched checkouts only** for this slice.

- The disclosed gap is specifically about the fetched `source/` tree. A remote
  checkout is a bounded shallow clone under the bundle; a local `repo` path is
  dirty-by-design, unbounded, and often full of unrelated files (`.venv/`, data,
  outputs) — noisy and expensive to hash, lower attestation value (no commit anyway).
- Populate the field only on the `repo_argument.kind == "remote"` branch alongside
  `source_url`/`source_commit` (`cli.py:945-952` / `:977-987`). Local-repo tree
  hashing is a noted deferral.

## Sub-decisions to settle in the PRD (not user-facing)

- Tree-walk determinism: sorted POSIX-relative paths; fold `"relpath\0hex\n"` lines
  into one `sha256`. Reuse `compute_output_checksums` shape (`bundle.py:303`).
- `.git/` **excluded** (metadata, not content; huge, non-deterministic).
- Symlinks: follow the file or record the link target? Lean: skip/record honestly,
  never traverse out of tree (defense-in-depth, cf. the locator containment guards).
- Unreadable file: degrade honestly (the whole hash → `None`, or an error note),
  never fabricate — mirror `compute_reference_identity`'s `None`-on-error.
- New helper `compute_tree_sha256(root)` in `bundle.py` next to
  `compute_output_checksums`.

## Guardrails check

Layer-2 reproducibility integrity ✓ · no NL→workflow ✓ · no wet-lab/clinical ✓ ·
stdlib-only (`hashlib`) ✓ · UNVERIFIED-never-PASS honesty posture preserved (an
unreadable/absent tree degrades honestly, never a fabricated hash) ✓.

## No contradictions found

The card's "bytes that actually ran" phrasing resolves cleanly to "the source tree
as checked out to run" (Q2 pre-run). No conflict between the brief and the code.

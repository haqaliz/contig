# Card: feat reproduce-remote-intake (C8, slice 6)

**Type:** feat · **Owner:** aliz · **Branch:** `feat/reproduce-remote-intake/aliz`

No GitHub issue — this unit of work came from `/contig-next` (cn), 2026-07-23. The
recommendation below is the source brief.

## Brief

C8 slice 6: teach `contig reproduce` to take a **remote git/HTTPS repo URL** as its `repo`
argument (today `cli.py:715` is local-path-only: `repo: str = "Path to the local repo to
reproduce"`), fetching it into a run-scoped directory, recording the resolved **commit SHA**
on the `ReproduceRecord`/bundle so a remote reproduction is itself re-runnable, then handing
the working tree to the unchanged existing engine — locators, freshness guard,
`--allow-install`, signing, and `--fail-on-diverged` all reused, not forked.

Fetching must sit behind an **injectable seam** (mirroring `runner.Installer` /
`runner.IndexBuilder`) so CI stays network-free and tests use a scripted fetcher over on-disk
fixtures; a local path must keep behaving byte-identically.

**Caveats to design around up front:**

1. This makes Contig fetch code it then executes. Gate the remote path behind an explicit
   opt-in flag in the `--allow-install` spirit, and contain the checkout inside the runs dir.
2. **Scope DOI resolution out of this slice** — a DOI→repo mapping is heuristic (landing page,
   sometimes Zenodo/DataCite `codeRepository`), so either defer it or make an unresolvable DOI
   an honest pre-run refusal that writes nothing, never a guessed URL.

Every unresolved path (fetch fails, bad URL, unreachable host) is an honest
exit-non-zero-nothing-written or UNVERIFIED, never a false REPRODUCED.

## Why this was picked (from the `cn` ranking)

- **It is the missing half of C8.** Six slices shipped the *binding* side (JSON `path`,
  TSV/CSV cell, stdout/log regex, notebook cell, env resurrection, freshness guard across all
  surfaces — `docs/technical/CAPABILITY_ROADMAP.md:1047-1335`, CHANGELOG v0.40.0→v0.46.0). The
  *intake* side never moved. Every C8 slice's deferral list carries "remote `<doi|url>`"
  (`CAPABILITY_ROADMAP.md:1073, 1093, 1159, 1213, 1252`), and the capability's own build
  surface names `contig reproduce <repo|doi>` as the shipping surface (`:1372`).
- **It unblocks two things gated on real repos, not on code.** The slice-4 `occurrence`/`group`
  selectors are explicitly "gated on a counted post-merge experiment over 5 real repos"
  (`:1211`), and C8's corpus stream into C6 ("every reproduction attempt is a labeled corpus
  case", `:1379`) needs actual published-repo attempts.
- **It is the acquisition channel the roadmap already banked on.** "I ran 50 published papers'
  code — here is how many reproduced" (`:1353-1355`) is a batch over URLs, not over hand-cloned
  directories. Layer-2 throughout: fetch, run, self-heal, verify — no workflow authoring, no
  clinical/wet-lab dependency.

## Explicitly out of scope / not picked alongside

- Figure/plot claims — hard-blocked (no plot-hash; would break the stdlib-only dependency
  contract, `CAPABILITY_ROADMAP.md:1337-1344`).
- Paper-parsing to extract claims — a separate, larger slice.
- C6 eval fold-in of reproduce outcomes — blocked on a labeling design (`:878-884`).
- Dashboard card for `reproduce` — pure surface over shipped logic; deferred again.

## Alternates the `cn` run considered and ranked below this

- C8 dashboard card for `reproduce` (cheap, visible, low moat).
- C5 RO-Crate export of reference identity/provenance (`:815`) — stdlib JSON-LD, deepens the
  reproduce guarantee, but no demand-pull.

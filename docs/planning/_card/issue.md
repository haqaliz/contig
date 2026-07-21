# Card: feat reproduce-tsv-csv-locator (C8 slice 3)

**Type:** feat · **Owner:** aliz · **Branch:** `feat/reproduce-tsv-csv-locator/aliz`

No GitHub issue — this unit of work came from `/contig-next` (cn), 2026-07-19. The
recommendation below is the source brief.

## Brief

Add a **TSV/CSV output-locator** to `contig reproduce` — C8 slice 3, the "named next
step" deferred by both shipped output-locator slices
(`docs/technical/CAPABILITY_ROADMAP.md:1093,1122`).

A reproduce claim should be able to bind its regenerated number from a **cell in a
repo's own tabular output** (`.tsv`/`.csv`), not only from structured JSON as today, so
the tool reads real cloned bioinformatics repos whose numbers live in DESeq2 / count /
stats tables (where the numbers overwhelmingly live in this domain — JSON-only is a weak
locator for bioinformatics specifically).

Reuse slice 1.5's `classify` core, the strict numeric-string → UNVERIFIED rule, and the
pre-run `from`-containment guard; parse with the stdlib `csv` module (no new dependency —
the stdlib-only runtime contract `pydantic`/`typer`/`cryptography` must hold).

## The one design fork to resolve in the dig

The cell-addressing syntax:
- header-name vs positional column selection
- row-key-match (e.g. `{"gene":"BRCA1"}`) vs raw row-index selection
- delimiter sniffing (tab vs comma) and headerless-file handling

Everything else inherits the JSON locator's contracts.

## Honesty contract (inherited, non-negotiable)

- Every unresolved / non-numeric / out-of-range address degrades to **UNVERIFIED**, never
  `DIVERGED`, never a false reproduce.
- A numeric **string** cell is strictly UNVERIFIED (never coerced) — same as slice 1.5.
- An escaping / absolute `from` path is refused **pre-run** (exit non-zero, no record);
  the engine additionally never reads outside the repo.
- JSON-only was the slice-1.5 scope; this slice adds TSV/CSV. Figure/plot & table-*image*
  claims remain out of scope (blocked: no plot-hash, stdlib-only dep contract).

## Constraints

- Layer-2 only (run/verify/reproduce). Not Layer 1. Research-use, no raw-read egress.
- Test-first (strict TDD). Deterministic. **No real repo, network, or pip in CI.**

## Prior art in-repo (starting points for the dig)

- `src/contig/verification/reproduce.py` — `resolve_pointer` / `_parse_path` (JSON walker,
  slice 1.5), `load_claims`, `classify`, `run_reproduction`, `reduce_reproduction`.
- `benchmark._relative_delta` — the reused float-tolerance comparison.
- Slice 1.5 planning: `docs/planning/reproduce-output-locator/`.
- Slice 1 / slice 2 planning: `docs/planning/reproduce-published-work/`,
  `docs/planning/reproduce-env-resurrection/`.

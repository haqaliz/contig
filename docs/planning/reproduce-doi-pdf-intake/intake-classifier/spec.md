# Spec: intake-classifier (paper-argument classification)

Aspect of: `reproduce-doi-pdf-intake`. Source: PRD M1 + the pinned decisions.

## Problem slice and user outcome

`contig extract-claims` must accept a DOI, a local `.pdf`, or the existing local
`.txt`/`.md` path in one `paper` argument. A pure, deterministic classifier
decides the kind before any I/O, so every refusal is a named message with
nothing written — the `classify_repo_argument` posture (`src/contig/fetch.py:110-155`).

## In-scope requirements

- `PaperArgument` frozen dataclass in `src/contig/verification/paper_intake.py`:
  `kind: Literal["text", "pdf", "doi"] | None`, `refusal: str | None`,
  `doi: str | None` — `__post_init__` enforces **exactly one** of `kind`/
  `refusal` set, and `doi` set only when `kind == "doi"` (the `RepoArgument`
  invariant, `fetch.py:29-68`).
- `classify_paper_argument(arg: str) -> PaperArgument`, pure (no filesystem,
  network, subprocess), decision order:
  1. **Leading `-` refused first, unconditionally** (the RCE-shape posture):
     message mirroring `fetch.py:129-133` ("looks like a command-line option,
     not a paper; pass a DOI or a path to a .pdf/.txt/.md paper").
  2. **DOI forms → kind `doi`**, reusing `_is_doi` from `contig.fetch`
     (`fetch.py:75-76,96-97`): `doi:` (case-insensitive), bare
     `10.<digits>/…`, and `https://doi.org/<doi>` (case-insensitive prefix).
     The `doi` field holds the DOI after stripping the `https://doi.org/`
     prefix and surrounding whitespace; **a DOI containing `?` or `#` is
     refused** (fragment/query is a different document — pinned decision).
     `doi:` with an empty remainder, or `https://doi.org/` with an empty
     remainder, is refused.
  3. **Local `.pdf` (case-insensitive extension) → kind `pdf`.**
  4. **Any other URL scheme** (`http`, `ftp`, `ssh`, `git`, `file`, …) and
     **scp-like** `user@host:path` → refusal naming what is supported
     (`doi`, `https://doi.org/…`, local `.pdf`/`.txt`/`.md`).
  5. **Everything else → kind `text`** (existing behavior, byte-identical).

## Out-of-scope boundaries

- No direct `https://…pdf` URLs (other than `doi.org`) — refused by rule 4.
- No filesystem/network access in the classifier.
- No change to `classify_repo_argument` or `_is_doi` in `fetch.py`
  (the reproduce command's DOI refusal stays).

## Acceptance criteria (testable)

- One pinned test per decision: leading `-` first even when DOI-shaped;
  all three DOI forms → `doi` with the correct stripped `doi` value;
  whitespace-padded DOI stripped; `?`/`#` DOIs refused; empty-remainder
  `doi:` / `https://doi.org/` refused; `.pdf` and `.PDF` → `pdf`;
  `http`/`ftp`/`ssh`/`git`/`file` schemes refused naming supported forms;
  scp-like refused; `paper.txt`/`paper.md`/`paper` → `text`; `-` alone
  refused; `PaperArgument` kind/refusal mutual exclusion enforced
  (constructing a both-set or neither-set instance raises).

## Dependencies and sequencing notes

- Prerequisite for the `cli-wiring` aspect (the CLI calls the classifier
  first). Independent of `doi-fetch` and `pdf-text-seam`.
- Imports `_is_doi` from `contig.fetch` (intra-package private import is
  acceptable; do not rename or refactor `fetch.py`).

## Open questions / risks

- A local file literally named `10.1234/abc` classifies as `doi` (DOI-shaped
  wins over local path) — documented, matching the reproduce classifier's
  existing DOI-before-local ordering.
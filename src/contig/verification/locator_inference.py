"""Safe artifact walk for locator inference (candidate-sweep aspect, R1/R2).

Before a claim's value can be matched to a coordinate in a repo's output
artifacts, we need to know what candidate files exist. `iter_artifacts`
mirrors `bundle.compute_tree_sha256`'s published WALK discipline: prune
`.git` (at any depth) and symlinked directories in place, skip symlinked
files, `os.walk(followlinks=False)`. Only `.json`/`.tsv`/`.csv`/`.tsv.gz`/
`.csv.gz` files are candidates; the result is sorted by POSIX-relative path
for a reproducible sweep.

It deliberately DIVERGES from `compute_tree_sha256` on error handling:
`compute_tree_sha256` produces a single digest, where a partial walk would be
a dishonest result, so any `OSError` aborts it entirely (`onerror=_raise`,
`bundle.py:383-410`). A sweep's contract is the opposite (spec R6): every
unreadable artifact/directory must produce a `SweepSkip` and the sweep must
keep going, never abort. So an unreadable subdirectory here is recorded as a
`SweepSkip` naming it, and the walk continues into the rest of the tree.

This module is the pure substrate only (R1/R2). Enumerating numeric leaves
inside each artifact (R4/R5), the size bound (R3), and the sweep driver are
later slices of the same aspect.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path

_CANDIDATE_EXTENSIONS = (".json", ".tsv", ".csv", ".tsv.gz", ".csv.gz")


@dataclass(frozen=True)
class Candidate:
    source: str  # repo-relative POSIX path == the locator "from"
    kind: str  # "json" | "table"
    value: float
    path: str | None = None  # kind == "json"
    column: str | int | None = None  # kind == "table"
    row: int | None = None  # kind == "table"
    header: bool | None = None  # kind == "table"


@dataclass(frozen=True)
class SweepSkip:
    source: str
    reason: str


def iter_artifacts(repo: Path) -> tuple[list[Path], list[SweepSkip]]:
    """Walk `repo` for candidate artifact files, honest and never raising.

    `os.walk(followlinks=False)` with `.git` and symlinked directories
    pruned in place (dirnames mutated) at any depth, and symlinked files
    skipped. Only files ending in `.json`, `.tsv`, `.csv`, `.tsv.gz`, or
    `.csv.gz` are candidates. A missing or non-directory `repo` returns
    `([], [])` rather than raising -- that's an invalid call, not a sweep
    that hit an unreadable directory, so no `SweepSkip` is manufactured for
    it.

    A subdirectory `os.walk` cannot list (e.g. permission denied) is
    recorded as a `SweepSkip(source=<repo-relative posix path>, reason=...)`
    and the walk continues into every other directory. A single dirname or
    filename whose `is_symlink()` stat raises (e.g. a delete race) is
    likewise recorded as its own `SweepSkip` in isolation, without dropping
    any of its siblings -- an unreadable subtree, or one flaky entry, must
    never silently shrink the candidate set with no signal (spec R6).

    Returns paths sorted by POSIX-relative path so a sweep is reproducible.
    """
    base = Path(repo)
    if not base.is_dir():
        return [], []
    found: list[Path] = []
    skips: list[SweepSkip] = []

    def _skip_for(bad_path: Path, err: OSError) -> None:
        # An unreadable subtree, or a stat() race on one entry, must never
        # silently shrink the candidate set with no signal -- record it as
        # an honest SweepSkip and let the walk (or this directory's
        # remaining entries) continue (never abort the sweep -- R6).
        try:
            source = bad_path.relative_to(base).as_posix()
        except ValueError:
            source = str(bad_path)
        skips.append(SweepSkip(source=source, reason=str(err)))

    def _walk_onerror(err: OSError) -> None:
        _skip_for(Path(getattr(err, "filename", None) or base), err)

    for dirpath, dirnames, filenames in os.walk(
        base, followlinks=False, onerror=_walk_onerror
    ):
        kept_dirnames = []
        for d in dirnames:
            if d == ".git":
                continue
            dpath = Path(dirpath, d)
            try:
                is_link = dpath.is_symlink()
            except OSError as err:
                # A stat() race on THIS entry only (e.g. it was deleted
                # between os.walk's listdir and our check) must not drop any
                # sibling dirname -- record just this one and keep pruning
                # the rest.
                _skip_for(dpath, err)
                continue
            if not is_link:
                kept_dirnames.append(d)
        dirnames[:] = kept_dirnames

        for name in filenames:
            if not name.endswith(_CANDIDATE_EXTENSIONS):
                continue
            p = Path(dirpath, name)
            try:
                is_link = p.is_symlink()
            except OSError as err:
                # Same isolation for a filename: this entry's failure must
                # not drop any sibling filename in this directory.
                _skip_for(p, err)
                continue
            if is_link:
                continue
            found.append(p)
    return sorted(found, key=lambda p: p.relative_to(base).as_posix()), skips


def _is_numeric_leaf(value: object) -> bool:
    """True iff `value` is a JSON leaf `resolve_pointer` should be pointed at.

    `bool` is `int` in Python -- rejected first (D4) so `true`/`false` are
    never candidates. `str` (including a numeric-looking string like
    `"0.91"`) is never a candidate (D5): it is strictly UNVERIFIED at
    reproduce time, so proposing a locator for it would propose one that can
    never verify. Non-finite floats (`nan`/`inf`, which `json.loads` accepts
    by default) are likewise never candidates.
    """
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    return False


def _key_expressible(key: str, is_first: bool) -> bool:
    """True iff `key` can appear as one dotted-path segment (D1).

    Mirrors `_parse_path`'s grammar (`reproduce.py:78`) exactly, since that
    is the shipped, unchanged parser every emitted `path` must round-trip
    through:

    - A bare/dotted key is read up to the next `.` or `[`, so a key
      containing either character would silently truncate or merge with an
      adjacent segment -- never expressible, at any position.
    - An empty key can't be written as a segment at all: as the first token
      it fails `_parse_path`'s leading `if not s: return None`; after a `.`
      it fails the `s[i] in ".["` look-ahead. Never expressible.
    - Only the *first* token is subject to `_parse_path`'s one-time leading
      `$` strip. A key that itself starts with `$` would have that `$`
      silently eaten when it's the first segment (resolving a different key
      than intended), but is fine as a later segment, where the leading `.`
      protects it.
    """
    if key == "" or "." in key or "[" in key:
        return False
    if is_first and key.startswith("$"):
        return False
    return True


def _count_numeric_leaves(value: object) -> int:
    """Count numeric leaves anywhere beneath `value`, ignoring key
    expressibility entirely.

    Used to size the ONE `SweepSkip` a rejected dict key gets: that key's
    subtree is unreachable as a whole, so whatever is further nested inside
    it -- including another unexpressible key -- is counted here rather
    than separately reported (the outermost rejection owns the whole
    subtree's count; see `_json_candidates`).
    """
    if isinstance(value, dict):
        return sum(_count_numeric_leaves(v) for v in value.values())
    if isinstance(value, list):
        return sum(_count_numeric_leaves(v) for v in value)
    return 1 if _is_numeric_leaf(value) else 0


def _why_key_unexpressible(key: object, is_first: bool) -> str:
    """Name the specific reason `_key_expressible` rejected `key`.

    Mirrors `_key_expressible`'s checks, in the same order, so this is
    reachable only through a branch that already matches one of them.
    """
    if not isinstance(key, str):
        return "key is not a string"  # JSON keys are always str; defensive only
    if key == "":
        return "key is empty"
    if "." in key:
        return "key contains '.'"
    if "[" in key:
        return "key contains '['"
    if is_first and key.startswith("$"):
        return "key starts with '$' in the first path position"
    return "key is not expressible in the locator path grammar"  # unreachable


def _build_path(tokens: list[str | int]) -> str:
    """Render `tokens` into the dotted+`[n]` expression `_parse_path` reads.

    An int token is always `[n]`, with no preceding `.` (matching the
    grammar, where `[` may follow a key directly, e.g. `xs[0]`). A str token
    is bare only in the first position; every later str token is
    `.`-prefixed.
    """
    parts: list[str] = []
    for i, tok in enumerate(tokens):
        if isinstance(tok, int):
            parts.append(f"[{tok}]")
        else:
            parts.append(tok if i == 0 else f".{tok}")
    return "".join(parts)


def _json_candidates(source: str, text: str) -> tuple[list[Candidate], list[SweepSkip]]:
    """Enumerate every numeric leaf in a JSON document as a `Candidate`.

    `source` is the repo-relative POSIX path this text was read from (it
    becomes `Candidate.source`/`SweepSkip.source` verbatim); `text` is the
    file's already-read content (R4). Every emitted `path` is built to
    round-trip through the shipped, unchanged `resolve_pointer` (D1) --
    never guessed, never emitted speculatively.

    Never raises (R6): malformed JSON is one `SweepSkip` naming the parse
    error, not an exception. A bare top-level scalar with no accessor at
    all is likewise one `SweepSkip` (there is no zero-length path
    `_parse_path` can accept).

    A dict key that cannot be given an expressible path (D1: contains
    `.`/`[`, is empty, or is a first-position `$`) makes its entire subtree
    unreachable as a unit -- we do not descend into it. That is recorded as
    ONE `SweepSkip` naming the key, why it was rejected, and the count of
    numeric leaves rendered unreachable beneath it (mirroring the shipped
    idiom of `resolve_match`/`resolve_cell`, which also name counts in
    their reasons) -- never one skip per leaf, which would pay the full
    cost of an *n*-leaf subtree in the skip list without buying anything
    back (a leaf's reason can only carry its unreachable path, never its
    value, so per-leaf reporting cannot answer "was value X among the lost
    ones?" any better than per-key can). A rejected key with ZERO numeric
    leaves beneath it gets NO skip at all -- nothing was lost, so there is
    nothing to disclose. A bad key nested inside an already-rejected key's
    subtree is never separately reported: the OUTERMOST rejection owns the
    whole subtree's count.

    `bool`, `str` (D5), `None`, and non-finite floats (D4) are simply not
    numeric leaves at all -- excluded by definition, not skipped.
    """
    candidates: list[Candidate] = []
    skips: list[SweepSkip] = []

    try:
        doc = json.loads(text)
    except json.JSONDecodeError as err:
        skips.append(SweepSkip(source=source, reason=f"malformed JSON: {err}"))
        return candidates, skips

    def walk(value: object, tokens: list[str | int]) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                is_first = not tokens
                if isinstance(key, str) and _key_expressible(key, is_first):
                    walk(child, [*tokens, key])
                    continue
                # `child`'s subtree is unreachable as a whole -- do not
                # recurse into it (that would let a nested bad key
                # double-report the same lost leaves under two skips).
                leaf_count = _count_numeric_leaves(child)
                if leaf_count == 0:
                    continue
                key_path = (*tokens, key)
                skips.append(
                    SweepSkip(
                        source=source,
                        reason=(
                            f"key {key!r} at {key_path!r} is not expressible "
                            "in the locator path grammar "
                            f"({_why_key_unexpressible(key, is_first)}); "
                            f"{leaf_count} numeric leaf(s) beneath it are "
                            "unreachable"
                        ),
                    )
                )
            return
        if isinstance(value, list):
            for index, child in enumerate(value):
                # A list index is always an expressible `[n]` segment --
                # only dict keys carry D1's coverage hole.
                walk(child, [*tokens, index])
            return
        if not _is_numeric_leaf(value):
            return
        if not tokens:
            skips.append(
                SweepSkip(
                    source=source,
                    reason="numeric root value has no expressible path (empty path)",
                )
            )
            return
        candidates.append(
            Candidate(source=source, kind="json", value=value, path=_build_path(tokens))
        )

    walk(doc, [])
    return candidates, skips

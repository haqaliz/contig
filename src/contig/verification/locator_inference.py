"""The candidate sweep for locator inference (candidate-sweep aspect).

`sweep_repo` walks a repo and enumerates EVERY numeric value in EVERY
candidate artifact as a coordinate the SHIPPED resolvers (`resolve_pointer`,
`resolve_cell` in `verification/reproduce.py`) can re-resolve to that same
value. Aspect 2 then matches those candidates against a paper's claimed
values; nothing here matches, rounds, or constructs a locator.

The whole module is four pieces:

- `iter_artifacts` (R1/R2) -- the safe walk, mirroring
  `bundle.compute_tree_sha256`'s published discipline: prune `.git` (at any
  depth) and symlinked directories in place, never follow a symlinked file,
  `os.walk(followlinks=False)`. Only `.json`/`.tsv`/`.csv`/`.tab`/`.tsv.gz`/
  `.csv.gz`/`.tab.gz` files are candidates, matched case-insensitively (a
  sweep walks other people's repos, where filename casing is not ours to
  control) while the emitted path keeps its real on-disk casing.
- `_json_candidates` (R4, D1/D4/D5) -- one `Candidate` per numeric JSON leaf,
  with a dotted+`[n]` `path` that round-trips through `_parse_path`.
- `_table_candidates` (R5, D2/D3/D5) -- one `Candidate` per numeric table
  cell, with `column`/`row`/`header` that `resolve_cell` re-resolves.
- `sweep_repo` (R3/R6/R7) -- the driver: the per-artifact size bound and
  dispatch to one of the two enumerators.

**The central guarantee is that the sweep never silently produces fewer
candidates than there are numbers present.** A claim that fails to bind
because we quietly skipped its file is indistinguishable, to the user, from
an honest miss -- so every number this module cannot address must come back
as a `SweepSkip` naming what was lost and why. Two vocabularies matter here
and are kept distinct: something *excluded by definition* (a `.txt` file, a
JSON `true`/`null`/string, a non-numeric table cell) is not a loss and gets
no skip; something that IS a number but has no expressible coordinate is a
loss and always gets one. A rejection with zero numeric values beneath it
gets no skip, because nothing was lost.

This module deliberately DIVERGES from `compute_tree_sha256` on error
handling: `compute_tree_sha256` produces a single digest, where a partial
walk would be a dishonest result, so any `OSError` aborts it entirely
(`onerror=_raise`, `bundle.py:383-410`). A sweep's contract is the opposite
(spec R6): every unreadable artifact or directory produces a `SweepSkip` and
the sweep keeps going. **Nothing here raises** -- not on a malformed
document, an unreadable subtree, a mid-walk delete race, or a document
nested deeper than Python's recursion limit.

Both returned lists are sorted by the artifact's POSIX-relative path, so two
sweeps of the same tree return byte-identical results.

Stdlib only, no I/O beyond reading the artifacts, and no shipped file is
modified or re-implemented: `_parse_path`, `_read_table`, `_resolve_delimiter`
and `_MAX_MATCH_BYTES` are imported from `reproduce.py` and used as-is (R7).
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path

from contig.verification.reproduce import (
    _MAX_MATCH_BYTES,
    _parse_path,
    _read_table,
    _resolve_delimiter,
)

_CANDIDATE_EXTENSIONS = (
    ".json",
    ".tsv",
    ".csv",
    ".tab",
    ".tsv.gz",
    ".csv.gz",
    ".tab.gz",
)


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
    skipped. Only files ending in `.json`, `.tsv`, `.csv`, `.tab`,
    `.tsv.gz`, `.csv.gz`, or `.tab.gz` are candidates, matched
    case-insensitively (`RESULTS.JSON`/`DATA.CSV`/`counts.TSV` all match) --
    the returned `Path` always keeps the file's real on-disk casing, since
    only the match is case-insensitive, never the emitted name. A missing
    or non-directory `repo` returns `([], [])` rather than raising --
    that's an invalid call, not a sweep that hit an unreadable directory,
    so no `SweepSkip` is manufactured for it.

    Three things this walk cannot look at become honest `SweepSkip`s rather
    than silent omissions, each with its own prose (they are genuinely
    different situations and a reader must be able to tell them apart):

    - A subdirectory `os.walk` cannot list (e.g. permission denied): a whole
      SUBTREE of artifacts went unsearched. This is the commonest real skip
      when sweeping someone else's repo, so it says so in words, keeping the
      raw errno as the tail rather than as the entire message.
    - A single dirname or filename whose `is_symlink()` stat raises (e.g. a
      delete race): recorded in isolation, without dropping any of its
      siblings.
    - A SYMLINK we deliberately did not follow. Containment discipline stands
      -- the sweep never reads through a symlink -- but a symlinked
      `results.json` pointing at a legitimate in-repo target is real numbers
      gone, so it is named. Only symlinks that would otherwise have been
      swept are disclosed: a symlinked `.txt`, or a symlinked `.git`, was
      excluded by definition before the symlink check ran and is not a loss.

    Both lists are sorted by POSIX-relative path so a sweep is reproducible
    -- the skips as well as the paths, since a non-deterministic disclosure
    list is as unreproducible as a non-deterministic candidate list.
    """
    base = Path(repo)
    if not base.is_dir():
        return [], []
    found: list[Path] = []
    skips: list[SweepSkip] = []

    def _skip_for(bad_path: Path, reason: str) -> None:
        # An unreadable subtree, a stat() race on one entry, or an
        # unfollowed symlink must never silently shrink the candidate set
        # with no signal -- record it as an honest SweepSkip and let the walk
        # (or this directory's remaining entries) continue (never abort the
        # sweep -- R6).
        try:
            source = bad_path.relative_to(base).as_posix()
        except ValueError:
            source = str(bad_path)
        skips.append(SweepSkip(source=source, reason=reason))

    def _walk_onerror(err: OSError) -> None:
        _skip_for(
            Path(getattr(err, "filename", None) or base),
            "directory could not be listed, so every artifact in it and "
            f"beneath it went unsearched: {err}",
        )

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
                _skip_for(
                    dpath,
                    "directory entry could not be stat()ed while pruning "
                    "symlinks, so it and everything beneath it went "
                    f"unsearched: {err}",
                )
                continue
            if is_link:
                _skip_for(
                    dpath,
                    "symlinked directory, not followed (the sweep never "
                    "reads through a symlink), so every artifact beneath it "
                    "went unsearched",
                )
                continue
            kept_dirnames.append(d)
        dirnames[:] = kept_dirnames

        for name in filenames:
            # Matched case-insensitively (RESULTS.JSON, DATA.CSV, a .TSV --
            # a sweep walks other people's repos, whose filename casing is
            # not ours to control) but `name` itself, used below to build
            # the emitted path, is never lower-cased: the on-disk casing is
            # what a locator must resolve against.
            if not name.lower().endswith(_CANDIDATE_EXTENSIONS):
                continue
            p = Path(dirpath, name)
            try:
                is_link = p.is_symlink()
            except OSError as err:
                # Same isolation for a filename: this entry's failure must
                # not drop any sibling filename in this directory.
                _skip_for(
                    p,
                    "artifact could not be stat()ed while checking for a "
                    f"symlink, so it was not swept: {err}",
                )
                continue
            if is_link:
                # NOT followed -- but named. This is the one exclusion the
                # module's "excluded by definition" vocabulary must not
                # cover: the file has a candidate extension, so its numbers
                # were in scope and are now missing.
                _skip_for(
                    p,
                    "symlinked artifact, not followed (the sweep never reads "
                    "through a symlink), so its numeric value(s) were not "
                    "swept",
                )
                continue
            found.append(p)
    return (
        sorted(found, key=lambda p: p.relative_to(base).as_posix()),
        sorted(skips, key=lambda s: s.source),
    )


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

    A NECESSARY-CONDITIONS filter over `_parse_path`'s grammar
    (`reproduce.py:78`), not a complete one, and deliberately not the thing
    that guarantees correctness. It exists to give each rejected key a
    specific, useful reason (see `_why_key_unexpressible`); the actual
    guarantee that an emitted path resolves to the value it claims is the
    token-equality round-trip in `_json_candidates`, which re-parses the
    rendered path through the shipped parser itself.

    That division matters: this function once claimed to mirror the grammar
    "exactly" and did not -- it missed `_parse_path`'s leading `expr.strip()`
    (`reproduce.py:79`), so a key like `" x"` or `"x "` passed every check
    here and then resolved to a DIFFERENT key. Hand-re-deriving a parser is
    how that happens; the backstop is why it cannot happen again. Add rules
    here for better messages, never for safety.

    The conditions checked:

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

    (The function name keeps "leaves" because that is the JSON structural
    term; every user-facing skip reason says "numeric value(s)", one
    vocabulary across the JSON and table paths.)

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
    reachable only through a branch that already matches one of them. Like
    that function it is a MESSAGE-QUALITY helper, not a safety boundary: a
    key that slips past both is still caught by `_json_candidates`'s
    token-equality round-trip, which reports it generically rather than
    specifically. The trailing fallback is that generic case.
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
    numeric values rendered unreachable beneath it (mirroring the shipped
    idiom of `resolve_match`/`resolve_cell`, which also name counts in
    their reasons) -- never one skip per leaf, which would pay the full
    cost of an *n*-leaf subtree in the skip list without buying anything
    back (a leaf's reason can only carry its unreachable path, never its
    value, so per-leaf reporting cannot answer "was value X among the lost
    ones?" any better than per-key can). A rejected key with ZERO numeric
    values beneath it gets NO skip at all -- nothing was lost, so there is
    nothing to disclose. A bad key nested inside an already-rejected key's
    subtree is never separately reported: the OUTERMOST rejection owns the
    whole subtree's count.

    Before ANY candidate is emitted, its rendered `path` is re-parsed through
    the shipped `_parse_path` and the result compared to the tokens that
    built it -- TOKEN EQUALITY, not "is it parseable". This is the
    authoritative guard, and it is deliberately a backstop rather than a
    fourth place to hand-re-derive the grammar: `_key_expressible`,
    `_why_key_unexpressible` and `_build_path` each encode their own reading
    of `_parse_path`, and three hand-derivations is exactly how
    `_parse_path`'s leading `expr.strip()` (`reproduce.py:79`) came to be
    missed by all of them. The paths that miss ARE parseable -- they simply
    parse to DIFFERENT tokens, so `{" x": 0.91, "x": 0.42}` would emit the
    path `" x"` carrying the value 0.91 while `resolve_pointer` returns
    0.42: ANOTHER KEY'S VALUE, the worst outcome this aspect can produce.
    `_key_expressible` is kept because it gives specific, useful reasons;
    this closes the class behind it, at zero recall cost (every path the
    module legitimately emits satisfies token equality, including keys with
    inner whitespace in a non-first position).

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
    except RecursionError:
        # `json.loads` recurses per nesting level, so a deeply enough nested
        # document exhausts the stack inside the PARSER. "Never raises" (R6)
        # is unconditional: one pathological artifact must not abort the
        # sweep of every other artifact in the repo.
        skips.append(
            SweepSkip(
                source=source,
                reason=(
                    "JSON nests too deeply to parse (it exceeds Python's "
                    "recursion limit); no numeric value in it could be "
                    "enumerated"
                ),
            )
        )
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
                            f"{leaf_count} numeric value(s) beneath it are "
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
        path = _build_path(tokens)
        if _parse_path(path) != tokens:
            # The authoritative round-trip guard (see the docstring). Token
            # equality, never "is it parseable" -- a path that parses to
            # DIFFERENT tokens resolves to a different value, silently.
            skips.append(
                SweepSkip(
                    source=source,
                    reason=(
                        f"path {path!r} for key path {tuple(tokens)!r} does not "
                        "round-trip through the shipped locator path grammar "
                        f"(it re-parses to {_parse_path(path)!r}); 1 numeric "
                        "value(s) beneath it are unreachable"
                    ),
                )
            )
            return
        candidates.append(Candidate(source=source, kind="json", value=value, path=path))

    try:
        walk(doc, [])
    except RecursionError:
        # `walk` (and `_count_numeric_leaves`) recurse per nesting level, so
        # a document `json.loads` accepted can still exhaust the stack here.
        # Candidates already enumerated are KEPT -- honesty cuts both ways,
        # and discarding good coordinates would shrink the candidate set for
        # a reason unrelated to them -- but the abandoned remainder is
        # disclosed, since we cannot say how many numeric values it held.
        skips.append(
            SweepSkip(
                source=source,
                reason=(
                    "JSON nests too deeply to enumerate (it exceeds Python's "
                    "recursion limit); enumeration stopped after "
                    f"{len(candidates)} numeric value(s) and an unknown "
                    "number beyond that point are unreachable"
                ),
            )
        )
    return candidates, skips


def _table_delimiter(path: Path) -> str | None:
    """Infer the read-only delimiter for `path` from its extension (D3).

    A thin named wrapper over the shipped `_resolve_delimiter(path.name,
    None)` -- never a second, independently-maintained extension mapping.
    D3 means we never emit a delimiter (`Candidate` has no delimiter field
    at all); it is used only to drive `_read_table` here. Because we never
    emit one, `load_claims` re-derives the delimiter from the same
    extension at reproduce time -- if our mapping and the engine's ever
    diverged, we would read a file one way and the engine another, and our
    coordinates would silently point at different cells. Sharing the one
    function (rather than mirroring its logic) makes that impossible
    rather than merely unlikely. It already lower-cases and strips one
    trailing `.gz`, so `.tab`/`.tab.gz` and any casing `iter_artifacts`
    admits are covered for free. An unrecognized extension (unreachable via
    `iter_artifacts`, which already filters to `_CANDIDATE_EXTENSIONS`, but
    this function is also called directly) returns `None` rather than
    guessing.
    """
    return _resolve_delimiter(path.name, None)


def _cell_parses_as_float(cell: str) -> bool:
    """True iff `cell` is accepted by `float()` -- D2's header test, for one
    cell.

    Deliberately the raw `float()` test, including `"nan"`/`"inf"`-spelled
    strings: D2 is stated as "no cell parses as a float", not "no cell
    parses as a *finite* float", and this uncalibrated heuristic is
    implemented exactly as specified, never sharpened. (Finiteness is
    filtered separately, only once a cell is about to become a candidate's
    value -- see `_numeric_table_value`.)
    """
    try:
        float(cell)
    except (ValueError, TypeError):
        return False
    return True


def _numeric_table_value(cell: str) -> float | None:
    """Parse `cell` into a candidate value, or `None` if it isn't one.

    D5: a table cell is always a string, and a numeric-*looking* string
    (e.g. `"5.0"`) IS a candidate here -- the opposite of the JSON rule
    (`_is_numeric_leaf`), where a numeric string is never a candidate.
    `nan`/`inf` are excluded even though `float()` accepts them (mirrors
    D4's JSON exclusion, for the same reason A4 needs it here too: the
    round-trip pin checks `float(resolved) == cand.value`, which can never
    hold for NaN, since NaN != NaN).
    """
    try:
        value = float(cell)
    except (ValueError, TypeError):
        return None
    if not math.isfinite(value):
        return None
    return value


def _table_candidates(source: str, path: Path) -> tuple[list[Candidate], list[SweepSkip]]:
    """Enumerate every numeric cell in a `.tsv`/`.csv`/`.tab`(`.gz`) table
    as a `Candidate` (R5). `iter_artifacts` matches these extensions
    case-insensitively; this function is handed the file's real,
    on-disk-cased `path` regardless.

    `source` is the repo-relative POSIX path this table lives at (becomes
    `Candidate.source`/`SweepSkip.source` verbatim); `path` is the real
    filesystem path read via `_read_table` (R7: reused unchanged -- this
    function never opens a file or a gzip stream itself, and never runs its
    own CSV parser).

    Header detection (D2): row 0 is a header iff NO cell in it parses as a
    float; otherwise the table is headerless. This is a **deliberately
    uncalibrated engineering default**, implemented exactly as specified
    and never sharpened with per-column or per-file cleverness (see
    `_cell_parses_as_float`). Misdetection silently shifts every row index
    in the file, and nothing inside this function can detect that from the
    data alone -- `header`/`row` are `resolve_cell`'s literal,
    self-consistent coordinate, not a claim about which row is "really"
    the header.

    Header mode: `column` is the header name (str); `row` indexes DATA rows
    only (`rows[1:]`), so the first data row is `row=0`. A column whose
    header name is not unique never becomes a candidate source --
    `resolve_cell` calls a duplicate name ambiguous (`reproduce.py:263`),
    so emitting one would propose a locator that can never resolve. Every
    numeric cell beneath every column sharing that name is folded into ONE
    `SweepSkip` naming the name, the duplicate count, and how many numeric
    candidates are unreachable as a result (mirrors `_json_candidates`'s
    per-key, not per-leaf, skip). A duplicate name with zero numeric cells
    beneath it costs nothing and gets no skip at all -- same rule as a
    rejected JSON key with zero numeric leaves.

    Headerless mode (`header=False`): `column` is a 0-based integer field
    index; `row` indexes ALL rows.

    D3: the delimiter is derived from `path`'s extension purely to read the
    file (`_table_delimiter`) and is never attached to a `Candidate` --
    `Candidate` has no delimiter field to set.

    D5: a numeric-looking string cell IS a candidate -- see
    `_numeric_table_value`.

    A non-numeric cell (`"NA"`, a gene id, a free-text note) is simply not a
    candidate at all -- excluded by definition, not skipped, exactly as
    `bool`/`str`/`None`/non-finite are on the JSON side.

    Never raises (R6): an unrecognized extension, or anything `_read_table`
    can't parse (missing file, non-UTF-8, corrupt gzip, malformed CSV), is
    one `SweepSkip`, never an exception. An empty table (`_read_table`
    returns `[]`) yields no candidates and no skip -- nothing was lost.

    RAGGED ROWS CUT BOTH WAYS, and the two directions get opposite
    treatment because `resolve_cell` treats them differently:

    - A data row SHORTER than the header contributes only its real cells; a
      cell past its row's end is simply absent, never an `IndexError` (A9),
      and nothing was lost because nothing was there.
    - A data row LONGER than the header holds real numbers at column indices
      the header never names. In header mode those cells are NOT ADDRESSABLE:
      `resolve_cell` bounds an integer column by the HEADER row's width, not
      the target row's (`reproduce.py:301-305`), so `resolve_cell(rows, 2, 0,
      True)` on a 2-column header is "column index 2 out of range (2 header
      columns)" no matter how wide the data row is. Emitting them would trade
      a silent loss for a coordinate that can never bind, so each over-wide
      column that held at least one numeric cell is ONE `SweepSkip` naming
      the column index and the count (same shape as the duplicate-name skip);
      an over-wide column with zero numeric cells gets no skip, same
      zero-lost-means-no-skip rule as everywhere else.

    This is not an exotic shape. D2 sees a leading `# Program:featureCounts
    v2.0.1` line as a ONE-COLUMN header and pushes the entire table off the
    right edge, and a leading blank line yields a ZERO-column header;
    `#`/`##` preamble lines are ordinary in bioinformatics table output. In
    headerless mode none of this applies -- `resolve_cell` bounds the column
    by the target row itself -- so over-wide cells there are ordinary
    candidates, not skips.

    One reachability the case-insensitive extension match in
    `iter_artifacts` creates: the shipped `_read_table` detects gzip via a
    CASE-SENSITIVE `path.name.endswith(".gz")`, so a `*.GZ`-suffixed file
    (any casing other than exactly lower-case `.gz`) is opened as plain
    text, not decompressed, and `_read_table` degrades it to `None` same as
    a genuinely corrupt/unreadable file. Reusing that generic reason here
    would be a confidently WRONG diagnosis -- no corrupt gzip, no malformed
    CSV, just a case mismatch -- so that specific case is detected and
    named BEFORE calling `_read_table`, with its own accurate `SweepSkip`
    naming the file and the case-sensitivity cause, rather than folded into
    the generic "could not be read" reason.
    """
    candidates: list[Candidate] = []
    skips: list[SweepSkip] = []

    delimiter = _table_delimiter(path)
    if delimiter is None:
        skips.append(
            SweepSkip(source=source, reason=f"unrecognized table extension: {path.name!r}")
        )
        return candidates, skips

    if path.name.lower().endswith(".gz") and not path.name.endswith(".gz"):
        # `iter_artifacts`'s match is case-insensitive, but the shipped
        # `_read_table` only decompresses a lower-case ".gz" suffix
        # (`path.name.endswith(".gz")`). This file WOULD reach
        # `_read_table` and fail there too, but with the generic "could not
        # be read" reason -- which would misdiagnose a case mismatch as a
        # corrupt gzip or malformed CSV. Name the real cause instead of
        # letting the generic path swallow it.
        skips.append(
            SweepSkip(
                source=source,
                reason=(
                    f"{path.name!r} cannot be decompressed: the shipped table "
                    "reader's gzip detection is case-sensitive and only "
                    "recognizes a lower-case '.gz' suffix -- rename the file "
                    "to end in a lower-case '.gz' to have it read"
                ),
            )
        )
        return candidates, skips

    rows = _read_table(path, delimiter)
    if rows is None:
        skips.append(
            SweepSkip(
                source=source,
                reason=(
                    "table could not be read (missing, unreadable, not valid "
                    "UTF-8, corrupt gzip, or malformed CSV)"
                ),
            )
        )
        return candidates, skips

    if not rows:
        return candidates, skips

    header_row = rows[0]
    header = not any(_cell_parses_as_float(cell) for cell in header_row)

    if not header:
        for row_idx, data_row in enumerate(rows):
            for col_idx, cell in enumerate(data_row):
                value = _numeric_table_value(cell)
                if value is None:
                    continue
                candidates.append(
                    Candidate(
                        source=source,
                        kind="table",
                        value=value,
                        column=col_idx,
                        row=row_idx,
                        header=False,
                    )
                )
        return candidates, skips

    data_rows = rows[1:]
    name_counts: dict[str, int] = {}
    for name in header_row:
        name_counts[name] = name_counts.get(name, 0) + 1
    duplicate_lost: dict[str, int] = {}
    over_wide_lost: dict[int, int] = {}

    # Row-major so candidates come out in the order a reader would scan the
    # table (top to bottom, left to right) -- the same order the ragged-row
    # and duplicate-header tests pin.
    for row_idx, data_row in enumerate(data_rows):
        for col_idx, name in enumerate(header_row):
            if col_idx >= len(data_row):
                continue
            value = _numeric_table_value(data_row[col_idx])
            if value is None:
                continue
            if name_counts[name] > 1:
                duplicate_lost[name] = duplicate_lost.get(name, 0) + 1
                continue
            candidates.append(
                Candidate(
                    source=source, kind="table", value=value, column=name, row=row_idx, header=True
                )
            )
        # The other ragged direction: cells past the HEADER's right edge are
        # enumerated by the loop above only up to `len(header_row)`, so
        # without this they would be lost with no signal at all. They are not
        # addressable (see the docstring), so they are counted, never
        # emitted.
        for col_idx in range(len(header_row), len(data_row)):
            if _numeric_table_value(data_row[col_idx]) is None:
                continue
            over_wide_lost[col_idx] = over_wide_lost.get(col_idx, 0) + 1

    for name, count in name_counts.items():
        if count <= 1:
            continue
        lost = duplicate_lost.get(name, 0)
        if lost == 0:
            continue
        skips.append(
            SweepSkip(
                source=source,
                reason=(
                    f"column {name!r} is ambiguous: {count} header matches "
                    "(resolve_cell cannot disambiguate); "
                    f"{lost} numeric value(s) beneath it are unreachable"
                ),
            )
        )

    # Sorted by column index so the disclosure list is deterministic
    # regardless of which row first ran over the header's width.
    for col_idx in sorted(over_wide_lost):
        skips.append(
            SweepSkip(
                source=source,
                reason=(
                    f"column index {col_idx} is past the header row's "
                    f"{len(header_row)} column(s): resolve_cell bounds an "
                    "integer column by the header row's width, so no cell "
                    "there is addressable; "
                    f"{over_wide_lost[col_idx]} numeric value(s) beneath it "
                    "are unreachable"
                ),
            )
        )

    return candidates, skips


def sweep_repo(repo: Path) -> tuple[list[Candidate], list[SweepSkip]]:
    """Compose the repo-wide candidate sweep (R3, R6, R7): walk `repo`
    (`iter_artifacts`), apply the size bound, and dispatch each surviving
    artifact to `_json_candidates` or `_table_candidates`.

    This function does no enumeration of its own -- it only decides, per
    artifact, whether it is too big to read, and if not, which of the two
    shipped enumerators reads it. All matching/rounding/locator-construction
    logic is out of scope (aspect 2).

    The walk's own `SweepSkip`s (an unreadable subdirectory, a per-entry stat
    race -- see `iter_artifacts`) are carried through into the returned
    skips verbatim; discarding them here would silently undo the walk's own
    never-aborts contract one layer up.

    R3/A2: an artifact whose `stat().st_size` exceeds `_MAX_MATCH_BYTES` is
    one `SweepSkip` naming the size, and neither enumerator is ever called
    on it -- checked before dispatch, never a truncated read.

    Dispatch is by extension, matched case-insensitively (mirroring
    `iter_artifacts`'s own `.lower().endswith(...)` match): a case-sensitive
    check here would let an uppercase-suffixed file that `iter_artifacts`
    already admitted (e.g. `RESULTS.JSON`) fall through dispatch and vanish
    from the candidate set with no skip at all -- silently, one layer above
    where `iter_artifacts` and `_table_candidates` already fixed the same
    class of bug. `iter_artifacts` only ever hands back a path ending in one
    of `_CANDIDATE_EXTENSIONS`, so "not JSON" always means "table" here;
    there is no third case to misroute into.

    Reading a JSON file's text is this function's job (`_json_candidates`
    takes already-read text, by design -- see the module docstring); an
    `OSError` (missing file, permission race) or `UnicodeDecodeError`
    (non-UTF-8 bytes) on that read is one `SweepSkip` naming the failure,
    scoped to that single `read_text()` call so it can never swallow an
    unrelated sibling artifact's outcome (A9). A malformed-but-readable JSON
    document is `_json_candidates`'s own concern, not this function's --
    that skip is produced inside `_json_candidates`, not caught here.
    `_table_candidates` reads its own file (it must own gzip handling) and
    already never raises (R6, pinned in Task 3), so no `try/except` wraps
    that call.

    Returns `(candidates, skips)` with BOTH lists in POSIX-relative-path
    order, so a sweep is reproducible (R2). Candidates inherit that order
    from `iter_artifacts`'s sorted paths; skips are re-sorted by `source`
    here, because the walk's own skips and the per-artifact skips are
    produced in two different passes and concatenating them would otherwise
    hand back a disclosure list whose order depended on how the failures
    happened to interleave. The sort is stable, so several skips about the
    SAME artifact keep the order the enumerator emitted them in.
    """
    base = Path(repo)
    paths, skips = iter_artifacts(base)
    candidates: list[Candidate] = []

    for path in paths:
        source = path.relative_to(base).as_posix()

        try:
            size = path.stat().st_size
        except OSError as err:
            # A stat() race (e.g. deleted between the walk and here) must
            # not drop any sibling artifact's outcome -- isolated to this
            # one artifact, same discipline as iter_artifacts's own races.
            skips.append(SweepSkip(source=source, reason=f"could not stat artifact: {err}"))
            continue

        if size > _MAX_MATCH_BYTES:
            skips.append(
                SweepSkip(
                    source=source,
                    reason=(
                        f"artifact is {size} bytes, over the "
                        f"{_MAX_MATCH_BYTES}-byte match limit"
                    ),
                )
            )
            continue

        if path.name.lower().endswith(".json"):
            try:
                # `encoding="utf-8"` EXPLICITLY: a bare `read_text()` uses
                # the platform locale's encoding, so under a non-UTF-8 locale
                # a perfectly valid artifact would degrade to a misleading
                # "could not read artifact" skip and the sweep's result would
                # depend on the machine it ran on -- unacceptable in a
                # reproducibility tool. This matches `_read_table`, which
                # already passes utf-8 explicitly on both its branches.
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as err:
                skips.append(
                    SweepSkip(source=source, reason=f"could not read artifact: {err}")
                )
                continue
            new_candidates, new_skips = _json_candidates(source, text)
        else:
            new_candidates, new_skips = _table_candidates(source, path)

        candidates.extend(new_candidates)
        skips.extend(new_skips)

    skips.sort(key=lambda s: s.source)
    return candidates, skips

"""Reproduce engine for C8: claims loader, tolerance classifier, run engine,
the missing-module detector for environment resurrection, and the pure
reduction over claim results.

A "claim" is one published numeric result (e.g. an AUC or accuracy) that a
paper/repo states. `load_claims` reads a small JSON claims file; `classify`
decides, for one claim, whether a freshly observed value reproduces it within
tolerance; `detect_missing_module` pulls a missing Python package name out of a
failed run's captured output (slice 2 environment resurrection); and
`run_reproduction` drives an injected executor over the repo, reads its results
file, optionally installs a missing dependency and retries, and classifies
every claim into a `ReproduceRecord`.
"""

from __future__ import annotations

import csv
import gzip
import json
import math
import re
import shlex
import shutil
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from contig.benchmark import _relative_delta
from contig.models import (
    ClaimResult,
    ClaimStatus,
    Diagnosis,
    Patch,
    RepairStep,
    ReproduceRecord,
)
from contig.runner import Installer, _pip_install_argv, default_installer
from contig.verification.import_aliases import package_for_import

_STATUSES: tuple[ClaimStatus, ...] = ("reproduced", "within_tolerance", "diverged", "unverified")

_DEFAULT_TOLERANCE = 0.1

_MISSING_MODULE_RE = re.compile(r"No module named ['\"]([^'\"]+)['\"]", re.IGNORECASE)
_SAFE_PACKAGE_TOKEN_RE = re.compile(r"^[A-Za-z0-9._-]+$")

# Upper bound on how much text a user-authored pattern is ever run over (a
# ReDoS input bound, not a memory guard -- run output is already fully
# buffered upstream by `subprocess.PIPE`). Text over the cap is UNVERIFIED
# rather than silently truncated, which could report "0 matches" for a
# pattern that does match past the cut.
_MAX_MATCH_BYTES = 8 * 1024 * 1024

# Notebooks get a higher cap than plain text: embedded figure payloads inflate a
# real `.ipynb` well past 8 MiB, while the text a pattern is run over stays small.
_MAX_NOTEBOOK_BYTES = 32 * 1024 * 1024

# Cap on `ClaimResult.matched_output`: enough to show the matched cell/value,
# never the whole file. The marker makes the cut explicit to a reader.
_MAX_MATCHED_OUTPUT_CHARS = 512
_MATCHED_OUTPUT_TRUNCATED = "...[truncated]"


def _matched_output(text: str) -> str:
    """Cap a locator's matched fragment at `_MAX_MATCHED_OUTPUT_CHARS` chars."""
    if len(text) <= _MAX_MATCHED_OUTPUT_CHARS:
        return text
    return text[:_MAX_MATCHED_OUTPUT_CHARS] + _MATCHED_OUTPUT_TRUNCATED

# The named flags a claim's optional `"flags": [...]` array may carry. Anything
# else is refused by `load_claims` pre-run rather than silently ignored.
_REGEX_FLAGS = {
    "IGNORECASE": re.IGNORECASE,
    "MULTILINE": re.MULTILINE,
    "DOTALL": re.DOTALL,
}

# At most this many env-resurrection installs per run. Paired with the
# per-run seen-set, the retry loop provably terminates: a module already
# installed this run is never installed again, and the cap bounds distinct
# modules even in the worst case.
_MAX_INSTALLS = 2


def detect_missing_module(output: str) -> str | None:
    """Extract the missing top-level package from a run's captured error text.

    Scans for a `No module named 'X'` message (as emitted by ModuleNotFoundError /
    ImportError) and returns X's top-level package (`sklearn.utils` -> `sklearn`).
    Returns None when nothing matches or the token is not a safe package name.
    Pure, no I/O.
    """
    match = _MISSING_MODULE_RE.search(output)
    if match is None:
        return None
    module = match.group(1).split(".")[0]
    if not _SAFE_PACKAGE_TOKEN_RE.match(module):
        return None
    return module


def _parse_path(expr: str) -> list[str | int] | None:
    """Tokenize a dotted+[n] path into keys (str) and indices (int).

    Leading '$' and one leading '.' are stripped. Returns None on any
    malformed expression -- the caller treats None as "unresolved".
    """
    s = expr.strip()
    if s.startswith("$"):
        s = s[1:]
    if s.startswith("."):
        s = s[1:]
    if not s:
        return None
    tokens: list[str | int] = []
    i, n = 0, len(s)
    first = True
    while i < n:
        c = s[i]
        if c == "[":
            j = s.find("]", i)
            if j == -1:
                return None
            inner = s[i + 1 : j]
            if not inner.isdecimal():  # rejects empty, sign, spaces, non-digit;
                # isdecimal() (not isdigit()) so every accepted char is one
                # int() actually parses -- e.g. "²".isdigit() is True but
                # int("²") raises ValueError
                return None
            tokens.append(int(inner))
            i = j + 1
        elif c == ".":
            if first:
                return None
            i += 1
            if i >= n or s[i] in ".[":
                return None
            start = i
            while i < n and s[i] not in ".[":
                i += 1
            tokens.append(s[start:i])
        else:  # a bare key -- only valid as the very first accessor
            if not first:
                return None
            start = i
            while i < n and s[i] not in ".[":
                i += 1
            tokens.append(s[start:i])
        first = False
    return tokens or None


def resolve_pointer(data: object, expr: str) -> object | None:
    """Walk `data` (nested dict/list from parsed JSON) by `expr`.

    Any unresolved step -> None. Never raises. Never guesses.
    """
    tokens = _parse_path(expr)
    if tokens is None:
        return None
    cur = data
    for tok in tokens:
        if isinstance(tok, int):
            if isinstance(cur, list) and 0 <= tok < len(cur):
                cur = cur[tok]
            else:
                return None
        else:
            if isinstance(cur, dict) and tok in cur:
                cur = cur[tok]
            else:
                return None
    return cur


class ClaimsError(ValueError):
    """Raised when a claims file is malformed or one of its claims is invalid."""


@dataclass(frozen=True)
class Locator:
    """Where to find a located claim's observed value: `source` is the
    claims file's `"from"` field (a repo-relative JSON file path -- named
    `source` internally because `from` is a Python keyword), `path` is the
    dotted+`[n]` pointer into that file's parsed JSON, resolved via
    `resolve_pointer`.
    """

    source: str
    path: str


@dataclass(frozen=True)
class TableLocator:
    """Where to find a located claim's observed value inside a delimited
    text table: `source` is the claims file's `"from"` field (a
    repo-relative TSV/CSV file path -- named `source` internally for the
    same reason as `Locator.source`); `column` is a header name (str) or a
    0-based field index (int); `row` is a 0-based data-row index (int) or a
    `{column_name: predicate}` match, where a predicate is an exact string, a
    `{"regex": <pattern>}` object, or a numeric comparison object over
    `gt`/`gte`/`lt`/`lte`/`eq`; `delimiter` is the resolved,
    single-character field separator; `header` says whether row 0 of the
    file is a header row.
    """

    source: str
    column: str | int
    row: int | dict[str, str | dict[str, object]]
    delimiter: str
    header: bool


@dataclass(frozen=True)
class PatternLocator:
    """Where to find a located claim's observed value inside free text:
    `pattern` is a Python regex whose capture is the observed value (group 1
    when the pattern has capturing groups, otherwise the whole match);
    `source` is the claims file's `"from"` field (a repo-relative text/log
    file path -- named `source` internally for the same reason as
    `Locator.source`), or `None`, which means the run's own captured
    combined stdout+stderr rather than any file on disk; `flags` are the
    claim's named regex flags (`"flags": [...]`), applied on top of any
    inline `(?i)`/`(?m)`/`(?s)`.
    """

    source: str | None
    pattern: str
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class NotebookLocator:
    """Where to find a located claim's observed value inside a Jupyter
    notebook: `source` is the claims file's `"from"` field (a repo-relative
    `.ipynb` path -- named `source` internally for the same reason as
    `Locator.source`, and always a real string, never `None`); `cell`
    addresses the target cell, either an `int` index into the notebook's
    `cells` array or a single-key `{"contains": <source substring>}` /
    `{"tag": <metadata.tags entry>}` object that selects the unique cell
    matching that substring (over `source`) or tag (over `cell.metadata.tags`);
    `pattern` is a Python regex whose capture is the observed value (group 1
    when the pattern has capturing groups, otherwise the whole match), applied
    to that cell's extracted textual output; `flags` are the claim's named
    regex flags, applied on top of any inline flags.
    """

    source: str
    cell: int | dict[str, str]
    pattern: str
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Observation:
    """One locator read: the parsed value, the exact matched fragment (None
    when unverified -- never fabricated), and whether the freshness guard --
    not a missing/unreadable artifact -- is why it stayed unverified."""

    value: float | None = None
    matched: str | None = None
    stale: bool = False


def _resolve_delimiter(source: str, explicit: str | None) -> str | None:
    """Resolve the field delimiter for a table locator's `source` path.

    An explicit delimiter (already shape-validated by the caller) always
    wins. Otherwise infer from the extension: lower-case `source`, strip one
    trailing `.gz`, then map `.tsv`/`.tab` -> tab, `.csv` -> comma. An
    unrecognized extension with no explicit delimiter returns None, which
    signals a `ClaimsError` to the caller. Pure, no I/O.
    """
    if explicit is not None:
        return explicit
    s = source.lower()
    if s.endswith(".gz"):
        s = s[: -len(".gz")]
    if s.endswith(".tsv") or s.endswith(".tab"):
        return "\t"
    if s.endswith(".csv"):
        return ","
    return None


def _read_table(path: Path, delimiter: str) -> list[list[str]] | None:
    """Read a delimited text table at `path`, gzip-transparent.

    A `.gz`-suffixed name is decompressed via stdlib `gzip` (text mode,
    utf-8); anything else is opened directly (also utf-8). Parses with
    stdlib `csv.reader(f, delimiter=delimiter)` and returns every row as
    `list[list[str]]`. Never raises: a missing file, a directory path, a
    non-UTF-8 file, or an unparseable CSV all degrade to `None` (the caller
    treats `None` as "unresolved").
    """
    try:
        if path.name.endswith(".gz"):
            with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
                return list(csv.reader(f, delimiter=delimiter))
        with open(path, encoding="utf-8", newline="") as f:
            return list(csv.reader(f, delimiter=delimiter))
    except (OSError, UnicodeDecodeError, csv.Error, EOFError, zlib.error):
        return None


def resolve_cell(
    rows: list[list[str]],
    column: str | int,
    row: int | dict[str, str | dict[str, object]],
    header: bool,
) -> tuple[str | None, str]:
    """Resolve one cell out of already-parsed table `rows`.

    Pure, index-safe, never raises -- any unresolved, ambiguous, or
    malformed address returns `(None, reason)` rather than raising (mirrors
    `resolve_pointer`'s "never raises" contract). On success returns
    `(cell_string, "")`; the cell is always a raw string -- parsing it to a
    float is the caller's job, not this function's.

    Header mode (`header=True`): row 0 is the header, the rest are data
    rows. `column` is either a header-name string (a duplicate or absent
    name -> unresolved) or a 0-based field index (out of range ->
    unresolved). `row` is either a 0-based index over the DATA rows (out of
    range -> unresolved, naming the data-row count) or a one-or-more-key
    `{col: predicate}` object selecting the data row whose cells ALL satisfy
    the keyed predicates (a plain string is an exact `.strip()`ed equality, a
    `{"regex": <pattern>}` object a regex `search` over the `.strip()`ed cell,
    and a `gt`/`gte`/`lt`/`lte`/`eq` object a numeric comparison of the
    strictly float-parsed cell; an empty or malformed predicate object is
    unresolved) -- 0 or >1 matches -> unresolved, naming the match count.

    Headerless mode (`header=False`): `column` and `row` must both be
    ints, `row` indexing over ALL rows.

    A row shorter than the resolved column index (a ragged table) ->
    unresolved rather than an `IndexError`. An empty table, or a
    header-only table with 0 data rows, likewise -> unresolved.
    """
    if not rows:
        return None, "table has no rows"

    if header:
        header_row = rows[0]
        data_rows = rows[1:]

        if isinstance(column, str):
            matches = [i for i, name in enumerate(header_row) if name == column]
            if not matches:
                return None, f"column {column!r} not found in header"
            if len(matches) > 1:
                return None, (
                    f"column {column!r} is ambiguous: {len(matches)} header matches"
                )
            col_idx = matches[0]
        elif isinstance(column, int) and not isinstance(column, bool):
            if not (0 <= column < len(header_row)):
                return None, (
                    f"column index {column} out of range ({len(header_row)} header columns)"
                )
            col_idx = column
        else:
            return None, f"invalid column address: {column!r}"

        if isinstance(row, dict):
            if not row:
                return None, f"invalid row key-match: {row!r}"
            predicates = []
            for key_col, key_val in row.items():
                if not isinstance(key_col, str):
                    return None, f"invalid row key-match: {row!r}"
                problem = _row_predicate_error(key_val)
                if problem is not None:
                    return None, f"invalid row predicate for {key_col!r}: {problem}"
                key_matches = [i for i, name in enumerate(header_row) if name == key_col]
                if not key_matches:
                    return None, f"row key column {key_col!r} not found in header"
                if len(key_matches) > 1:
                    return None, (
                        f"row key column {key_col!r} is ambiguous: "
                        f"{len(key_matches)} header matches"
                    )
                predicates.append((key_matches[0], key_val))
            matched = [
                r
                for r in data_rows
                if all(
                    idx < len(r) and _row_predicate_matches(r[idx], wanted)
                    for idx, wanted in predicates
                )
            ]
            if not matched:
                return None, f"row {row!r} matched 0 rows"
            if len(matched) > 1:
                return None, f"row {row!r} matched {len(matched)} rows"
            target_row = matched[0]
        elif isinstance(row, int) and not isinstance(row, bool):
            if not (0 <= row < len(data_rows)):
                return None, (
                    f"row index {row} out of range ({len(data_rows)} data rows)"
                )
            target_row = data_rows[row]
        else:
            return None, f"invalid row address: {row!r}"
    else:
        if not (isinstance(column, int) and not isinstance(column, bool)):
            return None, f"headerless table requires an integer column, got {column!r}"
        if not (isinstance(row, int) and not isinstance(row, bool)):
            return None, f"headerless table requires an integer row, got {row!r}"
        if not (0 <= row < len(rows)):
            return None, f"row index {row} out of range ({len(rows)} rows)"
        target_row = rows[row]
        col_idx = column

    if col_idx < 0 or col_idx >= len(target_row):
        return None, (
            f"row has {len(target_row)} cells, short of column index {col_idx}"
        )

    return target_row[col_idx], ""


def _compile_pattern(pattern: str, flags: tuple[str, ...]) -> re.Pattern[str]:
    """Compile a claim's pattern with its named `flags`; an unknown name raises
    `ValueError` (a `re.error` never is one, so the two stay distinguishable)."""
    unknown = [name for name in flags if name not in _REGEX_FLAGS]
    if unknown:
        raise ValueError(f"unknown pattern flag {unknown[0]!r}")
    bits = 0
    for name in flags:
        bits |= _REGEX_FLAGS[name]
    return re.compile(pattern, bits)


# The operators a numeric row predicate may carry. `eq` composes with a range
# (`{"gte": 0.01, "eq": 0.05}`) and is also valid on its own.
_PREDICATE_OPS = ("gt", "gte", "lt", "lte", "eq")


def _row_predicate_error(predicate: object) -> str | None:
    """Why `predicate` is not a valid row predicate, or None when it is.

    A predicate is a plain string (exact, `.strip()`ed equality), a
    `{"regex": <pattern>}` object (inline flags only -- no `flags` array), or a
    numeric comparison over one or more of `gt`/`gte`/`lt`/`lte`/`eq`. Pure and
    total, so `load_claims` (pre-run refusal) and `resolve_cell` (never raises)
    share one rule set.
    """
    if isinstance(predicate, str):
        return None
    if not isinstance(predicate, dict) or not predicate:
        return f"expected a string, a regex object, or a numeric comparison: {predicate!r}"
    keys = list(predicate)
    unknown = [key for key in keys if key not in _PREDICATE_OPS and key != "regex"]
    if unknown:
        return f"unknown operator {unknown[0]!r}"
    if "regex" in predicate:
        if keys != ["regex"]:
            return "a regex predicate takes no other operator"
        pattern = predicate["regex"]
        if not isinstance(pattern, str) or not pattern.strip():
            return f"invalid regex {pattern!r}"
        try:
            _compile_pattern(pattern, ())
        except (ValueError, re.error) as exc:
            return f"uncompilable regex {pattern!r}: {exc}"
        return None
    for op in keys:
        operand = predicate[op]
        if isinstance(operand, bool) or not isinstance(operand, (int, float)):
            return f"non-numeric operand for {op!r}: {operand!r}"
    return None


def _compare_number(value: float, op: str, operand: float) -> bool:
    if op == "gt":
        return value > operand
    if op == "gte":
        return value >= operand
    if op == "lt":
        return value < operand
    if op == "lte":
        return value <= operand
    return value == operand  # "eq"


def _row_predicate_matches(cell: str, predicate: str | dict) -> bool:
    """True when one table cell satisfies an already-validated `predicate`.

    Exact strings compare the `.strip()`ed cell; a regex is a `search` over it
    (so `^...$` anchors the whole cell); a numeric predicate strictly
    float-parses it -- a cell that does not parse is simply not a match.
    """
    if isinstance(predicate, str):
        return cell.strip() == predicate.strip()
    if "regex" in predicate:
        return _compile_pattern(predicate["regex"], ()).search(cell.strip()) is not None
    try:
        value = float(cell.strip())
    except ValueError:
        return False
    return all(_compare_number(value, op, predicate[op]) for op in predicate)


def resolve_match(
    text: str, pattern: str, flags: tuple[str, ...] = ()
) -> tuple[str | None, str]:
    """Resolve one captured string out of `text` with a user-authored regex.

    Pure, never raises -- any oversized text, uncompilable pattern, ambiguous
    match count, or non-participating capture group returns `(None, reason)`
    rather than raising (mirrors `resolve_cell`'s "never raises" contract). On
    success returns `(captured_string, "")`; the capture is always a raw
    string -- parsing it to a float is the caller's job, not this function's.

    The text size is bounded FIRST, before the pattern is compiled or scanned:
    text over `_MAX_MATCH_BYTES` is unresolved, naming the size and the limit.
    Truncating instead would be dishonest -- it could report "0 matches" for a
    pattern that does match past the cut.

    Matching is STRICT: all non-overlapping matches are found, and exactly one
    is required. 0 matches or N>1 matches -> unresolved, naming the count
    (`resolve_cell`'s "matched N rows" wording shape). Never an arbitrary pick.

    Capture selection: if the compiled pattern has capturing groups, group 1
    is the value (a named group is group 1 too); with no groups, the whole
    match is. A group 1 that did NOT participate in the match yields `None`
    from `match.group(1)` -- the one input shape that would otherwise crash a
    caller on `float(None)` -- so it is unresolved as well.

    Flags are supplied inline in the pattern (`(?i)`, `(?m)`, `(?s)`) or as
    names in `flags` (`"IGNORECASE"`/`"MULTILINE"`/`"DOTALL"`), which combine
    with the inline ones; an unknown name is unresolved, never ignored. The
    compile is wrapped defensively so the contract holds even when called
    directly with an uncompilable pattern (`load_claims` already gates this
    pre-run).
    """
    if len(text) > _MAX_MATCH_BYTES:
        return None, (
            f"text is {len(text)} chars, over the {_MAX_MATCH_BYTES}-char match limit"
        )

    try:
        compiled = _compile_pattern(pattern, flags)
    except ValueError as exc:
        return None, str(exc)
    except re.error as exc:
        return None, f"pattern {pattern!r} is not a valid regex: {exc}"

    matches = list(compiled.finditer(text))
    if len(matches) != 1:
        return None, f"pattern {pattern!r} matched {len(matches)} times"

    match = matches[0]
    captured = match.group(1) if compiled.groups else match.group(0)
    if captured is None:
        return None, (
            f"pattern {pattern!r} capture group did not participate in the match"
        )
    return captured, ""


def _join_source_or_text(v: object) -> str:
    """Join a notebook `source`/`text` field into a single string.

    Jupyter stores these as either a plain `str` or a `list[str]` of line
    fragments (joined with `""` -- the fragments already carry their own
    newlines). A `str` is returned as-is; a `list` is joined over only its
    `str` items (non-string items are skipped, never coerced); anything else
    (None, int, dict, ...) yields `""`. Pure, never raises.
    """
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return "".join(item for item in v if isinstance(item, str))
    return ""


def _cell_has_tag(cell: object, tag: str) -> bool:
    """True when a notebook cell's `metadata.tags` list contains `tag`.

    The `.ipynb` schema stores tags as `cell["metadata"]["tags"]` (a list of
    strings); anything else -- a missing/None metadata, a string tag value, a
    non-list -- is simply not a match. Pure, never raises.
    """
    if not isinstance(cell, dict):
        return False
    metadata = cell.get("metadata")
    tags = metadata.get("tags") if isinstance(metadata, dict) else None
    return isinstance(tags, list) and tag in tags


def resolve_notebook_cell_text(
    doc: object, cell: int | dict[str, str]
) -> tuple[str | None, str]:
    """Resolve one cell's textual output out of an already-parsed notebook.

    Pure, index-safe, never raises -- any malformed document, out-of-range or
    ambiguous cell address, or output-less cell returns `(None, reason)`
    rather than raising (mirrors `resolve_cell`/`resolve_match`'s "never
    raises" contract). On success returns `(text, "")`; the returned text is
    the RAW concatenated cell output -- capturing a number out of it is the
    caller's job, not this function's.

    `doc` is the parsed `.ipynb` JSON (expected a dict with a `cells` list).
    `cell` addresses the target: an `int` indexes the full `cells` array
    (bool is rejected -- it is an int subclass but never a valid address; a
    negative or out-of-range index is unresolved, naming the cell count); a
    `{"contains": s}` object selects the UNIQUE cell whose joined `source`
    contains `s`, and a `{"tag": s}` object the UNIQUE cell whose
    `metadata.tags` list contains `s` (0 or >1 matches -> unresolved, naming
    the match count -- never an arbitrary pick).

    Output text is the concatenation, in `outputs` order, of: `stream`
    outputs named `stdout` (their `text` field) and `execute_result` /
    `display_data` outputs' `data["text/plain"]`. Each field is a `str` or a
    `list[str]`, joined with `""` (see `_join_source_or_text`). `stderr`
    streams and `error` outputs are excluded, as is anything else. A cell that
    contributes no such piece is unresolved ("no textual output").
    """
    if not isinstance(doc, dict):
        return None, "notebook is not a JSON object"
    cells = doc.get("cells")
    if not isinstance(cells, list):
        return None, "notebook has no cells array"

    if isinstance(cell, bool):
        return None, f"invalid cell address: {cell!r}"
    if isinstance(cell, int):
        if not (0 <= cell < len(cells)):
            return None, f"cell index {cell} out of range ({len(cells)} cells)"
        idx = cell
    elif isinstance(cell, dict):
        key = next(iter(cell)) if len(cell) == 1 else None
        if key not in ("contains", "tag") or not isinstance(cell[key], str):
            return None, f"invalid cell address: {cell!r}"
        value = cell[key]
        if key == "contains":
            matches = [
                i
                for i, c in enumerate(cells)
                if value
                in _join_source_or_text(c.get("source") if isinstance(c, dict) else None)
            ]
        else:
            matches = [i for i, c in enumerate(cells) if _cell_has_tag(c, value)]
        if len(matches) != 1:
            return None, (
                f"cell selector {{{key!r}: {value!r}}} matched {len(matches)} cells"
            )
        idx = matches[0]
    else:
        return None, f"invalid cell address: {cell!r}"

    target = cells[idx]
    if not isinstance(target, dict):
        return None, f"cell {idx} is not a cell object"

    outputs = target.get("outputs")
    pieces: list[str] = []
    if isinstance(outputs, list):
        for out in outputs:
            if not isinstance(out, dict):
                continue
            kind = out.get("output_type")
            if kind == "stream":
                if out.get("name") == "stdout":
                    pieces.append(_join_source_or_text(out.get("text")))
            elif kind in ("execute_result", "display_data"):
                data = out.get("data")
                if isinstance(data, dict):
                    pieces.append(_join_source_or_text(data.get("text/plain")))

    if not pieces:
        return None, f"cell {idx} has no textual output"
    return "".join(pieces), ""


@dataclass(frozen=True)
class Claim:
    """One published numeric claim to reproduce: `id` names the metric,
    `value` is the claimed reference number, `tolerance` is the relative
    band (see `classify`) within which an observed value still counts as
    reproducing it. `locator`, when set, means this claim's observed value
    is bound from its own repo-relative file rather than from the flat
    `--results` map (slice-1 behavior, `locator=None`): a `Locator` reads a
    dotted+`[n]` pointer into a JSON file (slice 1.5), a `TableLocator`
    reads one cell out of a TSV/CSV table (slice 3), and a `PatternLocator`
    captures it with a regex over a repo-relative text/log file or -- when
    its `source` is `None` -- over the run's own captured output (slice 4).
    """

    id: str
    value: float
    tolerance: float = _DEFAULT_TOLERANCE
    locator: Locator | TableLocator | PatternLocator | NotebookLocator | None = None


def _claim_pattern(claim_id: str, item: dict) -> tuple[str, tuple[str, ...]]:
    """Validate a claim's `pattern` and optional `flags` pre-run, returning them
    normalized. An unknown flag name is refused here, never ignored."""
    raw_pattern = item["pattern"]
    if not isinstance(raw_pattern, str) or not raw_pattern.strip():
        raise ClaimsError(f"claim {claim_id!r} has an invalid 'pattern': {raw_pattern!r}")

    raw_flags = item.get("flags", [])
    if not isinstance(raw_flags, list) or not all(
        isinstance(name, str) for name in raw_flags
    ):
        raise ClaimsError(f"claim {claim_id!r} has an invalid 'flags': {raw_flags!r}")
    flags = tuple(raw_flags)

    try:
        _compile_pattern(raw_pattern, flags)
    except ValueError as exc:
        raise ClaimsError(f"claim {claim_id!r} has {exc}") from exc
    except re.error as exc:
        raise ClaimsError(f"claim {claim_id!r} has an uncompilable 'pattern': {exc}") from exc
    return raw_pattern, flags


def load_claims(path: str | Path) -> list[Claim]:
    """Read a JSON claims file: a list of `{"id", "value", "tolerance"?}` objects.

    Raises `ClaimsError` on anything invalid: malformed JSON, a non-list top
    level, a claim missing `id`/`value`, a non-numeric `value` (a Python
    `bool` does not count, even though `bool` is an `int` subclass), a
    duplicate `id`, or a `tolerance <= 0`.
    """
    text = Path(path).read_text()
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ClaimsError(f"claims file is not valid JSON: {exc}") from exc

    if not isinstance(raw, list):
        raise ClaimsError("claims file must contain a JSON list of claim objects")

    claims: list[Claim] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ClaimsError(f"claim at index {index} must be a JSON object")
        if "id" not in item:
            raise ClaimsError(f"claim at index {index} is missing required field 'id'")
        if "value" not in item:
            raise ClaimsError(f"claim at index {index} is missing required field 'value'")

        claim_id = item["id"]
        if claim_id in seen_ids:
            raise ClaimsError(f"duplicate claim id: {claim_id!r}")
        seen_ids.add(claim_id)

        value = item["value"]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ClaimsError(f"claim {claim_id!r} has a non-numeric 'value': {value!r}")

        tolerance = item.get("tolerance", _DEFAULT_TOLERANCE)
        if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)):
            raise ClaimsError(f"claim {claim_id!r} has a non-numeric 'tolerance': {tolerance!r}")
        if tolerance <= 0:
            raise ClaimsError(f"claim {claim_id!r} has a non-positive 'tolerance': {tolerance!r}")

        has_from = "from" in item
        has_path = "path" in item
        has_pattern = "pattern" in item
        has_flags = "flags" in item
        has_cell = "cell" in item
        has_column = "column" in item
        has_row = "row" in item
        has_delimiter = "delimiter" in item
        has_header = "header" in item
        has_table_field = has_column or has_row or has_delimiter or has_header

        if not has_from and not has_pattern and (has_path or has_table_field or has_cell):
            raise ClaimsError(
                f"claim {claim_id!r} must set 'from' together with 'path', or with "
                "'column'+'row', or with 'cell'+'pattern', or neither"
            )
        if has_flags and not has_pattern:
            raise ClaimsError(f"claim {claim_id!r} sets 'flags' without 'pattern'")

        source: str | None = None
        if has_from:
            raw_from = item["from"]
            if not isinstance(raw_from, str) or not raw_from.strip():
                raise ClaimsError(f"claim {claim_id!r} has an invalid 'from': {raw_from!r}")
            source = raw_from

        locator: Locator | TableLocator | PatternLocator | NotebookLocator | None = None
        if has_cell:
            # Notebook locator (slice 5): `cell` is only meaningful together
            # with a `from` notebook and a `pattern`, and never alongside a
            # JSON `path` or any table field -- the four locator families are
            # mutually exclusive.
            if not has_from:
                raise ClaimsError(
                    f"claim {claim_id!r} 'cell' requires 'from' (a notebook path)"
                )
            if not has_pattern:
                raise ClaimsError(
                    f"claim {claim_id!r} 'cell' requires 'pattern'"
                )
            if has_path:
                raise ClaimsError(
                    f"claim {claim_id!r} must set 'cell'+'pattern' or 'path', not both"
                )
            if has_table_field:
                raise ClaimsError(
                    f"claim {claim_id!r} must set 'cell'+'pattern' or 'column'+'row', "
                    "not both (a table field has no meaning for a notebook locator)"
                )

            raw_cell = item["cell"]
            cell: int | dict[str, str]
            if isinstance(raw_cell, bool):
                raise ClaimsError(f"claim {claim_id!r} has an invalid 'cell': {raw_cell!r}")
            if isinstance(raw_cell, int):
                if raw_cell < 0:
                    raise ClaimsError(
                        f"claim {claim_id!r} has a negative 'cell' index: {raw_cell!r}"
                    )
                cell = raw_cell
            elif isinstance(raw_cell, dict):
                key = next(iter(raw_cell)) if len(raw_cell) == 1 else None
                if key not in ("contains", "tag"):
                    raise ClaimsError(
                        f"claim {claim_id!r} has an invalid 'cell' object (expected a "
                        f"single 'contains' or 'tag' key): {raw_cell!r}"
                    )
                raw_value = raw_cell[key]
                if not isinstance(raw_value, str) or not raw_value.strip():
                    raise ClaimsError(
                        f"claim {claim_id!r} has an invalid 'cell' {key!r} value: "
                        f"{raw_value!r}"
                    )
                cell = raw_cell
            else:
                raise ClaimsError(f"claim {claim_id!r} has an invalid 'cell': {raw_cell!r}")

            raw_pattern, flags = _claim_pattern(claim_id, item)
            locator = NotebookLocator(
                source=raw_from, cell=cell, pattern=raw_pattern, flags=flags
            )
        elif has_pattern:
            if has_path:
                raise ClaimsError(
                    f"claim {claim_id!r} must set 'path' or 'pattern', not both"
                )
            if has_table_field:
                raise ClaimsError(
                    f"claim {claim_id!r} must set 'column'+'row' or 'pattern', not both "
                    "(a table field has no meaning for a pattern locator)"
                )

            raw_pattern, flags = _claim_pattern(claim_id, item)
            locator = PatternLocator(source=source, pattern=raw_pattern, flags=flags)
        elif has_from:
            is_table_mode = has_column or has_row
            if has_path and is_table_mode:
                raise ClaimsError(
                    f"claim {claim_id!r} must set 'path' or 'column'+'row', not both"
                )

            if has_path:
                raw_path = item["path"]
                if not isinstance(raw_path, str) or not raw_path.strip():
                    raise ClaimsError(f"claim {claim_id!r} has an invalid 'path': {raw_path!r}")
                locator = Locator(source=raw_from, path=raw_path)
            elif is_table_mode:
                if has_column != has_row:
                    raise ClaimsError(
                        f"claim {claim_id!r} must set both 'column' and 'row', or neither"
                    )

                raw_header = item.get("header", True)
                if not isinstance(raw_header, bool):
                    raise ClaimsError(
                        f"claim {claim_id!r} has a non-boolean 'header': {raw_header!r}"
                    )
                header = raw_header

                raw_column = item["column"]
                if isinstance(raw_column, bool) or not isinstance(raw_column, (str, int)):
                    raise ClaimsError(
                        f"claim {claim_id!r} has an invalid 'column': {raw_column!r}"
                    )
                if isinstance(raw_column, str):
                    if not raw_column.strip():
                        raise ClaimsError(
                            f"claim {claim_id!r} has an invalid 'column': {raw_column!r}"
                        )
                    if header is False:
                        raise ClaimsError(
                            f"claim {claim_id!r} 'column' names a header field but "
                            "'header' is false"
                        )
                    column: str | int = raw_column
                else:
                    if raw_column < 0:
                        raise ClaimsError(
                            f"claim {claim_id!r} has a negative 'column' index: {raw_column!r}"
                        )
                    column = raw_column

                raw_row = item["row"]
                if isinstance(raw_row, bool) or not isinstance(raw_row, (int, dict)):
                    raise ClaimsError(f"claim {claim_id!r} has an invalid 'row': {raw_row!r}")
                row: int | dict[str, str | dict[str, object]]
                if isinstance(raw_row, dict):
                    if header is False:
                        raise ClaimsError(
                            f"claim {claim_id!r} 'row' is a key-match object but "
                            "'header' is false"
                        )
                    if len(raw_row) < 1:
                        raise ClaimsError(
                            f"claim {claim_id!r} has an invalid 'row' object (expected "
                            f"one or more keys): {raw_row!r}"
                        )
                    for row_key, row_val in raw_row.items():
                        if not isinstance(row_key, str) or not row_key.strip():
                            raise ClaimsError(
                                f"claim {claim_id!r} has an invalid 'row' key: {row_key!r}"
                            )
                        problem = _row_predicate_error(row_val)
                        if problem is not None:
                            raise ClaimsError(
                                f"claim {claim_id!r} has an invalid 'row' predicate for "
                                f"{row_key!r}: {problem}"
                            )
                    row = raw_row
                else:
                    if raw_row < 0:
                        raise ClaimsError(
                            f"claim {claim_id!r} has a negative 'row' index: {raw_row!r}"
                        )
                    row = raw_row

                raw_delimiter = item.get("delimiter")
                if has_delimiter and (
                    not isinstance(raw_delimiter, str) or len(raw_delimiter) != 1
                ):
                    raise ClaimsError(
                        f"claim {claim_id!r} has an invalid 'delimiter': {raw_delimiter!r}"
                    )
                delimiter = _resolve_delimiter(raw_from, raw_delimiter if has_delimiter else None)
                if delimiter is None:
                    raise ClaimsError(
                        f"claim {claim_id!r} 'from' has an unrecognized extension and no "
                        f"'delimiter' was given: {raw_from!r}"
                    )

                locator = TableLocator(
                    source=raw_from, column=column, row=row, delimiter=delimiter, header=header
                )
            else:
                raise ClaimsError(
                    f"claim {claim_id!r} must set 'path' or 'column'+'row' when 'from' is set"
                )

        claims.append(
            Claim(
                id=claim_id,
                value=float(value),
                tolerance=float(tolerance),
                locator=locator,
            )
        )

    return claims


def classify(
    claimed: float, observed: float | None, tolerance: float
) -> tuple[ClaimStatus, float | None, str]:
    """Classify one observed value against a claimed reference within tolerance.

    `delta` is the RELATIVE delta (`_relative_delta(observed, claimed)`, i.e.
    consistent with the tolerance band it is compared against, not a plain
    `observed - claimed`). `None` observed, or either value being NaN/inf,
    is always `unverified` with `delta=None` -- never `diverged`.
    """
    if observed is None:
        return "unverified", None, "claim not verified: no observed value"

    if any(math.isnan(x) or math.isinf(x) for x in (observed, claimed)):
        return (
            "unverified",
            None,
            f"claim not verified: observed={observed} or claimed={claimed} is not finite",
        )

    delta = _relative_delta(observed, claimed)

    if abs(observed - claimed) <= 1e-9:
        return "reproduced", delta, f"observed {observed} matches claimed {claimed} exactly"

    if delta <= tolerance:
        return (
            "within_tolerance",
            delta,
            f"observed {observed} is within tolerance {tolerance} of claimed {claimed} "
            f"(delta={delta})",
        )

    return (
        "diverged",
        delta,
        f"observed {observed} diverged from claimed {claimed} (delta={delta}, "
        f"tolerance={tolerance})",
    )


def run_reproduction(
    repo: str,
    run_command: str,
    claims: list[Claim],
    *,
    executor: Callable[[list[str], Path], tuple[int, str]],
    claims_sha256: str,
    results_path: str = "results.json",
    created_at: str,
    run_started_at: float | None = None,
    reproduce_id: str,
    allow_install: bool = False,
    installer: Installer = default_installer,
) -> ReproduceRecord:
    """Drive `executor` over `repo`, then classify every claim.

    A nonzero exit code short-circuits: every claim is `unverified` and the
    results file is never read. On a zero exit, a missing or unparseable
    results file also marks every claim `unverified`; otherwise each claim's
    id is looked up in the flat `{id: number}` results map (a missing key or
    a non-numeric value, including `bool`, is `unverified`; everything else
    goes through `classify`). Extra keys in the results map that no claim
    names are ignored. `created_at`/`reproduce_id` are passed in, never
    generated here, so the record stays deterministic.

    A located claim also records the exact fragment the locator extracted as
    `ClaimResult.matched_output` (capped at `_MAX_MATCHED_OUTPUT_CHARS`); an
    unlocated claim, or one whose locator resolved nothing, carries `None`.
    `ClaimResult.stale` is True exactly when the freshness guard -- not a
    missing/unreadable artifact -- is why a claim stayed unverified.

    When the first run fails (nonzero exit) and `allow_install` is True, this
    makes bounded env-resurrection attempts: detect a missing Python module
    in the run's output (`detect_missing_module`), resolve its PyPI package
    name (`package_for_import`), install it via `installer`, and retry the
    run. A retry that fails with a NEW missing module starts another cycle,
    at most `_MAX_INSTALLS` installs per run. A module already installed
    this run is never installed again (per-run seen-set), so the loop
    provably terminates even when the same failure keeps recurring.
    `repair_history` records one step per install attempt (empty when
    `allow_install` is False, or when no installable module was detected).
    The final `exit_code` on the record is always the LAST run's exit code
    (the retried one, if a retry happened).
    """
    repo_path = Path(repo)
    repo_root = repo_path.resolve()
    _json_cache: dict[str, object | None] = {}
    _table_cache: dict[str, list[list[str]] | None] = {}
    _text_cache: dict[str, str | None] = {}
    _notebook_cache: dict[str, object | None] = {}

    def _require_fresh(
        resolved: Path, noun: str, label: str, *, mtime: float | None = None
    ) -> str | None:
        """Return an UNVERIFIED message when `resolved` was not rewritten by
        this run, else None.

        A committed artifact holds the AUTHORS' stored output, so binding it
        would report a false REPRODUCED for a computation that never ran --
        the exact failure the verdict contract exists to prevent. The
        undecidable "was this recomputed?" question is replaced by the
        decidable one: was this file rewritten by THIS run?

        Non-bypassable: `run_started_at is None` is a programming error, not
        an UNVERIFIED. A None meaning "guard off" would silently disable a
        false-pass guard, so it raises loudly instead.

        A path that cannot be stat()'d returns None -- NOT a freshness
        failure. The caller's own missing/unreadable branch owns that
        message, so this helper never pre-empts a more specific error.

        `mtime` lets a caller that already has a `stat()` result (the
        notebook observer needs the size from the same call) reuse it
        instead of statting twice; the rule applied is identical.

        NEVER pass `follow_symlinks=False` to the `stat()` below. Statting
        the link itself would let a `ln -s` created during the run stamp a
        fresh mtime onto ancient, author-committed content -- reintroducing
        the exact false pass this guard exists to prevent. `Path.stat()`
        follows symlinks by default; keep it that way.
        """
        if run_started_at is None:
            raise ValueError("run_started_at is required to read an artifact off disk")
        if mtime is None:
            try:
                mtime = resolved.stat().st_mtime
            except OSError:
                return None
        if mtime < run_started_at:
            return f"{noun} {label} was not rewritten by this run (mtime predates run start)"
        return None

    def _observe_located(loc: Locator) -> tuple[_Observation, str]:
        """Bind one located claim's observed value from its own repo-relative
        JSON file at `loc.path`. Never reads outside the repo (containment
        guard below); every resolution failure returns an unverified
        `_Observation` rather than raising -- the caller always maps that to
        `unverified`. Requires the file to have been rewritten by this run
        (freshness guard) before it is ever parsed.
        """
        resolved = (repo_path / loc.source).resolve()
        try:
            resolved.relative_to(repo_root)  # defense-in-depth: never read outside repo
        except ValueError:
            return _Observation(), f"locator 'from' {loc.source!r} escapes the repo"

        # The guard fires before the file is parsed and before the parse
        # enters the per-run cache, so a stale artifact is never read for
        # content.
        stale = _require_fresh(resolved, "locator file", repr(loc.source))
        if stale is not None:
            return _Observation(stale=True), stale

        key = str(resolved)
        if key not in _json_cache:
            parsed: object | None = None
            if resolved.exists():
                try:
                    parsed = json.loads(resolved.read_text())
                except (ValueError, OSError):
                    # ValueError covers json.JSONDecodeError (already a
                    # ValueError subclass) and UnicodeDecodeError raised by
                    # read_text() on a non-UTF-8 file (also a ValueError
                    # subclass, NOT an OSError) -- both are "unparseable".
                    parsed = None
            _json_cache[key] = parsed

        if not resolved.exists():
            return _Observation(), f"locator file {loc.source!r} is missing"

        parsed = _json_cache[key]
        if parsed is None:
            return _Observation(), f"locator file {loc.source!r} is not valid JSON"

        target = resolve_pointer(parsed, loc.path)
        if target is None:
            return _Observation(), f"locator path {loc.path!r} did not resolve in {loc.source!r}"

        if isinstance(target, bool) or not isinstance(target, (int, float)):
            return _Observation(), (
                f"locator value at {loc.path!r} in {loc.source!r} is not a number: {target!r}"
            )

        if math.isnan(target) or math.isinf(target):
            return _Observation(), (
                f"locator value at {loc.path!r} in {loc.source!r} is not finite: {target!r}"
            )

        return _Observation(float(target), _matched_output(json.dumps(target))), ""

    def _observe_table_located(loc: TableLocator) -> tuple[_Observation, str]:
        """Bind one located claim's observed value from a cell in its own
        repo-relative TSV/CSV file. Sibling of `_observe_located`: same
        containment guard (never reads outside the repo), same "parse once,
        cache by resolved absolute path" shape (`_table_cache` in place of
        `_json_cache`), same "any resolution failure -> unverified" contract
        the caller always maps to `unverified`.

        Unlike the JSON reader, a numeric-looking cell STRING (e.g. "30.4")
        is the normal, valid case here -- every table cell is a string, so
        it is float-parsed and, if finite, returned as the observed value
        rather than rejected the way a JSON numeric string is.

        Requires the file to have been rewritten by this run (freshness
        guard) before it is ever parsed.
        """
        resolved = (repo_path / loc.source).resolve()
        try:
            resolved.relative_to(repo_root)  # defense-in-depth: never read outside repo
        except ValueError:
            return _Observation(), f"locator 'from' {loc.source!r} escapes the repo"

        stale = _require_fresh(resolved, "table", repr(loc.source))
        if stale is not None:
            return _Observation(stale=True), stale

        key = str(resolved)
        if key not in _table_cache:
            _table_cache[key] = _read_table(resolved, loc.delimiter)

        rows = _table_cache[key]
        if rows is None:
            return _Observation(), f"locator file {loc.source!r} is missing or unreadable"

        cell, reason = resolve_cell(rows, loc.column, loc.row, loc.header)
        if cell is None:
            return _Observation(), f"locator cell in {loc.source!r} did not resolve: {reason}"

        try:
            value = float(cell)
        except ValueError:
            return _Observation(), (
                f"locator cell {cell!r} in {loc.source!r} is not a finite number"
            )

        if math.isnan(value) or math.isinf(value):
            return _Observation(), (
                f"locator cell {cell!r} in {loc.source!r} is not finite: {value!r}"
            )

        return _Observation(value, _matched_output(cell)), ""

    def _observe_pattern_located(loc: PatternLocator) -> tuple[_Observation, str]:
        """Bind one located claim's observed value by matching a user-authored
        regex against free text. Sibling of `_observe_table_located`: same
        containment guard for the file case (never reads outside the repo),
        same "read once, cache by resolved absolute path" shape (`_text_cache`
        in place of `_table_cache`), same "any resolution failure ->
        unverified" contract the caller always maps to `unverified`.

        Two addressing modes. With `loc.source is None` the text is the run's
        own captured combined stdout+stderr -- `run_output` from the enclosing
        scope, with NO path join and no filesystem access at all. Because this
        is a closure over the *variable* and it is only ever CALLED from the
        dispatch loop below -- after the env-resurrection retry rebinds
        `run_output` -- a stdout claim automatically observes the RETRIED run's
        output under `--allow-install`, never the failed first run's. With
        `loc.source` set the text is that repo-relative file, whose size is
        checked via `stat()` BEFORE any read, so an oversized log is never
        pulled into memory.

        File mode requires the file to have been rewritten by this run
        (freshness guard, checked before the size cap and before any read);
        stdout mode is exempt by construction -- it is the run's own captured
        output, so it can never be a stale, pre-existing artifact.

        Like the table reader and unlike the JSON reader, a numeric-looking
        capture STRING is the normal, valid case -- a regex capture is a
        string by construction -- so it is stripped, float-parsed and, if
        finite, returned as the observed value rather than rejected.
        """
        if loc.source is None:
            text: str | None = run_output
            where = "the run output"
        else:
            resolved = (repo_path / loc.source).resolve()
            try:
                resolved.relative_to(repo_root)  # defense-in-depth: never read outside repo
            except ValueError:
                return _Observation(), f"locator 'from' {loc.source!r} escapes the repo"

            stale = _require_fresh(resolved, "locator file", repr(loc.source))
            if stale is not None:
                return _Observation(stale=True), stale

            key = str(resolved)
            if key not in _text_cache:
                try:
                    size = resolved.stat().st_size
                except OSError:
                    size = None
                if size is not None and size > _MAX_MATCH_BYTES:
                    # Deliberately NOT cached: caching would have to store a
                    # None text, which reads back as "missing or unreadable"
                    # and would lose the size in the message. A repeat stat()
                    # is cheap and still never reads the file.
                    return _Observation(), (
                        f"locator file {loc.source!r} is {size} bytes, "
                        f"over the {_MAX_MATCH_BYTES}-byte match limit"
                    )
                loaded: str | None = None
                try:
                    loaded = resolved.read_text()
                except (OSError, ValueError):
                    # ValueError covers UnicodeDecodeError on a non-UTF-8 file
                    # (a ValueError subclass, NOT an OSError -- see the comment
                    # in _observe_located); OSError covers missing files and a
                    # directory given as `from`.
                    loaded = None
                _text_cache[key] = loaded

            text = _text_cache[key]
            where = repr(loc.source)

        if text is None:
            return _Observation(), f"locator file {loc.source!r} is missing or unreadable"

        captured, reason = resolve_match(text, loc.pattern, loc.flags)
        if captured is None:
            return _Observation(), f"locator pattern in {where} did not resolve: {reason}"

        try:
            value = float(captured.strip())
        except ValueError:
            return _Observation(), (
                f"locator capture {captured!r} in {where} is not a finite number"
            )

        if math.isnan(value) or math.isinf(value):
            return _Observation(), (
                f"locator capture {captured!r} in {where} is not finite: {value!r}"
            )

        return _Observation(value, _matched_output(captured)), ""

    def _observe_notebook_located(loc: NotebookLocator) -> tuple[float | None, str]:
        """Bind one located claim's observed value out of a Jupyter notebook
        the run itself rewrote. Sibling of `_observe_pattern_located`, with one
        extra, load-bearing gate: a **freshness guard**. A notebook whose mtime
        predates `run_started_at` was NOT produced by this run -- it is an
        author's committed artifact -- so it is UNVERIFIED even when its stored
        output matches the claim exactly. This is the whole point of the
        locator: a bound value must come from what THIS run computed, never
        from a checked-in cell output. The guard fires BEFORE the file is ever
        parsed, so a stale notebook is never even read for content.

        `run_started_at is None` here is a programming error, not an
        UNVERIFIED: this observer must never be reached without a stamped run
        start, so it raises loudly rather than silently degrading.

        Same containment guard, same "parse once, cache by resolved absolute
        path" shape (`_notebook_cache`), and same "any resolution failure ->
        unverified" contract the caller maps to `unverified` as the other
        observers. Like the table/pattern readers, a numeric-looking capture
        STRING is the normal valid case, so it is stripped, float-parsed and,
        if finite, returned.
        """
        if run_started_at is None:
            raise ValueError("run_started_at is required to verify a notebook locator")

        resolved = (repo_path / loc.source).resolve()
        try:
            resolved.relative_to(repo_root)  # defense-in-depth: never read outside repo
        except ValueError:
            return _Observation(), f"locator 'from' {loc.source!r} escapes the repo"

        try:
            stat = resolved.stat()  # one stat() gives both size and mtime
        except OSError:
            return _Observation(), f"notebook {loc.source!r} is missing or unreadable"

        if stat.st_size > _MAX_NOTEBOOK_BYTES:
            return _Observation(), (
                f"notebook {loc.source!r} is {stat.st_size} bytes, "
                f"over the {_MAX_NOTEBOOK_BYTES}-byte match limit"
            )

        # Same rule as every other surface, applied through the shared
        # helper rather than a second inline copy (the two had already
        # drifted). The already-obtained mtime is passed in so this observer
        # keeps its single stat() and its size-check-first ordering.
        stale = _require_fresh(
            resolved, "notebook", repr(loc.source), mtime=stat.st_mtime
        )
        if stale is not None:
            return _Observation(stale=True), stale

        key = str(resolved)
        if key not in _notebook_cache:
            doc: object | None = None
            try:
                doc = json.loads(resolved.read_text())
            except (ValueError, OSError):
                # ValueError covers json.JSONDecodeError and UnicodeDecodeError
                # on a non-UTF-8 file (both ValueError subclasses); OSError
                # covers a file that vanished between the stat() and the read.
                doc = None
            _notebook_cache[key] = doc

        doc = _notebook_cache[key]
        if doc is None:
            return _Observation(), f"notebook {loc.source!r} is not valid JSON"

        text, reason = resolve_notebook_cell_text(doc, loc.cell)
        if text is None:
            return _Observation(), f"notebook cell in {loc.source!r} did not resolve: {reason}"

        captured, reason = resolve_match(text, loc.pattern, loc.flags)
        if captured is None:
            return _Observation(), f"notebook pattern in {loc.source!r} did not resolve: {reason}"

        try:
            value = float(captured.strip())
        except ValueError:
            return _Observation(), (
                f"notebook capture {captured!r} in {loc.source!r} is not a finite number"
            )

        if math.isnan(value) or math.isinf(value):
            return _Observation(), (
                f"notebook capture {captured!r} in {loc.source!r} is not finite: {value!r}"
            )

        return _Observation(value, _matched_output(captured)), ""

    exit_code, run_output = executor(shlex.split(run_command), repo_path)
    repair_history: list[RepairStep] = []

    if exit_code != 0 and allow_install:
        seen: set[str] = set()
        installs = 0
        while exit_code != 0 and installs < _MAX_INSTALLS:
            module = detect_missing_module(run_output)
            if module is None or module in seen:
                break
            seen.add(module)
            installs += 1
            target = package_for_import(module)
            diagnosis = Diagnosis(
                failure_class="missing_dependency",
                root_cause=f"missing Python module {module!r}",
                evidence=[run_output[:500]],
                confidence=0.8,
            )
            patch = Patch(
                kind="env",
                operation={"install": target},
                rationale=f"install {target} (import {module}) and retry",
                risk="needs_confirmation",
                expected_signal="run exits 0 after install",
            )
            install_rc = installer(_pip_install_argv(target), repo_path)
            if install_rc != 0:
                repair_history.append(
                    RepairStep(
                        attempt=installs,
                        diagnosis=diagnosis,
                        patch=patch,
                        outcome="install_failed",
                        detail=f"pip install {target} exited {install_rc}",
                        # pip exited non-zero: the patch was proposed but its
                        # operation never ran.
                        patch_applied=False,
                    )
                )
                break
            exit_code, run_output = executor(shlex.split(run_command), repo_path)
            if exit_code != 0:
                detail = f"installed {target} (import {module}); retry exited {exit_code}"
                # Name a same-module re-detection in the step that precedes it:
                # the install did not take (different-interpreter symptom), so
                # the seen-set would stop the loop next iteration -- the step
                # says why instead of leaving it implicit.
                if detect_missing_module(run_output) == module:
                    detail += "; same module re-detected -- not re-installing"
                repair_history.append(
                    RepairStep(
                        attempt=installs,
                        diagnosis=diagnosis,
                        patch=patch,
                        outcome="retry_failed",
                        detail=detail,
                        # The install SUCCEEDED (install_rc == 0) -- the
                        # patch was enacted and the loop proceeded to retry.
                        # The retry then failed on its own, which is a
                        # separate fact: applied != successful.
                        patch_applied=True,
                    )
                )
            else:
                repair_history.append(
                    RepairStep(
                        attempt=installs,
                        diagnosis=diagnosis,
                        patch=patch,
                        outcome="installed_and_retried",
                        detail=f"installed {target} (import {module}); retry exited 0",
                        patch_applied=True,
                    )
                )
        # module is None (or already installed this run): nothing new to
        # record -- honest UNVERIFIED via the short-circuit below.

    if exit_code != 0:
        claim_results = [
            ClaimResult(
                id=claim.id,
                status="unverified",
                claimed=claim.value,
                observed=None,
                tolerance=claim.tolerance,
                delta=None,
                message=f"run did not complete (exit {exit_code})",
            )
            for claim in claims
        ]
        return ReproduceRecord(
            reproduce_id=reproduce_id,
            repo=repo,
            run_command=run_command,
            claims_sha256=claims_sha256,
            claim_results=claim_results,
            exit_code=exit_code,
            created_at=created_at,
            repair_history=repair_history,
        )

    results_file = repo_path / results_path
    results: dict | None = None
    results_stale: str | None = None
    if results_file.exists():
        # Freshness before parse: a committed results.json is the authors'
        # stored output, not this run's, and binding it would be a false
        # REPRODUCED. A stale file is never read for content.
        results_stale = _require_fresh(results_file, "results file", repr(results_path))
        if results_stale is None:
            try:
                loaded = json.loads(results_file.read_text())
            # UnicodeDecodeError is not a JSONDecodeError: a non-UTF-8 file
            # (binary, latin-1, a mis-encoded artifact) must degrade to
            # "unparseable", never escape the guard as a crash.
            except (json.JSONDecodeError, UnicodeDecodeError):
                loaded = None
            if isinstance(loaded, dict):
                results = loaded

    claim_results = []
    for claim in claims:
        if claim.locator is not None:
            # Explicit isinstance chain, never an unguarded fallback: a
            # PatternLocator dropping into the JSON reader would raise
            # AttributeError on the missing `.path`.
            if isinstance(claim.locator, NotebookLocator):
                observation, fail_msg = _observe_notebook_located(claim.locator)
            elif isinstance(claim.locator, TableLocator):
                observation, fail_msg = _observe_table_located(claim.locator)
            elif isinstance(claim.locator, PatternLocator):
                observation, fail_msg = _observe_pattern_located(claim.locator)
            else:
                observation, fail_msg = _observe_located(claim.locator)
            if observation.value is None:
                claim_results.append(
                    ClaimResult(
                        id=claim.id,
                        status="unverified",
                        claimed=claim.value,
                        observed=None,
                        tolerance=claim.tolerance,
                        delta=None,
                        message=fail_msg,
                        stale=observation.stale,
                    )
                )
                continue

            status, delta, message = classify(
                claim.value, observation.value, claim.tolerance
            )
            claim_results.append(
                ClaimResult(
                    id=claim.id,
                    status=status,
                    claimed=claim.value,
                    observed=observation.value,
                    tolerance=claim.tolerance,
                    delta=delta,
                    message=message,
                    matched_output=observation.matched,
                    stale=observation.stale,
                )
            )
            continue

        if results_stale is not None:
            claim_results.append(
                ClaimResult(
                    id=claim.id,
                    status="unverified",
                    claimed=claim.value,
                    observed=None,
                    tolerance=claim.tolerance,
                    delta=None,
                    message=results_stale,
                    stale=True,
                )
            )
            continue

        if results is None:
            claim_results.append(
                ClaimResult(
                    id=claim.id,
                    status="unverified",
                    claimed=claim.value,
                    observed=None,
                    tolerance=claim.tolerance,
                    delta=None,
                    message=f"results file '{results_path}' is missing or unparseable",
                )
            )
            continue

        if claim.id not in results:
            claim_results.append(
                ClaimResult(
                    id=claim.id,
                    status="unverified",
                    claimed=claim.value,
                    observed=None,
                    tolerance=claim.tolerance,
                    delta=None,
                    message=f"claim {claim.id!r} not found in results",
                )
            )
            continue

        raw_observed = results[claim.id]
        if isinstance(raw_observed, bool) or not isinstance(raw_observed, (int, float)):
            claim_results.append(
                ClaimResult(
                    id=claim.id,
                    status="unverified",
                    claimed=claim.value,
                    observed=None,
                    tolerance=claim.tolerance,
                    delta=None,
                    message=f"claim {claim.id!r} has a non-numeric observed value: "
                    f"{raw_observed!r}",
                )
            )
            continue

        observed = float(raw_observed)
        status, delta, message = classify(claim.value, observed, claim.tolerance)
        claim_results.append(
            ClaimResult(
                id=claim.id,
                status=status,
                claimed=claim.value,
                observed=observed,
                tolerance=claim.tolerance,
                delta=delta,
                message=message,
            )
        )

    return ReproduceRecord(
        reproduce_id=reproduce_id,
        repo=repo,
        run_command=run_command,
        claims_sha256=claims_sha256,
        claim_results=claim_results,
        exit_code=exit_code,
        created_at=created_at,
        repair_history=repair_history,
    )


def prune_reproduce_checkouts(
    runs_dir: str | Path, *, keep: int, current_id: str
) -> list[str]:
    """Remove the `source/` checkouts of the `keep` oldest remote reproduce runs.

    Eligibility is deliberately narrow: only `<runs-dir>/<id>/source` where the
    run's own record says `source_url` is set (a checkout this feature created).
    A local-path run and the current run are never touched. Oldest is ordered by
    the record's `created_at` (dir name as a tie-break). Returns one message per
    removal that failed -- an empty list means every eligible checkout was pruned.
    """
    candidates: list[tuple[str, Path]] = []
    for bundle in Path(runs_dir).iterdir():
        source = bundle / "source"
        if bundle.name == current_id or not source.is_dir():
            continue
        try:
            record = json.loads((bundle / "reproduce_record.json").read_text())
        except (OSError, ValueError):
            continue
        if record.get("source_url"):
            candidates.append((record.get("created_at") or bundle.name, bundle))
    candidates.sort(key=lambda item: (item[0], item[1].name))

    failures: list[str] = []
    for _, bundle in candidates[:keep]:
        try:
            shutil.rmtree(bundle / "source")
        except OSError as exc:
            failures.append(f"could not prune {bundle / 'source'}: {exc}")
    return failures


def reduce_reproduction(results: list[ClaimResult]) -> dict:
    """Per-status counts over a list of claim results, plus a one-line summary.

    Pure: never mutates its input, never re-derives or upgrades a claim's status
    -- it only counts what each ClaimResult already says (mirrors the QC verdict
    contract: no silent upgrades to "reproduced").
    """
    counts = {status: 0 for status in _STATUSES}
    for result in results:
        counts[result.status] += 1

    total = len(results)
    if total == 0:
        summary = "no claims to reproduce"
    else:
        other = [f"{counts[status]} {status}" for status in _STATUSES[1:] if counts[status]]
        summary = f"{counts['reproduced']}/{total} reproduced"
        if other:
            summary += f", {', '.join(other)}"

    return {**counts, "summary": summary}

"""Boundary tests for C8 slice 5 phase 1: the pure notebook cell-output
extractor `resolve_notebook_cell_text`.

Strict TDD: this file is written before `resolve_notebook_cell_text` exists in
src/contig/verification/reproduce.py.

Mirrors tests/test_reproduce_pattern_locator.py's structure (the pure regex
capture resolver tests): `resolve_notebook_cell_text` must NEVER raise -- any
malformed document, out-of-range/ambiguous cell address, or output-less cell
returns `(None, reason)` rather than raising. On success it returns the RAW
extracted output text; parsing/capturing from it is the caller's job.

The extraction rule (locked in the plan): output text is the concatenation, in
`outputs` order, of `stream` outputs named `stdout` (`text` field) and
`execute_result`/`display_data` outputs' `data["text/plain"]`. Both `str` and
`list[str]` shapes are joined with `""`. `stderr` streams and `error` outputs
are excluded.
"""

from __future__ import annotations

from contig.verification.reproduce import resolve_notebook_cell_text

# ---------------------------------------------------------------------------
# small builders (notebook JSON is just already-parsed dicts/lists)
# ---------------------------------------------------------------------------


def _stdout(text):
    return {"output_type": "stream", "name": "stdout", "text": text}


def _stderr(text):
    return {"output_type": "stream", "name": "stderr", "text": text}


def _result(text_plain):
    return {"output_type": "execute_result", "data": {"text/plain": text_plain}}


def _display(text_plain):
    return {"output_type": "display_data", "data": {"text/plain": text_plain}}


def _error():
    return {
        "output_type": "error",
        "ename": "ValueError",
        "evalue": "boom",
        "traceback": ["Traceback", "ValueError: boom"],
    }


def _code(source, outputs):
    return {"cell_type": "code", "source": source, "outputs": outputs}


def _doc(*cells):
    return {"cells": list(cells)}


# ---------------------------------------------------------------------------
# happy paths -- int addressing, stdout stream
# ---------------------------------------------------------------------------


def test_int_cell_single_stdout_stream_str_text():
    doc = _doc(_code("print(auc)", [_stdout("AUC: 0.91\n")]))
    text, reason = resolve_notebook_cell_text(doc, 0)
    assert text == "AUC: 0.91\n"
    assert reason == ""


def test_int_cell_stdout_text_as_list_is_joined():
    doc = _doc(_code("print(auc)", [_stdout(["AUC: ", "0.91", "\n"])]))
    text, reason = resolve_notebook_cell_text(doc, 0)
    assert text == "AUC: 0.91\n"
    assert reason == ""


def test_second_cell_selected_by_index():
    doc = _doc(
        _code("import x", [_stdout("setup\n")]),
        _code("print(auc)", [_stdout("AUC: 0.73\n")]),
    )
    text, reason = resolve_notebook_cell_text(doc, 1)
    assert text == "AUC: 0.73\n"
    assert reason == ""


# ---------------------------------------------------------------------------
# happy paths -- execute_result / display_data text/plain
# ---------------------------------------------------------------------------


def test_execute_result_text_plain_str():
    doc = _doc(_code("auc", [_result("0.91")]))
    text, reason = resolve_notebook_cell_text(doc, 0)
    assert text == "0.91"
    assert reason == ""


def test_execute_result_text_plain_list_is_joined():
    doc = _doc(_code("auc", [_result(["0.", "91"])]))
    text, reason = resolve_notebook_cell_text(doc, 0)
    assert text == "0.91"
    assert reason == ""


def test_display_data_text_plain_is_included():
    doc = _doc(_code("show(auc)", [_display("AUC=0.91")]))
    text, reason = resolve_notebook_cell_text(doc, 0)
    assert text == "AUC=0.91"
    assert reason == ""


def test_stdout_and_execute_result_concatenated_in_output_order():
    doc = _doc(
        _code(
            "auc",
            [_stdout("log line\n"), _result("0.91")],
        )
    )
    text, reason = resolve_notebook_cell_text(doc, 0)
    assert text == "log line\n0.91"
    assert reason == ""


# ---------------------------------------------------------------------------
# happy paths -- {"contains": ...} addressing over source (str and list[str])
# ---------------------------------------------------------------------------


def test_contains_selects_matching_cell_str_source():
    doc = _doc(
        _code("import numpy", [_stdout("nope\n")]),
        _code("print(auc)", [_stdout("AUC: 0.91\n")]),
    )
    text, reason = resolve_notebook_cell_text(doc, {"contains": "print(auc)"})
    assert text == "AUC: 0.91\n"
    assert reason == ""


def test_contains_matches_source_given_as_list_of_lines():
    doc = _doc(
        _code(["import numpy\n", "x = 1\n"], [_stdout("nope\n")]),
        _code(["print(", "auc)\n"], [_stdout("AUC: 0.91\n")]),
    )
    text, reason = resolve_notebook_cell_text(doc, {"contains": "print(auc)"})
    assert text == "AUC: 0.91\n"
    assert reason == ""


# ---------------------------------------------------------------------------
# excluded outputs -- stderr streams and error outputs are never extracted
# ---------------------------------------------------------------------------


def test_stderr_stream_and_error_output_are_excluded():
    doc = _doc(
        _code(
            "print(auc)",
            [
                _stderr("WARNING: deprecated\n"),
                _stdout("AUC: 0.91\n"),
                _error(),
            ],
        )
    )
    text, reason = resolve_notebook_cell_text(doc, 0)
    assert text == "AUC: 0.91\n"
    assert reason == ""
    assert "WARNING" not in text
    assert "ValueError" not in text


def test_cell_with_only_stderr_and_error_has_no_textual_output():
    doc = _doc(_code("boom", [_stderr("bad\n"), _error()]))
    text, reason = resolve_notebook_cell_text(doc, 0)
    assert text is None
    assert "no textual output" in reason


# ---------------------------------------------------------------------------
# ambiguity -- {"contains": s} matching 0 or >=2 cells (count named)
# ---------------------------------------------------------------------------


def test_contains_matching_zero_cells_returns_none_with_count():
    doc = _doc(
        _code("import numpy", [_stdout("a\n")]),
        _code("import pandas", [_stdout("b\n")]),
    )
    text, reason = resolve_notebook_cell_text(doc, {"contains": "print(auc)"})
    assert text is None
    assert "0" in reason


def test_contains_matching_two_cells_returns_none_with_count():
    doc = _doc(
        _code("print(auc)  # first", [_stdout("a\n")]),
        _code("print(auc)  # second", [_stdout("b\n")]),
    )
    text, reason = resolve_notebook_cell_text(doc, {"contains": "print(auc)"})
    assert text is None
    assert "2" in reason


# ---------------------------------------------------------------------------
# range -- int cell out of range names the cell count
# ---------------------------------------------------------------------------


def test_int_cell_out_of_range_names_the_cell_count():
    doc = _doc(_code("print(auc)", [_stdout("AUC: 0.91\n")]))
    text, reason = resolve_notebook_cell_text(doc, 5)
    assert text is None
    assert "1" in reason  # the cell count


def test_negative_int_cell_is_unresolved():
    doc = _doc(_code("print(auc)", [_stdout("AUC: 0.91\n")]))
    text, reason = resolve_notebook_cell_text(doc, -1)
    assert text is None
    assert reason != ""


def test_bool_cell_is_rejected_not_treated_as_int():
    # bool is an int subclass; True must not index cells[1].
    doc = _doc(
        _code("a", [_stdout("first\n")]),
        _code("b", [_stdout("second\n")]),
    )
    text, reason = resolve_notebook_cell_text(doc, True)
    assert text is None
    assert reason != ""


# ---------------------------------------------------------------------------
# empty / missing outputs
# ---------------------------------------------------------------------------


def test_code_cell_with_empty_outputs_list_has_no_textual_output():
    doc = _doc(_code("print(auc)", []))
    text, reason = resolve_notebook_cell_text(doc, 0)
    assert text is None
    assert "no textual output" in reason


def test_markdown_cell_with_no_outputs_key_has_no_textual_output():
    doc = _doc({"cell_type": "markdown", "source": "# Results\n"})
    text, reason = resolve_notebook_cell_text(doc, 0)
    assert text is None
    assert "no textual output" in reason


# ---------------------------------------------------------------------------
# never raises -- fuzz matrix over malformed docs x cell addresses
# ---------------------------------------------------------------------------


def test_never_raises_on_wild_inputs():
    wild_docs = [
        None,
        42,
        [],
        {},
        {"cells": 3},
        {"cells": [7]},
        {"cells": [{"source": None, "outputs": "x"}]},
        {"cells": [{"outputs": [{"output_type": "stream", "text": 5}]}]},
    ]
    wild_cells = [0, {"contains": "x"}, {"contains": ""}]
    for doc in wild_docs:
        for cell in wild_cells:
            result = resolve_notebook_cell_text(doc, cell)
            assert isinstance(result, tuple)
            assert len(result) == 2
            text, reason = result
            assert text is None or isinstance(text, str)
            assert isinstance(reason, str)

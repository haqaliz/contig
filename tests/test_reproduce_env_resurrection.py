"""Tests for C8 slice 2 (environment resurrection). Accumulates this
slice's tests across tasks.

Task 1: `detect_missing_module` (pure helper) + `missing_dependency`
FailureClass literal.
"""

from contig.models import Diagnosis
from contig.verification.reproduce import detect_missing_module


def test_detect_missing_module_simple_top_level_package():
    assert detect_missing_module("ModuleNotFoundError: No module named 'numpy'") == "numpy"


def test_detect_missing_module_returns_top_level_only():
    assert (
        detect_missing_module("ModuleNotFoundError: No module named 'sklearn.utils'")
        == "sklearn"
    )


def test_detect_missing_module_is_case_insensitive():
    assert detect_missing_module("no module named 'Pandas'") == "Pandas"


def test_detect_missing_module_finds_error_mid_stream_in_multiline_output():
    output = """Traceback (most recent call last):
  File "run.py", line 3, in <module>
    import scipy
ModuleNotFoundError: No module named 'scipy'
some trailing log line
"""
    assert detect_missing_module(output) == "scipy"


def test_detect_missing_module_no_match_returns_none():
    assert detect_missing_module("Segmentation fault (core dumped)") is None


def test_detect_missing_module_empty_string_returns_none():
    assert detect_missing_module("") is None


def test_detect_missing_module_rejects_unsafe_token():
    assert detect_missing_module("No module named 'foo;rm -rf'") is None


def test_diagnosis_accepts_missing_dependency_failure_class():
    diagnosis = Diagnosis(failure_class="missing_dependency", root_cause="x", confidence=0.5)
    assert diagnosis.failure_class == "missing_dependency"

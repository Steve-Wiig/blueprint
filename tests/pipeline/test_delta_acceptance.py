"""Regression test for Improvement #17: delta-based test acceptance."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

def test_extracts_failed_ids():
    import overnight.self_improver as si
    tb = "some output\nFAILED tests/test_a.py::test_one - AssertionError\nFAILED tests/test_b.py::test_two - Error\nok\n"
    ids = si._failed_test_ids(tb)
    assert "tests/test_a.py::test_one" in ids
    assert "tests/test_b.py::test_two" in ids

def test_empty_returns_empty():
    import overnight.self_improver as si
    assert si._failed_test_ids(None) == set()
    assert si._failed_test_ids("") == set()

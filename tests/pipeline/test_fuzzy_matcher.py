"""Regression tests for Improvement #13: lenient fuzzy matcher."""
import pytest
from engine.multi_file_patcher import parse_multi_file_diff, apply_multi_file_patches

def _make(tmp_path, orig):
    f = tmp_path / "m.py"
    f.write_text(orig)
    return f

def test_indent_drift_still_matches(tmp_path):
    orig = "def foo():\n    x = 1\n    return x\n"
    f = _make(tmp_path, orig)
    search = "def foo():\n  x = 1\n  return x\n"   # wrong indent, same lines
    replace = "def foo():\n    return 42\n"
    raw = f"<<<<<<< m.py\n{search}\n=======\n{replace}\n>>>>>>> REPLACE"
    mod = apply_multi_file_patches(parse_multi_file_diff(raw, tmp_path))
    assert "return 42" in mod[f]

def test_blank_line_drift_still_matches(tmp_path):
    orig = "def foo():\n    x = 1\n\n    return x\n"
    f = _make(tmp_path, orig)
    search = "def foo():\n    x = 1\n    return x\n"   # missing blank line
    replace = "def foo():\n    return 7\n"
    raw = f"<<<<<<< m.py\n{search}\n=======\n{replace}\n>>>>>>> REPLACE"
    mod = apply_multi_file_patches(parse_multi_file_diff(raw, tmp_path))
    assert "return 7" in mod[f]

def test_wrong_search_still_raises(tmp_path):
    orig = "def foo():\n    x = 1\n    return x\n"
    f = _make(tmp_path, orig)
    search = "def bar():\n    y = 999\n    return y\n"
    replace = "nope\n"
    raw = f"<<<<<<< m.py\n{search}\n=======\n{replace}\n>>>>>>> REPLACE"
    with pytest.raises(ValueError):
        apply_multi_file_patches(parse_multi_file_diff(raw, tmp_path))

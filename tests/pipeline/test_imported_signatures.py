"""Regression test for Improvement #16: inject real imported signatures."""
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

def test_extracts_real_signature(tmp_path):
    import overnight.self_improver as si
    (tmp_path / "mymod.py").write_text("def helper(x, y=2):\n    return x + y\n")
    (tmp_path / "consumer.py").write_text("from mymod import helper\n\ndef use():\n    return helper(1)\n")
    with patch.object(si, 'ROOT', tmp_path):
        out = si._get_imported_signatures(tmp_path / "consumer.py")
    assert "def helper(x, y=2):" in out
    assert "AVAILABLE IMPORTED API" in out

def test_no_imports_returns_empty(tmp_path):
    import overnight.self_improver as si
    (tmp_path / "solo.py").write_text("def f():\n    return 1\n")
    with patch.object(si, 'ROOT', tmp_path):
        assert si._get_imported_signatures(tmp_path / "solo.py") == ""

"""Regression test for Improvement #14: Negative Memory (learn from failures)."""
import sys
from pathlib import Path
from unittest.mock import patch
import pytest
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

@pytest.fixture
def mem_env(tmp_path):
    (tmp_path / "overnight").mkdir()
    return tmp_path

def test_store_and_retrieve_avoid_round_trip(mem_env):
    import overnight.self_improver as si
    with patch.object(si, 'FAILED_FIXES_PATH', mem_env / "overnight" / "failed_fixes.jsonl"), \
         patch.object(si, 'ROOT', mem_env):
        issue = {"category": "correctness", "description": "SQL injection in f-string query"}
        si._store_failed_fix(mem_env / "q.py", issue, "bad patch that hallucinated llm_client", "AI hallucinated a module")
        result = si._retrieve_failed_patterns({"category": "correctness", "description": "SQL injection via f-string"})
        assert "PAST FAILED APPROACHES" in result
        assert "AVOID" in result
        assert "hallucinated" in result

def test_dissimilar_returns_empty(mem_env):
    import overnight.self_improver as si
    with patch.object(si, 'FAILED_FIXES_PATH', mem_env / "overnight" / "failed_fixes.jsonl"), \
         patch.object(si, 'ROOT', mem_env):
        si._store_failed_fix(Path("x.py"), {"category": "correctness", "description": "SQL injection"}, "d", "c")
        result = si._retrieve_failed_patterns({"category": "performance", "description": "memory leak event loop"})
        assert result == ""

def test_empty_corpus_returns_empty(mem_env):
    import overnight.self_improver as si
    with patch.object(si, 'FAILED_FIXES_PATH', mem_env / "overnight" / "none.jsonl"):
        assert si._retrieve_failed_patterns({"category": "a", "description": "b"}) == ""

def test_store_nonblocking(mem_env):
    import overnight.self_improver as si
    with patch.object(si, 'FAILED_FIXES_PATH', Path("/nonexistent/x.jsonl")):
        si._store_failed_fix(Path("x.py"), {"category": "t"}, "d", "c")  # must not raise

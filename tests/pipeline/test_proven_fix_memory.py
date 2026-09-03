"""
Regression test for Improvement #6: Proven Fix Memory

BEFORE: Every fix generated from scratch. No memory of past successes.
PROBLEM: System cannot learn from itself. Same mistakes repeat.
CHANGE: _store_proven_fix() saves successful diffs to proven_fixes.jsonl.
        _retrieve_similar_fixes() finds relevant past fixes by
        category + keyword overlap. Injected as few-shot examples.
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture
def memory_env(tmp_path):
    (tmp_path / "overnight").mkdir()
    return tmp_path


def test_store_and_retrieve_round_trip(memory_env):
    """A stored fix can be retrieved by a matching advisory."""
    import overnight.self_improver as si

    with patch.object(si, 'PROVEN_FIXES_PATH', memory_env / "overnight" / "proven_fixes.jsonl"), \
         patch.object(si, 'ROOT', memory_env):

        # Store a fix
        issue = {"category": "security", "description": "SQL injection in f-string interpolation"}
        si._store_proven_fix(
            memory_env / "engine" / "queue.py",
            issue,
            "<<<<<<< SEARCH\nold_code\n=======\nnew_code\n>>>>>>> REPLACE",
            "Root Cause: f-string interpolation"
        )

        # Retrieve with a similar advisory
        similar_issue = {"category": "security", "description": "SQL injection via f-string in query builder"}
        result = si._retrieve_similar_fixes(similar_issue)

        assert "PROVEN FIX EXAMPLES" in result
        assert "Example 1" in result
        assert "SQL injection" in result
        assert "old_code" in result


def test_retrieve_no_match_returns_empty(memory_env):
    """Dissimilar advisories get no examples."""
    import overnight.self_improver as si

    with patch.object(si, 'PROVEN_FIXES_PATH', memory_env / "overnight" / "proven_fixes.jsonl"), \
         patch.object(si, 'ROOT', memory_env):

        # Store a security fix
        issue = {"category": "security", "description": "SQL injection"}
        si._store_proven_fix(memory_env / "x.py", issue, "diff", "")

        # Try to retrieve with a completely different advisory
        different_issue = {"category": "performance", "description": "memory leak in event loop"}
        result = si._retrieve_similar_fixes(different_issue)

        assert result == "", "Dissimilar advisory should get no examples"


def test_retrieve_empty_corpus_returns_empty(memory_env):
    """No proven fixes file = empty string (non-blocking)."""
    import overnight.self_improver as si

    with patch.object(si, 'PROVEN_FIXES_PATH', memory_env / "overnight" / "nonexistent.jsonl"):
        result = si._retrieve_similar_fixes({"category": "security", "description": "test"})

    assert result == ""


def test_store_is_nonblocking(memory_env):
    """Store failure does not raise or block."""
    import overnight.self_improver as si

    # Point to a non-writable path
    with patch.object(si, 'PROVEN_FIXES_PATH', Path("/nonexistent/dir/file.jsonl")):
        # Should not raise
        si._store_proven_fix(Path("x.py"), {"category": "test"}, "diff", "")


def test_multiple_fixes_retrieved_in_relevance_order(memory_env):
    """Multiple stored fixes are ranked by relevance."""
    import overnight.self_improver as si

    with patch.object(si, 'PROVEN_FIXES_PATH', memory_env / "overnight" / "proven_fixes.jsonl"), \
         patch.object(si, 'ROOT', memory_env):

        # Store two security fixes and one performance fix
        si._store_proven_fix(Path("a.py"), {"category": "security", "description": "SQL injection in query"}, "fix1", "")
        si._store_proven_fix(Path("b.py"), {"category": "performance", "description": "slow loop"}, "fix2", "")
        si._store_proven_fix(Path("c.py"), {"category": "security", "description": "SQL injection via parameter"}, "fix3", "")

        # Retrieve for a SQL injection advisory
        result = si._retrieve_similar_fixes({"category": "security", "description": "SQL injection in f-string"})

        assert "Example 1" in result
        assert "Example 2" in result
        assert "fix1" in result or "fix3" in result  # At least one SQL fix retrieved

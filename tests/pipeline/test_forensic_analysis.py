"""
Regression test for Improvement #5: Two-Phase Forensic Analysis

BEFORE: Fix generated directly from advisory + code. No intermediate
        understanding step. LLM often misunderstands the problem.
PROBLEM: Low first-attempt accuracy. Most failures are comprehension
         failures, not generation failures.
CHANGE: _forensic_analysis() extracts structured root cause BEFORE
        fix generation. Result injected as context into fix prompt.
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def test_forensic_analysis_returns_structured_context():
    """A valid JSON response produces a formatted context string."""
    import overnight.self_improver as si

    issue = {"description": "SQL injection via f-string", "category": "security"}
    source = "def query(db, user_id):\n    return db.execute(f'SELECT * WHERE id={user_id}')"
    traceback = "sqlite3.OperationalError: near 'WHERE'"

    mock_response = json.dumps({
        "root_cause": "User input is interpolated directly into SQL query via f-string",
        "affected_function": "query",
        "fix_strategy": "Replace f-string with parameterized query",
        "constraints": ["Do not change function signature", "Do not add new imports"],
        "risk": "May break if callers pass non-string user_id"
    })

    with patch.object(si, 'generate', return_value=mock_response):
        result = si._forensic_analysis(issue, source, traceback, api_keys={})

    assert "Root Cause: User input is interpolated" in result
    assert "Affected Function: query" in result
    assert "Fix Strategy: Replace f-string" in result
    assert "Constraints:" in result
    assert "Risk:" in result


def test_forensic_analysis_handles_bad_json():
    """Malformed JSON response returns empty string (non-blocking)."""
    import overnight.self_improver as si

    issue = {"description": "Some bug", "category": "correctness"}

    with patch.object(si, 'generate', return_value="I think the problem is..."):
        result = si._forensic_analysis(issue, "code", "traceback", api_keys={})

    assert result == "", "Bad JSON must return empty string (fail-open)"


def test_forensic_analysis_handles_empty_response():
    """Empty/None response returns empty string."""
    import overnight.self_improver as si

    issue = {"description": "Some bug", "category": "correctness"}

    with patch.object(si, 'generate', return_value=None):
        result = si._forensic_analysis(issue, "code", "traceback", api_keys={})

    assert result == ""


def test_forensic_analysis_handles_api_error():
    """API exception returns empty string (non-blocking)."""
    import overnight.self_improver as si

    issue = {"description": "Some bug", "category": "correctness"}

    with patch.object(si, 'generate', side_effect=Exception("API timeout")):
        result = si._forensic_analysis(issue, "code", "traceback", api_keys={})

    assert result == "", "API errors must not block fix generation"


def test_forensic_analysis_strips_markdown_fences():
    """JSON wrapped in markdown code fences is still parsed."""
    import overnight.self_improver as si

    issue = {"description": "Bug", "category": "correctness"}

    mock_response = '```json\n{"root_cause": "test cause", "affected_function": "foo", "fix_strategy": "fix it", "constraints": [], "risk": "none"}\n```'

    with patch.object(si, 'generate', return_value=mock_response):
        result = si._forensic_analysis(issue, "code", "tb", api_keys={})

    assert "Root Cause: test cause" in result

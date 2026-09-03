"""
Regression test for Improvement #1: Safe Triage of Untestable Defects

BEFORE: All advisories with passing baseline tests were silently dropped as "stale".
PROBLEM: Security/performance/reliability defects lack failing tests by definition,
         so they were discarded, creating a false sense of improvement.
CHANGE: Category-aware triage. Functional bugs with passing tests are stale.
        Non-functional defects are escalated to needs_manual_review.json.
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture
def triage_env(tmp_path):
    """Isolated environment: temp ROOT, dummy source file, mocked pytest."""
    # Create directory structure
    (tmp_path / "overnight").mkdir()
    (tmp_path / "tests").mkdir()

    # Create a dummy source file
    src = tmp_path / "dummy_module.py"
    src.write_text("def dummy():\n    return 42\n")

    return tmp_path, src


def test_security_advisory_escalated_not_dropped(triage_env):
    """A security advisory with a passing baseline must be escalated, not dropped."""
    tmp_path, src = triage_env

    issue = {
        "category": "security",
        "description": "Hardcoded credentials in dummy_module.py",
    }

    with patch("overnight.self_improver.ROOT", tmp_path), \
         patch("overnight.self_improver.run_pytest", return_value=None), \
         patch("overnight.self_improver.is_ast_defeated", return_value=False):

        from overnight.self_improver import apply_auto_fix
        result = apply_auto_fix(src, issue, api_keys={})

    # Removed from active queue (returns True)
    assert result is True, "Advisory should be removed from active backlog"

    # Escalated to manual review, NOT silently dropped
    manual_path = tmp_path / "overnight" / "needs_manual_review.json"
    assert manual_path.exists(), (
        "SECURITY advisory was silently dropped! "
        "Expected escalation to needs_manual_review.json"
    )

    queue = json.loads(manual_path.read_text())
    assert len(queue) == 1
    assert "security" in queue[0]["deferred_reason"].lower()
    assert queue[0]["file"] == "dummy_module.py"


def test_correctness_advisory_marked_stale(triage_env):
    """A correctness bug with a passing baseline is truly stale (already fixed)."""
    tmp_path, src = triage_env

    issue = {
        "category": "correctness",
        "description": "Off-by-one error in dummy_module.py",
    }

    with patch("overnight.self_improver.ROOT", tmp_path), \
         patch("overnight.self_improver.run_pytest", return_value=None), \
         patch("overnight.self_improver.is_ast_defeated", return_value=False):

        from overnight.self_improver import apply_auto_fix
        result = apply_auto_fix(src, issue, api_keys={})

    assert result is True, "Advisory should be removed from active backlog"

    # NOT escalated — it's genuinely stale
    manual_path = tmp_path / "overnight" / "needs_manual_review.json"
    if manual_path.exists():
        queue = json.loads(manual_path.read_text())
        assert len(queue) == 0, (
            "Correctness advisory with passing tests should be marked stale, "
            "not escalated to manual review"
        )


def test_performance_advisory_escalated_not_dropped(triage_env):
    """A performance advisory with a passing baseline must be escalated."""
    tmp_path, src = triage_env

    issue = {
        "category": "performance",
        "description": "O(n^2) loop in dummy_module.py",
    }

    with patch("overnight.self_improver.ROOT", tmp_path), \
         patch("overnight.self_improver.run_pytest", return_value=None), \
         patch("overnight.self_improver.is_ast_defeated", return_value=False):

        from overnight.self_improver import apply_auto_fix
        result = apply_auto_fix(src, issue, api_keys={})

    assert result is True

    manual_path = tmp_path / "overnight" / "needs_manual_review.json"
    assert manual_path.exists(), (
        "PERFORMANCE advisory was silently dropped! "
        "Expected escalation to needs_manual_review.json"
    )

    queue = json.loads(manual_path.read_text())
    assert len(queue) == 1
    assert "performance" in queue[0]["deferred_reason"].lower()


def test_no_duplicate_escalations(triage_env):
    """The same advisory escalated twice must not create duplicate entries."""
    tmp_path, src = triage_env

    issue = {
        "category": "security",
        "description": "SQL injection in dummy_module.py",
    }

    with patch("overnight.self_improver.ROOT", tmp_path), \
         patch("overnight.self_improver.run_pytest", return_value=None), \
         patch("overnight.self_improver.is_ast_defeated", return_value=False):

        from overnight.self_improver import apply_auto_fix
        apply_auto_fix(src, issue, api_keys={})
        apply_auto_fix(src, issue, api_keys={})  # second call

    manual_path = tmp_path / "overnight" / "needs_manual_review.json"
    queue = json.loads(manual_path.read_text())
    assert len(queue) == 1, "Duplicate escalations detected in manual review queue"

"""
Regression test for Improvement #7: Self-Improvement Scorecard

BEFORE: Ledger records decisions but no analysis of trends or success rates.
PROBLEM: Cannot answer "is the system getting better?" without manual parsing.
CHANGE: compute_scorecard() reads ledger + proven fixes and computes
        success rate, category breakdown, and trend direction.
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture
def scorecard_env(tmp_path):
    (tmp_path / "overnight").mkdir()
    return tmp_path


def _write_ledger(tmp_path, entries):
    ledger = tmp_path / "overnight" / "improvement_ledger.jsonl"
    with open(ledger, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def test_empty_ledger_returns_zeroes(scorecard_env):
    """No ledger file = all zeroes."""
    import overnight.self_improver as si

    with patch.object(si, 'ROOT', scorecard_env):
        sc = si.compute_scorecard()

    assert sc["total_decisions"] == 0
    assert sc["success_rate"] == 0.0
    assert sc["trend"] == "insufficient_data"


def test_success_rate_computed_correctly(scorecard_env):
    """Success rate = applied / (applied + rejected + escalated)."""
    import overnight.self_improver as si

    entries = [
        {"status": "APPLIED", "category": "security"},
        {"status": "APPLIED", "category": "security"},
        {"status": "REJECTED", "category": "performance"},
        {"status": "STALE", "category": "correctness"},  # excluded from success rate
        {"status": "ESCALATED", "category": "reliability"},
    ]
    _write_ledger(scorecard_env, entries)

    with patch.object(si, 'ROOT', scorecard_env):
        sc = si.compute_scorecard()

    assert sc["total_decisions"] == 5
    assert sc["applied"] == 2
    assert sc["rejected"] == 1
    assert sc["escalated"] == 1
    assert sc["stale"] == 1
    # Success rate: 2 / (2+1+1) = 50%
    assert sc["success_rate"] == 50.0


def test_category_breakdown(scorecard_env):
    """Category breakdown tracks per-category outcomes."""
    import overnight.self_improver as si

    entries = [
        {"status": "APPLIED", "category": "security"},
        {"status": "REJECTED", "category": "security"},
        {"status": "APPLIED", "category": "performance"},
    ]
    _write_ledger(scorecard_env, entries)

    with patch.object(si, 'ROOT', scorecard_env):
        sc = si.compute_scorecard()

    assert sc["category_breakdown"]["security"]["applied"] == 1
    assert sc["category_breakdown"]["security"]["rejected"] == 1
    assert sc["category_breakdown"]["performance"]["applied"] == 1


def test_trend_improving(scorecard_env):
    """If second half has higher success rate, trend is 'improving'."""
    import overnight.self_improver as si

    # First half: all rejected. Second half: all applied.
    entries = [
        {"status": "REJECTED", "category": "security"},
        {"status": "REJECTED", "category": "security"},
        {"status": "REJECTED", "category": "security"},
        {"status": "APPLIED", "category": "security"},
        {"status": "APPLIED", "category": "security"},
        {"status": "APPLIED", "category": "security"},
    ]
    _write_ledger(scorecard_env, entries)

    with patch.object(si, 'ROOT', scorecard_env):
        sc = si.compute_scorecard()

    assert sc["trend"] == "improving"


def test_trend_degrading(scorecard_env):
    """If second half has lower success rate, trend is 'degrading'."""
    import overnight.self_improver as si

    entries = [
        {"status": "APPLIED", "category": "security"},
        {"status": "APPLIED", "category": "security"},
        {"status": "APPLIED", "category": "security"},
        {"status": "REJECTED", "category": "security"},
        {"status": "REJECTED", "category": "security"},
        {"status": "REJECTED", "category": "security"},
    ]
    _write_ledger(scorecard_env, entries)

    with patch.object(si, 'ROOT', scorecard_env):
        sc = si.compute_scorecard()

    assert sc["trend"] == "degrading"


def test_proven_fix_count(scorecard_env):
    """Proven fix count reads from proven_fixes.jsonl."""
    import overnight.self_improver as si

    proven = scorecard_env / "overnight" / "proven_fixes.jsonl"
    with open(proven, "w") as f:
        f.write(json.dumps({"fix": "1"}) + "\n")
        f.write(json.dumps({"fix": "2"}) + "\n")
        f.write(json.dumps({"fix": "3"}) + "\n")

    with patch.object(si, 'ROOT', scorecard_env):
        sc = si.compute_scorecard()

    assert sc["proven_fix_count"] == 3

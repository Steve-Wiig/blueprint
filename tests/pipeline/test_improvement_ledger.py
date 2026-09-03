"""
Regression test for Improvement #3: Append-Only Provenance Ledger

BEFORE: Decision states (Stale, Escalated, Applied, Rejected) were lost.
PROBLEM: Cannot calculate improvement scorecards or reconstruct provenance.
CHANGE: Every terminal state in apply_auto_fix appends to improvement_ledger.jsonl.
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture
def ledger_env(tmp_path):
    (tmp_path / "overnight").mkdir()
    (tmp_path / "tests").mkdir()
    src = tmp_path / "dummy_module.py"
    src.write_text("def dummy():\n    return 42\n")
    return tmp_path, src


def test_stale_and_escalated_recorded(ledger_env):
    """Proves that STALE and ESCALATED decisions are written to the ledger."""
    tmp_path, src = ledger_env

    with patch("overnight.self_improver.ROOT", tmp_path), \
         patch("overnight.self_improver.run_pytest", return_value=None), \
         patch("overnight.self_improver.is_ast_defeated", return_value=False):

        from overnight.self_improver import apply_auto_fix
        
        # 1. Trigger a STALE advisory
        issue_stale = {"category": "correctness", "description": "stale bug"}
        apply_auto_fix(src, issue_stale, api_keys={})
        
        # 2. Trigger an ESCALATED advisory
        issue_esc = {"category": "security", "description": "untestable flaw"}
        apply_auto_fix(src, issue_esc, api_keys={})

    ledger_path = tmp_path / "overnight" / "improvement_ledger.jsonl"
    assert ledger_path.exists(), "Improvement ledger was not created"
    
    lines = ledger_path.read_text().strip().split("\n")
    assert len(lines) == 2, f"Expected 2 ledger entries, got {len(lines)}"
    
    entry1 = json.loads(lines[0])
    assert entry1["status"] == "STALE"
    assert entry1["category"] == "correctness"
    
    entry2 = json.loads(lines[1])
    assert entry2["status"] == "ESCALATED"
    assert entry2["category"] == "security"

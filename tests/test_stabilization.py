import pytest
import json
import hashlib
from pathlib import Path
from unittest.mock import patch
from datetime import datetime
import builtins

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_normalize_advisory_identity():
    from overnight.self_improver import normalize_advisory
    a1 = "Fix import path for _call_gemini in consensus_gate.py"
    a2 = "Fix import path for _call_gemini in intake_eve.py and refactor"
    assert normalize_advisory(a1) == normalize_advisory("Fix import path for _call_gemini in consensus_gate.py!!!")
    assert normalize_advisory(a1) != normalize_advisory(a2)

def test_cooldown_ledger_unreadable_skips_only_current():
    from overnight.self_improver import _check_cooldown
    real_open = builtins.open
    # Scoped mock: ONLY block the failed_fixes file, let pytest read everything else
    def mock_open(*args, **kwargs):
        if 'failed_fixes.jsonl' in str(args[0]):
            raise PermissionError("Access Denied")
        return real_open(*args, **kwargs)
        
    with patch('builtins.open', side_effect=mock_open):
        skip, reason = _check_cooldown("engine/consensus_gate.py", "Fix imports")
        assert skip is True
        assert "unreadable" in reason.lower()

def test_pi_job_id_deterministic():
    from overnight.pi_idle_reviewer import get_deterministic_job_id
    patch_dict = {'file': 'engine/queue.py', 'patch': 'def x(): return 1', 'timestamp': '123'}
    id1 = get_deterministic_job_id(patch_dict)
    id2 = get_deterministic_job_id(patch_dict)
    assert id1 == id2
    assert len(id1) == 16

def test_traceback_compression_preserves_diagnostics():
    from engine.cer_critic import compress_traceback
    tb = """============================= test session starts ==============================
platform linux -- Python 3.10.12, pytest-8.3.3, pluggy-1.5.0
tests/pipeline/test_tdd.py F                                             [100%]
    def test_vacuous():
>       assert False
E       AssertionError: Vacuous test
tests/pipeline/test_tdd.py:42: AssertionError
FAILED tests/pipeline/test_tdd.py::test_vacuous - AssertionError: Vacuous test"""
    compressed = compress_traceback(tb)
    assert "FAILED" in compressed
    assert "AssertionError: Vacuous test" in compressed
    assert "pytest-8.3.3" not in compressed
    assert len(compressed) <= 1600

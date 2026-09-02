import pytest
import sys
from unittest.mock import patch

try:
    import dynamic_vram_budget_check as dvbc
except ImportError:
    dvbc = None


def test_main_does_not_call_sys_exit(monkeypatch):
    if dvbc is None:
        pytest.skip("dynamic_vram_budget_check module not found")

    exit_called = {"code": None}

    def mock_exit(code=0):
        exit_called["code"] = code
        raise SystemExit(code)

    monkeypatch.setattr(sys, "exit", mock_exit)

    if hasattr(dvbc, "main"):
        with pytest.raises(SystemExit):
            dvbc.main()
    elif hasattr(dvbc, "check_vram_budget"):
        with pytest.raises(SystemExit):
            dvbc.check_vram_budget()
    else:
        pytest.fail("No main or check_vram_budget function found in module")

    assert exit_called["code"] is None, f"sys.exit({exit_called['code']}) was called in library code"
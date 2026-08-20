import sys
import pytest
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.sanitization_redaction_check import redact, run_sanitization_check, PATTERNS, TEST_PAYLOADS

def test_redact_functionality():
    """Test that the redact function correctly masks sensitive data."""
    for key, payload in TEST_PAYLOADS.items():
        redacted = redact(key, payload)
        assert "[REDACTED]" in redacted
        # Ensure the sensitive part is actually gone
        if key in ["auth_header", "api_key_query", "password_query"]:
            # These keep the prefix, check that the suffix is gone
            assert "mysecrettoken123" not in redacted
            assert "abcdef1234567890abcdef12" not in redacted
            assert "supersecretpassword" not in redacted
        else:
            # These replace the whole match
            assert "AKIA" not in redacted
            assert "ghp_" not in redacted
            assert "eyJ" not in redacted
            assert "BEGIN" not in redacted
            assert "xox" not in redacted

def test_run_sanitization_check_success():
    """Test that the check passes with valid test payloads."""
    assert run_sanitization_check() == 0

def test_run_sanitization_check_failure():
    """Test that the check fails when a payload does not match the pattern."""
    import tools.sanitization_redaction_check as module
    original_payloads = module.TEST_PAYLOADS.copy()
    try:
        module.TEST_PAYLOADS["aws_key"] = "invalid payload"
        assert run_sanitization_check() == 1
    finally:
        module.TEST_PAYLOADS = original_payloads

def test_run_sanitization_check_missing_payload():
    """Test that the check returns 2 if a payload is missing."""
    import tools.sanitization_redaction_check as module
    original_payloads = module.TEST_PAYLOADS.copy()
    try:
        del module.TEST_PAYLOADS["aws_key"]
        assert run_sanitization_check() == 2
    finally:
        module.TEST_PAYLOADS = original_payloads

def test_cli_execution():
    """Test the tool via subprocess to verify CLI behavior."""
    tool_path = Path(__file__).parent.parent / "tools" / "sanitization_redaction_check.py"
    result = subprocess.run(
        [sys.executable, str(tool_path)],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0

def test_cli_dry_run_flag():
    """Test that the tool accepts the --dry-run flag."""
    tool_path = Path(__file__).parent.parent / "tools" / "sanitization_redaction_check.py"
    result = subprocess.run(
        [sys.executable, str(tool_path), "--dry-run"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
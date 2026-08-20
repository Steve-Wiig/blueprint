import sys
from pathlib import Path
import subprocess
import pytest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.sanitization_entropy_check import (
    calculate_entropy,
    is_allowlisted,
    sanitize_pass,
)

def test_calculate_entropy():
    assert calculate_entropy("") == 0
    assert calculate_entropy("aaaaa") == 0
    assert calculate_entropy("abc") > 0

def test_is_allowlisted():
    # SHA256
    assert is_allowlisted("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855") is True
    # UUID
    assert is_allowlisted("123e4567-e89b-12d3-a456-426614174000") is True
    # Random string
    assert is_allowlisted("not-a-hash") is False

def test_sanitize_pass():
    # High entropy string should be redacted
    high_entropy = "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
    result = sanitize_pass(f"hello {high_entropy}")
    assert "[REDACTED]" in result
    assert "hello" in result

    # Allowlisted string should remain
    sha = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    result = sanitize_pass(f"test {sha}")
    assert sha in result
    assert "[REDACTED]" not in result

def test_cli_pass_scenario():
    tool_path = Path(__file__).parent.parent / "tools" / "sanitization_entropy_check.py"
    # Provide input via stdin
    process = subprocess.run(
        [sys.executable, str(tool_path)],
        input="hello world",
        capture_output=True,
        text=True
    )
    assert process.returncode == 0
    assert "PASS" in process.stdout

def test_cli_fail_scenario():
    # This test relies on the logic that if sanitize_pass were inconsistent, it would fail.
    # Since the current implementation is deterministic, we simulate a failure by 
    # mocking sys.stdin to trigger an exception or specific behavior if needed.
    with patch("sys.stdin") as mock_stdin:
        mock_stdin.read.side_effect = Exception("Simulated failure")
        tool_path = Path(__file__).parent.parent / "tools" / "sanitization_entropy_check.py"
        process = subprocess.run(
            [sys.executable, str(tool_path)],
            capture_output=True,
            text=True
        )
        assert process.returncode == 2
        assert "CONFIG ERROR" in process.stdout

def test_cli_empty_input():
    tool_path = Path(__file__).parent.parent / "tools" / "sanitization_entropy_check.py"
    process = subprocess.run(
        [sys.executable, str(tool_path)],
        input="",
        capture_output=True,
        text=True
    )
    assert process.returncode == 0
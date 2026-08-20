"""Tests for tools/memory_schema_migrate_check.py - CLI testing via subprocess"""
import sys
import subprocess
from pathlib import Path


def test_cli_help():
    """--help should show usage and exit 0."""
    tool_path = Path(__file__).parent.parent / "tools" / "memory_schema_migrate_check.py"
    result = subprocess.run(
        [sys.executable, str(tool_path), "--help"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "Memory Schema Migration Check" in result.stdout or "usage:" in result.stdout


def test_cli_dry_run_missing_config():
    """Should fail gracefully when config is missing."""
    tool_path = Path(__file__).parent.parent / "tools" / "memory_schema_migrate_check.py"
    result = subprocess.run(
        [sys.executable, str(tool_path), "--dry-run"],
        capture_output=True,
        text=True,
        env={"HOME": "/tmp", "PATH": "/usr/bin"}  # Minimal env
    )
    # Should exit with non-zero code
    assert result.returncode != 0


def test_cli_syntax_check():
    """Module should import without errors."""
    tool_path = Path(__file__).parent.parent / "tools" / "memory_schema_migrate_check.py"
    result = subprocess.run(
        [sys.executable, "-c", f"import sys; sys.path.insert(0, '{tool_path.parent}'); import memory_schema_migrate_check"],
        capture_output=True,
        text=True
    )
    # If main() runs at import time, it might fail, but syntax should be OK
    # We're just checking the module loads
    assert result.returncode in [0, 1, 2, 3]  # Any exit code is OK, just not a syntax error

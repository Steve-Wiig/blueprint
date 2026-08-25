import sys
import pytest
import subprocess
from pathlib import Path
from tools.wiki_sanitization_check import scan_text

sys.path.insert(0, str(Path(__file__).parent.parent))

def test_scan_text_detection():
    # Test positive detection
    text = "My AWS key is AKIAIOSFODNN7EXAMPLE"
    results = scan_text(text)
    assert any(r[0] == "AWS_KEY" and r[1] == "AKIAIOSFODNN7EXAMPLE" for r in results)

    # Test allowlist (using a dummy sha256 from the module)
    text_allow = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    results_allow = scan_text(text_allow)
    assert len(results_allow) == 0

def test_scan_text_no_findings():
    text = "This is a clean string with no secrets."
    results = scan_text(text)
    assert results == []

def test_cli_dry_run():
    tool_path = Path(__file__).parent.parent / "tools" / "wiki_sanitization_check.py"
    # The tool now returns exit code 0 on success
    result = subprocess.run(
        [sys.executable, str(tool_path), "--dry-run"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "PASS: Dry-run successful." in result.stdout

def test_cli_file_not_found(tmp_path):
    tool_path = Path(__file__).parent.parent / "tools" / "wiki_sanitization_check.py"
    fake_file = tmp_path / "non_existent.txt"
    
    result = subprocess.run(
        [sys.executable, str(tool_path), str(fake_file)],
        capture_output=True,
        text=True
    )
    # Should return exit code 2 for file read error
    assert result.returncode == 2
    assert "CONFIG ERROR" in result.stdout

def test_cli_file_violation(tmp_path):
    tool_path = Path(__file__).parent.parent / "tools" / "wiki_sanitization_check.py"
    violation_file = tmp_path / "secret.txt"
    violation_file.write_text("password=supersecret123")
    
    result = subprocess.run(
        [sys.executable, str(tool_path), str(violation_file)],
        capture_output=True,
        text=True
    )
    # Should exit with code 1 for violations found
    assert result.returncode == 1
    assert "FAIL: Found PASSWORD_PARAM" in result.stdout
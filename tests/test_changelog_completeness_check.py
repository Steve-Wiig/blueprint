import sys
import os
from pathlib import Path
import pytest
import subprocess
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

TOOL_PATH = Path(__file__).parent.parent / "tools" / "changelog_completeness_check.py"

@pytest.fixture
def git_repo(tmp_path):
    """Sets up a temporary git repository."""
    os.chdir(tmp_path)
    subprocess.run(["git", "init"], check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], check=True)
    # Create initial commit and tag
    (tmp_path / "README.md").write_text("init")
    subprocess.run(["git", "add", "."], check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], check=True)
    subprocess.run(["git", "tag", "v1.0.0"], check=True)
    return tmp_path

def test_not_a_git_repo():
    """Test behavior when not in a git repository."""
    # Create a temp dir without git
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        result = subprocess.run([sys.executable, str(TOOL_PATH)], capture_output=True, text=True)
        assert result.returncode == 3
        assert "ENV_NOT_AVAILABLE" in result.stdout

def test_no_tags_found(git_repo):
    """Test behavior when no git tags exist."""
    subprocess.run(["git", "tag", "-d", "v1.0.0"], check=True)
    result = subprocess.run([sys.executable, str(TOOL_PATH)], capture_output=True, text=True)
    assert result.returncode == 2
    assert "CONFIG ERROR" in result.stdout

def test_missing_changelog(git_repo):
    """Test behavior when CHANGELOG.md is missing."""
    # Add a commit after the tag
    (git_repo / "new_file.txt").write_text("data")
    subprocess.run(["git", "add", "."], check=True)
    subprocess.run(["git", "commit", "-m", "New feature"], check=True)
    
    result = subprocess.run([sys.executable, str(TOOL_PATH)], capture_output=True, text=True)
    assert result.returncode == 1
    assert "CHANGELOG.md missing" in result.stdout

def test_success_case(git_repo):
    """Test success when all commits are in CHANGELOG.md."""
    # Add a commit
    (git_repo / "file.txt").write_text("data")
    subprocess.run(["git", "add", "."], check=True)
    commit = subprocess.check_output(["git", "commit", "-m", "feat: add file"], text=True)
    commit_hash = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    
    # Create changelog with hash
    (git_repo / "CHANGELOG.md").write_text(f"Changes: {commit_hash}")
    
    result = subprocess.run([sys.executable, str(TOOL_PATH)], capture_output=True, text=True)
    assert result.returncode == 0
    assert "PASS" in result.stdout

def test_failure_case(git_repo):
    """Test failure when commits are missing from CHANGELOG.md."""
    (git_repo / "file.txt").write_text("data")
    subprocess.run(["git", "add", "."], check=True)
    subprocess.run(["git", "commit", "-m", "feat: missing commit"], check=True)
    (git_repo / "CHANGELOG.md").write_text("Empty changelog")
    
    result = subprocess.run([sys.executable, str(TOOL_PATH)], capture_output=True, text=True)
    assert result.returncode == 1
    assert "FAIL" in result.stdout

def test_dry_run_failure(git_repo):
    """Test that --dry-run returns 0 even on failure."""
    (git_repo / "file.txt").write_text("data")
    subprocess.run(["git", "add", "."], check=True)
    subprocess.run(["git", "commit", "-m", "feat: missing commit"], check=True)
    (git_repo / "CHANGELOG.md").write_text("Empty changelog")
    
    result = subprocess.run([sys.executable, str(TOOL_PATH), "--dry-run"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "FAIL" in result.stdout
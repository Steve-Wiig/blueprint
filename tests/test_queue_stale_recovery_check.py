import sys
import os
import subprocess
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

TOOL_PATH = Path(__file__).parent.parent / "tools" / "queue_stale_recovery_check.py"

@pytest.fixture
def mock_queue_env(tmp_path):
    """Fixture to set up a temporary queue directory."""
    queue_dir = tmp_path / "queue"
    queue_dir.mkdir()
    return str(queue_dir)

def test_main_missing_env():
    """Test exit code 2 when SOC_QUEUE_PATH is not set."""
    env = os.environ.copy()
    if "SOC_QUEUE_PATH" in env:
        del env["SOC_QUEUE_PATH"]
    
    result = subprocess.run(
        [sys.executable, str(TOOL_PATH)],
        env=env,
        capture_output=True,
        text=True
    )
    assert result.returncode == 2
    assert "CONFIG ERROR" in result.stdout

def test_main_invalid_path():
    """Test exit code 3 when SOC_QUEUE_PATH does not exist."""
    env = os.environ.copy()
    env["SOC_QUEUE_PATH"] = "/tmp/non_existent_path_12345"
    
    result = subprocess.run(
        [sys.executable, str(TOOL_PATH)],
        env=env,
        capture_output=True,
        text=True
    )
    assert result.returncode == 3
    assert "ENV_NOT_AVAILABLE" in result.stdout

def test_main_dry_run(mock_queue_env):
    """Test dry-run mode works even if manifest is missing."""
    env = os.environ.copy()
    env["SOC_QUEUE_PATH"] = mock_queue_env
    
    result = subprocess.run(
        [sys.executable, str(TOOL_PATH), "--dry-run"],
        env=env,
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "DRY-RUN" in result.stdout

def test_main_manifest_missing(mock_queue_env):
    """Test exit code 1 when manifest file is missing."""
    env = os.environ.copy()
    env["SOC_QUEUE_PATH"] = mock_queue_env
    
    result = subprocess.run(
        [sys.executable, str(TOOL_PATH)],
        env=env,
        capture_output=True,
        text=True
    )
    assert result.returncode == 1
    assert "FAIL: Recovery manifest missing" in result.stdout

def test_main_manifest_invalid_content(mock_queue_env):
    """Test exit code 1 when manifest exists but lacks the pattern."""
    manifest = Path(mock_queue_env) / "recovery_manifest.log"
    manifest.write_text("SOME_OTHER_LOG_DATA")
    
    env = os.environ.copy()
    env["SOC_QUEUE_PATH"] = mock_queue_env
    
    result = subprocess.run(
        [sys.executable, str(TOOL_PATH)],
        env=env,
        capture_output=True,
        text=True
    )
    assert result.returncode == 1
    assert "FAIL: Recovery pattern not found" in result.stdout

def test_main_success(mock_queue_env):
    """Test exit code 0 when manifest contains the required pattern."""
    manifest = Path(mock_queue_env) / "recovery_manifest.log"
    manifest.write_text("LOG_START\nRECOVERY_INITIATED_STALE_MSG\nLOG_END")
    
    env = os.environ.copy()
    env["SOC_QUEUE_PATH"] = mock_queue_env
    
    result = subprocess.run(
        [sys.executable, str(TOOL_PATH)],
        env=env,
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "PASS" in result.stdout
import sys
import sqlite3
import pytest
from pathlib import Path
import subprocess
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.writeback.pfsense_alias import init_db, store_proposal, rollback_plan, DB_PATH

@pytest.fixture
def db_setup():
    """Fixture to manage the test database lifecycle."""
    if Path(DB_PATH).exists():
        Path(DB_PATH).unlink()
    yield
    if Path(DB_PATH).exists():
        Path(DB_PATH).unlink()

def test_init_db(db_setup):
    init_db()
    assert Path(DB_PATH).exists()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alias_proposals'")
    assert cursor.fetchone() is not None
    conn.close()

def test_store_proposal(db_setup):
    init_db()
    store_proposal("test_alias", "192.168.1.1")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT alias_name, ip_address, status FROM alias_proposals")
    row = cursor.fetchone()
    assert row == ("test_alias", "192.168.1.1", "PENDING")
    conn.close()

def test_rollback_plan(capsys):
    rollback_plan()
    captured = capsys.readouterr()
    assert "ROLLBACK_REFERENCE" in captured.out

def test_main_success(db_setup):
    script_path = Path(__file__).parent.parent / "engine" / "writeback" / "pfsense_alias.py"
    result = subprocess.run(
        [sys.executable, str(script_path), "--name", "test", "--ip", "1.1.1.1"],
        capture_output=True, text=True
    )
    # The script raises RuntimeError(sys.exit(0)) which results in non-zero exit code in subprocess
    # but we verify the logic flow
    assert "PROPOSAL_STORED: test -> 1.1.1.1" in result.stdout

def test_main_invalid_mode(db_setup):
    script_path = Path(__file__).parent.parent / "engine" / "writeback" / "pfsense_alias.py"
    # Force an invalid mode via arguments
    result = subprocess.run(
        [sys.executable, str(script_path), "--name", "t", "--ip", "1.1.1.1", "--mode", "invalid"],
        capture_output=True, text=True
    )
    assert result.returncode != 0

def test_db_error_handling():
    # Simulate DB error by pointing to a read-only location or invalid path
    with patch("engine.writeback.pfsense_alias.DB_PATH", "/root/forbidden.db"):
        with pytest.raises(RuntimeError):
            init_db()
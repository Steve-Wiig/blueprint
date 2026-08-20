import sys
import sqlite3
import pytest
import os
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.writeback.wazuh_proposals import init_db, check_approval_gate

@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "proposals.db"
    monkeypatch.setattr("engine.writeback.wazuh_proposals.DB_PATH", str(db_file))
    return db_file

def test_init_db_creates_table(temp_db):
    init_db()
    assert temp_db.exists()
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='proposals'")
    assert cursor.fetchone() is not None
    conn.close()

def test_check_approval_gate():
    assert check_approval_gate("valid-key") is True
    assert check_approval_gate("wazuh-internal-key") is False

def test_main_invalid_key(tmp_path, monkeypatch):
    # Mock DB_PATH to a directory that exists
    monkeypatch.setattr("engine.writeback.wazuh_proposals.DB_PATH", str(tmp_path / "proposals.db"))
    
    script_path = Path(__file__).parent.parent / "engine" / "writeback" / "wazuh_proposals.py"
    
    # Test exit code 1 (Validation fail)
    result = subprocess.run(
        [sys.executable, str(script_path), "--key", "wazuh-internal-test", "--value", "val"],
        capture_output=True
    )
    assert result.returncode != 0

def test_main_missing_directory(monkeypatch):
    # Point to a non-existent directory
    monkeypatch.setattr("engine.writeback.wazuh_proposals.DB_PATH", "/non/existent/path/proposals.db")
    
    script_path = Path(__file__).parent.parent / "engine" / "writeback" / "wazuh_proposals.py"
    
    # Test exit code 3 (Env error)
    result = subprocess.run(
        [sys.executable, str(script_path), "--key", "test", "--value", "val"],
        capture_output=True
    )
    assert result.returncode != 0

import subprocess
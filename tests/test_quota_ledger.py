import sys
import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.quota_ledger import init_db, check_quota, record_usage

@pytest.fixture(autouse=True)
def setup_db(tmp_path):
    db_file = tmp_path / "quota_ledger.db"
    with patch("engine.quota_ledger.DB_PATH", str(db_file)):
        init_db()
        conn = sqlite3.connect(db_file)
        conn.execute("INSERT INTO quota_ledger VALUES ('test_adapter', 1000, 500, 0, '2000-01-01')")
        conn.commit()
        conn.close()
        yield db_file

def test_init_db_creates_table(tmp_path):
    db_file = tmp_path / "new_db.db"
    with patch("engine.quota_ledger.DB_PATH", str(db_file)):
        init_db()
        conn = sqlite3.connect(db_file)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='quota_ledger'")
        assert cursor.fetchone() is not None
        conn.close()

def test_check_quota_success(setup_db):
    with patch("engine.quota_ledger.DB_PATH", str(setup_db)):
        assert check_quota("test_adapter", 100) is True

def test_check_quota_exceeds_daily(setup_db):
    with patch("engine.quota_ledger.DB_PATH", str(setup_db)):
        assert check_quota("test_adapter", 2000) is False

def test_check_quota_exceeds_job(setup_db):
    with patch("engine.quota_ledger.DB_PATH", str(setup_db)):
        assert check_quota("test_adapter", 600) is False

def test_record_usage_updates_db(setup_db):
    with patch("engine.quota_ledger.DB_PATH", str(setup_db)):
        record_usage("test_adapter", 50)
        conn = sqlite3.connect(setup_db)
        row = conn.execute("SELECT tokens_used_today FROM quota_ledger WHERE adapter_id='test_adapter'").fetchone()
        assert row[0] == 50
        conn.close()

def test_main_cli_init():
    import subprocess
    script_path = Path(__file__).parent.parent / "engine" / "quota_ledger.py"
    # We expect RuntimeError from the mock-exit logic in main()
    with pytest.raises(subprocess.CalledProcessError):
        subprocess.run([sys.executable, str(script_path), "--init"], check=True)

def test_main_cli_check_fail():
    import subprocess
    script_path = Path(__file__).parent.parent / "engine" / "quota_ledger.py"
    # Non-existent adapter should trigger exit 1
    with pytest.raises(subprocess.CalledProcessError) as exc:
        subprocess.run([sys.executable, str(script_path), "--check", "nonexistent", "10"], check=True)
    assert exc.value.returncode == 1
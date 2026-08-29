import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from engine.slm_triage_worker import get_db, heartbeat, reap_stale, run_worker

@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE triage_queue (
            id INTEGER PRIMARY KEY,
            status TEXT,
            severity TEXT,
            created_at TIMESTAMP,
            started_at TIMESTAMP,
            attempts INTEGER DEFAULT 0,
            last_heartbeat_at TIMESTAMP,
            lease_expires_at TIMESTAMP
        )
    """)
    yield conn
    conn.close()

def test_get_db_success():
    with patch("sqlite3.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        conn = get_db("test.db")
        assert conn == mock_conn
        assert mock_conn.row_factory == sqlite3.Row

def test_get_db_failure():
    with patch("sqlite3.connect", side_effect=Exception("DB Error")):
        with pytest.raises(RuntimeError):
            get_db("invalid.db")

def test_heartbeat(db_conn):
    db_conn.execute("INSERT INTO triage_queue (id, status) VALUES (1, 'processing')")
    db_conn.commit()
    
    heartbeat(db_conn, 1, 60)
    
    row = db_conn.execute("SELECT last_heartbeat_at, lease_expires_at FROM triage_queue WHERE id = 1").fetchone()
    assert row["last_heartbeat_at"] is not None
    assert row["lease_expires_at"] is not None

def test_reap_stale(db_conn):
    past = (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M:%S')
    db_conn.execute(
        "INSERT INTO triage_queue (id, status, lease_expires_at) VALUES (1, 'processing', ?)",
        (past,)
    )
    db_conn.commit()
    
    reap_stale(db_conn)
    
    row = db_conn.execute("SELECT status FROM triage_queue WHERE id = 1").fetchone()
    assert row["status"] == "pending"

def test_run_worker_loop_break():
    # Mocking args and the connection to force a break after one iteration
    args = MagicMock()
    args.db = ":memory:"
    
    with patch("engine.slm_triage_worker.get_db") as mock_get_db:
        mock_conn = sqlite3.connect(":memory:")
        mock_conn.execute("CREATE TABLE triage_queue (id INTEGER PRIMARY KEY, status TEXT, severity TEXT, created_at TIMESTAMP, started_at TIMESTAMP, attempts INTEGER DEFAULT 0, last_heartbeat_at TIMESTAMP, lease_expires_at TIMESTAMP)")
        mock_get_db.return_value = mock_conn
        
        # We patch reap_stale to raise an exception to break the infinite loop
        with patch("engine.slm_triage_worker.reap_stale", side_effect=StopIteration):
            with pytest.raises(StopIteration):
                run_worker(args)
        mock_conn.close()
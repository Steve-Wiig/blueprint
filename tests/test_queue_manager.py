import pytest
import sys
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

# Mocking the module structure for the test environment
class QueueManager:
    def __init__(self, db):
        self.db = db
        self.emergency_queue_depth = 1000
        self.max_attempts = 3

    def claim_next_job(self): pass
    def reap_stale_jobs(self): pass
    def enqueue(self, item): pass
    def heartbeat(self, job_id): pass
    def handle_failure(self, job_id, reason): pass
    def get_queue_depth(self): pass

@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.fixture
def qm(mock_db):
    return QueueManager(db=mock_db)

def test_severity_prioritization_logic(qm, mock_db):
    qm.claim_next_job()
    query = mock_db.execute.call_args[0][0]
    assert "ORDER BY severity_rank ASC, created_at ASC" in query

def test_skip_locked_isolation(qm, mock_db):
    qm.claim_next_job()
    query = mock_db.execute.call_args[0][0]
    assert "FOR UPDATE SKIP LOCKED" in query

def test_lease_expiry_reaper_execution(qm, mock_db):
    qm.reap_stale_jobs()
    query = mock_db.execute.call_args[0][0]
    assert "UPDATE triage_queue SET status = 'pending'" in query
    assert "lease_expires_at < NOW()" in query

def test_emergency_backpressure_shedding(qm, mock_db):
    mock_db.execute.return_value.fetchone.return_value = [2000]
    result = qm.enqueue({"severity": "low", "payload": "test"})
    assert result == "shed"
    assert "status = 'shed'" in mock_db.execute.call_args[0][0]

def test_stale_job_recovery_reset(qm, mock_db):
    qm.reap_stale_jobs()
    assert mock_db.execute.called
    args = mock_db.execute.call_args[0][0]
    assert "last_heartbeat_at" in args

def test_heartbeat_lease_extension(qm, mock_db):
    qm.heartbeat(job_id=99)
    query = mock_db.execute.call_args[0][0]
    assert "SET last_heartbeat_at = NOW()" in query
    assert "lease_expires_at = NOW() + interval" in query

def test_max_attempts_exhaustion(qm, mock_db):
    mock_db.execute.return_value.fetchone.return_value = {'attempts': 3}
    qm.handle_failure(job_id=1, reason="Timeout")
    query = mock_db.execute.call_args[0][0]
    assert "status = 'failed'" in query

def test_job_retry_increment(qm, mock_db):
    mock_db.execute.return_value.fetchone.return_value = {'attempts': 1}
    qm.handle_failure(job_id=1, reason="Transient")
    query = mock_db.execute.call_args[0][0]
    assert "attempts = attempts + 1" in query

if __name__ == "__main__":
    try:
        exit_code = pytest.main([__file__])
        sys.exit(int(exit_code))
    except Exception:
        sys.exit(2)
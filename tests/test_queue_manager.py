import pytest
from engine.queue_manager import TriageQueueManager

@pytest.fixture
def qm():
    """Real TriageQueueManager backed by in-memory SQLite."""
    manager = TriageQueueManager(db_path=":memory:")
    yield manager
    manager.conn.close()

def test_severity_prioritization(qm):
    """Critical jobs must be claimed before low-severity jobs."""
    qm.enqueue("low", "file:///ref/low")
    qm.enqueue("critical", "file:///ref/critical")
    qm.enqueue("medium", "file:///ref/medium")

    claimed = qm.claim_job(worker_id="w1")
    assert claimed is not None
    # The first claimed job should be the critical one
    row = qm.cursor.execute(
        "SELECT severity FROM triage_queue WHERE status = 'processing'"
    ).fetchone()
    assert row[0] == "critical"

def test_fifo_within_same_severity(qm):
    """Jobs with equal severity are claimed oldest-first."""
    qm.enqueue("high", "file:///ref/first")
    qm.enqueue("high", "file:///ref/second")

    qm.claim_job(worker_id="w1")
    row = qm.cursor.execute(
        "SELECT payload_ref FROM triage_queue WHERE status = 'processing'"
    ).fetchone()
    assert row[0] == "file:///ref/first"

def test_emergency_backpressure_shedding(qm):
    """Low-severity jobs are shed when queue exceeds emergency depth."""
    qm.emergency_depth = 0  # Force shedding immediately
    result = qm.enqueue("low", "file:///ref/shedme")
    assert result == 1, "Expected shed return code 1"

    row = qm.cursor.execute(
        "SELECT status, shed_reason FROM triage_queue WHERE payload_ref = ?",
        ("file:///ref/shedme",)
    ).fetchone()
    assert row[0] == "shed"
    assert row[1] == "emergency_backpressure"

def test_critical_not_shed_under_backpressure(qm):
    """Critical jobs must never be shed even under emergency depth."""
    qm.emergency_depth = 0
    result = qm.enqueue("critical", "file:///ref/critical")
    assert result == 0, "Critical job must not be shed"

    row = qm.cursor.execute(
        "SELECT status FROM triage_queue WHERE payload_ref = ?",
        ("file:///ref/critical",)
    ).fetchone()
    assert row[0] == "pending"

def test_claim_increments_attempts(qm):
    """Claiming a job must increment its attempts counter."""
    qm.enqueue("high", "file:///ref/job")
    qm.claim_job(worker_id="w1")

    row = qm.cursor.execute(
        "SELECT attempts, status, lease_expires_at FROM triage_queue WHERE status = 'processing'"
    ).fetchone()
    assert row[0] == 1, "attempts should be 1 after first claim"
    assert row[1] == "processing"
    assert row[2] is not None, "lease_expires_at must be set on claim"

def test_claim_empty_queue_returns_none(qm):
    """Claiming from an empty queue returns None."""
    result = qm.claim_job(worker_id="w1")
    assert result is None

def test_shed_reason_recorded(qm):
    """Shedding is auditable — shed_reason must be recorded."""
    qm.emergency_depth = 0
    qm.enqueue("informational", "file:///ref/info")
    row = qm.cursor.execute(
        "SELECT shed_reason FROM triage_queue WHERE status = 'shed'"
    ).fetchone()
    assert row is not None
    assert row[0] is not None

def test_informational_shed_before_high(qm):
    """Under backpressure, informational sheds but high does not."""
    qm.emergency_depth = 0
    assert qm.enqueue("informational", "file:///ref/info") == 1
    assert qm.enqueue("high", "file:///ref/high") == 0

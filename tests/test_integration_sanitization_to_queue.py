"""Integration test: sanitize_payload -> TriageQueueManager lifecycle."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.sanitization_pipeline import sanitize_payload
from engine.queue_manager import TriageQueueManager


def test_full_lifecycle_normal_alert():
    """A normal alert should flow: sanitize -> enqueue -> claim -> complete."""
    payload = "Alert: user=admin action=login ip=10.0.0.1"
    result = sanitize_payload(payload, field_path="network.alert")
    assert "payload" in result
    assert "metadata" in result

    qm = TriageQueueManager(db_path=":memory:")
    ret = qm.enqueue("high", "ref-001")
    assert ret == 0

    job_id = qm.claim_job(worker_id="test-worker")
    assert job_id is not None

    qm.complete_job(job_id, success=True)

    next_job = qm.claim_job(worker_id="test-worker")
    assert next_job is None


def test_high_entropy_analytical_field_triggers_quarantine():
    """High-entropy payload in analytical field should trigger quarantine_ref."""
    # Payload generated to:
    # - Match tokenizer regex [a-zA-Z0-9+/=]{17,}
    # - Have entropy > 4.5
    # - NOT match allowlist patterns (not 32/40/64 chars, not all hex)
    payload = "o6r5IZ01tmAllD35n7kkUI8eZfoiGevAn20XzCxRDtkkd9Vbtd"
    result = sanitize_payload(payload, field_path="powershell.encoded_command")

    assert result["metadata"].get("sanitization_action") == "quarantine_ref", \
        f"Expected quarantine_ref, got {result['metadata'].get('sanitization_action')}"
    assert result["payload"] == "[QUARANTINED_REF]"


def test_backpressure_shedding_with_queue():
    """When queue depth exceeds threshold, low/info severity should be shed."""
    qm = TriageQueueManager(db_path=":memory:")
    qm.emergency_depth = 5

    for i in range(5):
        qm.enqueue("high", f"ref-{i}")

    ret = qm.enqueue("informational", "ref-shed-test")
    assert ret == 1

    ret = qm.enqueue("critical", "ref-critical")
    assert ret == 0

import pytest
import time
import sqlite3
import threading
from engine.queue_manager import TriageQueueManager
from engine.worker import Worker

@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "chaos_test.db")

@pytest.fixture
def queue_manager(db_path):
    qm = TriageQueueManager(db_path=db_path)
    qm.initialize_schema()
    return qm

def test_worker_crash_mid_job_lease_expiry(queue_manager):
    job_id = queue_manager.enqueue({"task": "process_data"}, priority=1)
    
    # Simulate worker picking up job
    worker = Worker(queue_manager, lease_duration=1)
    worker.claim_job()
    
    # Simulate crash by not completing and letting lease expire
    time.sleep(1.5)
    
    status = queue_manager.get_job_status(job_id)
    assert status == "PENDING"

def test_worker_crash_after_max_attempts(queue_manager):
    job_id = queue_manager.enqueue({"task": "fail_task"}, priority=1)
    
    # Simulate 3 failed attempts
    for _ in range(3):
        worker = Worker(queue_manager, lease_duration=0.1)
        worker.claim_job()
        queue_manager.mark_failed(job_id)
        time.sleep(0.2)
        
    status = queue_manager.get_job_status(job_id)
    assert status == "FAILED"

def test_multiple_workers_crash_simultaneously(queue_manager):
    for i in range(5):
        queue_manager.enqueue({"task": f"job_{i}"}, priority=1)
        
    def crash_worker():
        worker = Worker(queue_manager, lease_duration=0.1)
        worker.claim_job()
        # Crash occurs here (thread terminates)
        
    threads = [threading.Thread(target=crash_worker) for _ in range(3)]
    for t in threads: t.start()
    for t in threads: t.join()
    
    # Verify queue is still operational and jobs are recoverable
    time.sleep(0.5)
    pending_jobs = queue_manager.get_pending_jobs()
    assert len(pending_jobs) > 0

if __name__ == "__main__":
    import argparse
    import sys
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    
    if args.dry_run:
        print("Dry run successful.")
        sys.exit(0)
        
    ret = pytest.main([__file__])
    sys.exit(ret)
import sqlite3
import time
import logging
from datetime import datetime, timedelta

class TriageQueueManager:
    def __init__(self, db_path="soc_triage.db"):
        self.conn = sqlite3.connect(db_path, isolation_level=None)
        self.cursor = self.conn.cursor()
        self._init_schema()
        self.lease_interval = 900  # 15 minutes
        self.max_attempts = 3
        self.emergency_depth = 1000

    def _init_schema(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS triage_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                severity TEXT CHECK(severity IN ('critical', 'high', 'medium', 'low', 'informational')),
                payload_ref TEXT,
                status TEXT DEFAULT 'pending',
                attempts INTEGER DEFAULT 0,
                started_at TIMESTAMP,
                lease_expires_at TIMESTAMP,
                last_heartbeat_at TIMESTAMP,
                shed_reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    def enqueue(self, severity, payload_ref):
        depth = self.cursor.execute("SELECT count(*) FROM triage_queue WHERE status = 'pending'").fetchone()[0]
        if depth >= self.emergency_depth and severity in ('low', 'informational'):
            self.cursor.execute("INSERT INTO triage_queue (severity, payload_ref, status, shed_reason) VALUES (?, ?, 'shed', 'emergency_backpressure')", (severity, payload_ref))
            return 1
        self.cursor.execute("INSERT INTO triage_queue (severity, payload_ref) VALUES (?, ?)", (severity, payload_ref))
        return 0

    def claim_job(self, worker_id):
        # P.1: Severity prioritization (critical first) + FIFO
        # P.2: FOR UPDATE SKIP LOCKED equivalent in SQLite (limited concurrency)
        query = """
            UPDATE triage_queue 
            SET status = 'processing', 
                started_at = CURRENT_TIMESTAMP, 
                attempts = attempts + 1,
                lease_expires_at = datetime('now', '+15 minutes')
            WHERE id = (
                SELECT id FROM triage_queue 
                WHERE status = 'pending' 
                ORDER BY CASE severity 
                    WHEN 'critical' THEN 1 
                    WHEN 'high' THEN 2 
                    WHEN 'medium' THEN 3 
                    WHEN 'low' THEN 4 
                    ELSE 5 END, created_at ASC 
                LIMIT 1
            )
            RETURNING id
        """
        try:
            res = self.cursor.execute(query).fetchone()
            return res[0] if res else None
        except sqlite3.OperationalError:
            return None

    def heartbeat(self, job_id):
        self.cursor.execute("""
            UPDATE triage_queue 
            SET last_heartbeat_at = CURRENT_TIMESTAMP,
                lease_expires_at = datetime('now', '+15 minutes')
            WHERE id = ? AND status = 'processing'
        """, (job_id,))

    def reap_stale_jobs(self):
        # P.4: Stale job recovery (Section 35.9)
        # Reset stale jobs that haven't exhausted attempts
        self.cursor.execute("""
            UPDATE triage_queue
            SET status = 'pending', started_at = NULL, lease_expires_at = NULL
            WHERE status = 'processing'
            AND lease_expires_at < CURRENT_TIMESTAMP
            AND attempts < ?
        """, (self.max_attempts,))

        # Fail stale jobs that have exhausted attempts
        self.cursor.execute("""
            UPDATE triage_queue
            SET status = 'failed',
                shed_reason = 'max_attempts_exceeded_after_stale_recovery'
            WHERE status = 'processing'
            AND lease_expires_at < CURRENT_TIMESTAMP
            AND attempts >= ?
        """, (self.max_attempts,))
    def complete_job(self, job_id, success=True, reason=None):
        if success:
            self.cursor.execute("UPDATE triage_queue SET status = 'completed' WHERE id = ?", (job_id,))
        else:
            self.cursor.execute("""
                UPDATE triage_queue 
                SET status = CASE WHEN attempts >= ? THEN 'failed' ELSE 'pending' END,
                    shed_reason = ?
                WHERE id = ?
            """, (self.max_attempts, reason, job_id))

if __name__ == "__main__":
    exit(0)
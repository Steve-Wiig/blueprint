from pathlib import Path
import logging
import os
import sqlite3
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Status constants
STATUS_PENDING = 'pending'
STATUS_PROCESSING = 'processing'
STATUS_COMPLETED = 'completed'
STATUS_FAILED = 'failed'
STATUS_SHED = 'shed'

# Severity constants (for Python-side comparisons)
SEVERITY_CRITICAL = 'critical'
SEVERITY_HIGH = 'high'
SEVERITY_MEDIUM = 'medium'
SEVERITY_LOW = 'low'
SEVERITY_INFORMATIONAL = 'informational'

class TriageQueueManager:
    """
    Manages a triage queue stored in SQLite.

    Attributes
    ----------
    conn : sqlite3.Connection
        SQLite connection object.
    cursor : sqlite3.Cursor
        Cursor for executing SQL statements.
    lease_interval : int
        Lease duration in seconds for a claimed job.
    max_attempts : int
        Maximum number of attempts before a job is marked failed.
    emergency_depth : int
        Threshold for backpressure on low‑priority jobs.
    """

    def __init__(
        self,
        db_path: str = ":memory:",
        lease_interval: Optional[int] = None,
        max_attempts: Optional[int] = None,
        emergency_depth: Optional[int] = None,
    ) -> None:
        """
        Initialize the queue manager.

        Parameters
        ----------
        db_path : str, optional
            Path to the SQLite database file. Defaults to
            "soc_triage.db". Use ":memory:" for an in‑memory database.
        lease_interval : int, optional
            Lease duration in seconds for a claimed job. Defaults to 900 (15 minutes).
        max_attempts : int, optional
            Maximum number of attempts before a job is marked failed. Defaults to 3.
        emergency_depth : int, optional
            Threshold for backpressure on low‑priority jobs. Defaults to 1000.
        """
        self.conn: sqlite3.Connection = sqlite3.connect(db_path)
        self.cursor: sqlite3.Cursor = self.conn.cursor()
        self._init_schema()
        self.lease_interval: int = lease_interval if lease_interval is not None else int(os.getenv("QUEUE_LEASE_INTERVAL", "900"))
        self.max_attempts: int = max_attempts if max_attempts is not None else int(os.getenv("QUEUE_MAX_ATTEMPTS", "3"))
        self.emergency_depth: int = emergency_depth if emergency_depth is not None else int(os.getenv("QUEUE_EMERGENCY_DEPTH", "1000"))
        self._lease_modifier: str = f"+{self.lease_interval // 60} minutes"
        logger.info(
            "TriageQueueManager initialized with db_path=%s, lease_interval=%d, max_attempts=%d, emergency_depth=%d",
            db_path,
            self.lease_interval,
            self.max_attempts,
            self.emergency_depth,
        )

    def _init_schema(self) -> None:
        """
        Create the necessary tables, indexes, and triggers for the queue.
        """
        schema_path = Path(__file__).parent / "schema.sql"
        self.cursor.executescript(schema_path.read_text())
        self.conn.commit()
        logger.debug("Database schema initialized")

    def _get_job_severity(self, job_id: int) -> Optional[str]:
        """Fetch the severity of a job by ID.
        
        Args:
            job_id: The job ID to look up.
            
        Returns:
            The severity string, or None if not found.
        """
        row = self.cursor.execute("SELECT severity FROM triage_queue WHERE id = ?", (job_id,)).fetchone()
        return row[0] if row else None

    def _check_approval(self, job_id: int, target_status: str) -> bool:
        """
        Check if an approval exists for the job and target status.
        """
        row = self.cursor.execute(
            "SELECT 1 FROM triage_queue_approvals WHERE job_id = ? AND target_status = ?",
            (job_id, target_status),
        ).fetchone()
        return row is not None

    def approve_job(self, job_id: int, target_status: str, approver: str) -> None:
        """
        Record an approval for a critical job to transition to target_status.

        Parameters
        ----------
        job_id : int
            Identifier of the job.
        target_status : str
            The status being approved ('completed' or 'failed').
        approver : str
            Identifier of the approver.
        """
        if target_status not in ('completed', 'failed'):
            raise ValueError("target_status must be 'completed' or 'failed'")
        self.cursor.execute(
            """
            INSERT OR REPLACE INTO triage_queue_approvals (job_id, target_status, approved_by)
            VALUES (?, ?, ?)
            """,
            (job_id, target_status, approver),
        )
        self.conn.commit()
        logger.info("Approval recorded for job %d to %s by %s", job_id, target_status, approver)

    def enqueue(self, severity: str, payload_ref: str) -> int:
        """
        Add a job to the queue.

        Parameters
        ----------
        severity : str
            Job severity ('critical', 'high', 'medium', 'low', 'informational').
        payload_ref : str
            Reference to the job payload.

        Returns
        -------
        int
            1 if the job was shed due to backpressure, 0 otherwise.
        """
        depth = self.cursor.execute(
            "SELECT value FROM triage_queue_counters WHERE name = 'pending_count'"
        ).fetchone()[0]
        if depth >= self.emergency_depth and severity in ('low', 'informational'):
            self.cursor.execute(
                """
                INSERT INTO triage_queue
                    (severity, payload_ref, status, shed_reason, last_modified_by)
                VALUES (?, ?, 'shed', 'emergency_backpressure', 'system')
                """,
                (severity, payload_ref),
            )
            self.conn.commit()
            logger.warning("Job shed due to emergency backpressure: severity=%s, payload_ref=%s", severity, payload_ref)
            return 1
        self.cursor.execute(
            """
            INSERT INTO triage_queue (severity, payload_ref, last_modified_by)
            VALUES (?, ?, 'system')
            """,
            (severity, payload_ref),
        )
        self.conn.commit()
        logger.info("Job enqueued: severity=%s, payload_ref=%s", severity, payload_ref)
        return 0

    def claim_job(self, worker_id: str) -> Optional[int]:
        """
        Claim the highest‑priority pending job for processing.

        Parameters
        ----------
        worker_id : str
            Identifier of the worker claiming the job.

        Returns
        -------
        Optional[int]
            The ID of the claimed job, or None if no job is available.
        """
        # Atomic claim: SELECT-then-UPDATE collapsed into one statement
        # The subquery finds the highest-priority pending job, and the UPDATE
        # atomically claims it under SQLite's write lock (no race window).
        # RETURNING id gives us the claimed job without a second query.
        row = self.cursor.execute(
            f"""
            UPDATE triage_queue
            SET status = 'processing',
                started_at = CURRENT_TIMESTAMP,
                attempts = attempts + 1,
                lease_expires_at = datetime('now', '{self._lease_modifier}'),
                last_modified_by = ?
            WHERE id = (
                SELECT id FROM triage_queue
                WHERE status = 'pending'
                ORDER BY CASE severity
                    WHEN 'critical' THEN 1
                    WHEN 'high' THEN 2
                    WHEN 'medium' THEN 3
                    WHEN 'low' THEN 4
                    ELSE 5 END,
                    created_at ASC
                LIMIT 1
            )
            RETURNING id
            """,
            (worker_id,)
        ).fetchone()

        if not row:
            logger.debug("No pending jobs available for worker %s", worker_id)
            return None

        self.conn.commit()
        job_id = row[0]
        logger.info("Job %d claimed by worker %s", job_id, worker_id)
        return job_id

    def heartbeat(self, job_id: int) -> None:
        """
        Update the heartbeat and lease expiration for a processing job.

        Parameters
        ----------
        job_id : int
            Identifier of the job to heartbeat.
        """
        self.cursor.execute(
            f"""
            UPDATE triage_queue
            SET last_heartbeat_at = CURRENT_TIMESTAMP,
                lease_expires_at = datetime('now', '{self._lease_modifier}')
            WHERE id = ? AND status = 'processing'
            """,
            (job_id,),
        )
        self.conn.commit()
        logger.debug("Heartbeat updated for job %d", job_id)

    def reap_stale_jobs(self) -> None:
        """
        Recover or fail jobs that have exceeded their lease without completion.
        """
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        # Reset stale jobs that haven't exhausted attempts
        self.cursor.execute(
            """
            UPDATE triage_queue
            SET status = 'pending',
                started_at = NULL,
                lease_expires_at = NULL,
                last_modified_by = 'system'
            WHERE status = 'processing'
              AND lease_expires_at < ?
              AND attempts < ?
            """,
            (now, self.max_attempts),
        )
        reset_count = self.cursor.rowcount

        # Fail stale jobs that have exhausted attempts
        stale_jobs = self.cursor.execute(
            """
            SELECT id, severity FROM triage_queue
            WHERE status = 'processing'
              AND lease_expires_at < ?
              AND attempts >= ?
            """,
            (now, self.max_attempts),
        ).fetchall()

        failed_count = 0
        for job_id, severity in stale_jobs:
            if severity == 'critical':
                if not self._check_approval(job_id, 'failed'):
                    logger.warning("Critical job %d requires approval to fail; skipping", job_id)
                    continue
            self.cursor.execute(
                """
                UPDATE triage_queue
                SET status = 'failed',
                    shed_reason = 'max_attempts_exceeded_after_stale_recovery',
                    last_modified_by = 'system'
                WHERE id = ?
                """,
                (job_id,),
            )
            failed_count += self.cursor.rowcount

        self.conn.commit()
        if reset_count or failed_count:
            logger.info("Reaped stale jobs: reset=%d, failed=%d", reset_count, failed_count)

    def complete_job(self, job_id: int, success: bool = True, reason: Optional[str] = None, changed_by: Optional[str] = None) -> None:
        """
        Mark a job as completed or failed.

        Parameters
        ----------
        job_id : int
            Identifier of the job to complete.
        success : bool, optional
            Whether the job completed successfully. Defaults to True.
        reason : str, optional
            Reason for completion or failure.
        changed_by : str, optional
            Identifier of the user or system that changed the job status.
        """
        status = STATUS_COMPLETED if success else STATUS_FAILED
        self.cursor.execute(
            """
            UPDATE triage_queue
            SET status = ?,
                completed_at = CURRENT_TIMESTAMP,
                last_modified_by = COALESCE(?, 'system')
            WHERE id = ?
            """,
            (status, changed_by, job_id),
        )
        if reason:
            self.cursor.execute(
                """
                UPDATE triage_queue
                SET fail_reason = ?
                WHERE id = ?
                """,
                (reason, job_id),
            )
        self.conn.commit()
        logger.info("Job %d marked as %s", job_id, status)

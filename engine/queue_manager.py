import logging
import sqlite3
from typing import Optional

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

    def __init__(self, db_path: str = "soc_triage.db") -> None:
        """
        Initialize the queue manager.

        Parameters
        ----------
        db_path : str, optional
            Path to the SQLite database file. Defaults to
            "soc_triage.db". Use ":memory:" for an in‑memory database.
        """
        self.conn: sqlite3.Connection = sqlite3.connect(db_path)
        self.cursor: sqlite3.Cursor = self.conn.cursor()
        self._init_schema()
        self.lease_interval: int = 900  # 15 minutes
        self.max_attempts: int = 3
        self.emergency_depth: int = 1000
        logger.info("TriageQueueManager initialized with db_path=%s", db_path)

    def _init_schema(self) -> None:
        """
        Create the necessary tables, indexes, and triggers for the queue.
        """
        self.cursor.executescript("""
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_modified_by TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_triage_queue_pending
                ON triage_queue (status, severity, created_at);

            CREATE INDEX IF NOT EXISTS idx_triage_queue_lease
                ON triage_queue (lease_expires_at)
                WHERE status = 'processing';

            CREATE TABLE IF NOT EXISTS triage_queue_counters (
                name TEXT PRIMARY KEY,
                value INTEGER NOT NULL DEFAULT 0
            );

            INSERT OR IGNORE INTO triage_queue_counters (name, value)
                VALUES ('pending_count', 0);

            CREATE TRIGGER IF NOT EXISTS triage_queue_pending_inc
                AFTER INSERT ON triage_queue
                WHEN NEW.status = 'pending'
                BEGIN
                    UPDATE triage_queue_counters
                    SET value = value + 1
                    WHERE name = 'pending_count';
                END;

            CREATE TRIGGER IF NOT EXISTS triage_queue_pending_dec
                AFTER UPDATE ON triage_queue
                WHEN OLD.status = 'pending' AND NEW.status != 'pending'
                BEGIN
                    UPDATE triage_queue_counters
                    SET value = value - 1
                    WHERE name = 'pending_count';
                END;

            CREATE TRIGGER IF NOT EXISTS triage_queue_pending_dec_delete
                AFTER DELETE ON triage_queue
                WHEN OLD.status = 'pending'
                BEGIN
                    UPDATE triage_queue_counters
                    SET value = value - 1
                    WHERE name = 'pending_count';
                END;

            -- Audit table for immutable status change logs
            CREATE TABLE IF NOT EXISTS triage_queue_audit (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                old_status TEXT,
                new_status TEXT,
                changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                changed_by TEXT
            );

            -- Trigger to capture every status transition
            CREATE TRIGGER IF NOT EXISTS triage_queue_audit_status_change
                AFTER UPDATE OF status ON triage_queue
                WHEN OLD.status IS NOT NEW.status
                BEGIN
                    INSERT INTO triage_queue_audit (job_id, old_status, new_status, changed_by)
                    VALUES (NEW.id, OLD.status, NEW.status, COALESCE(NEW.last_modified_by, 'system'));
                END;

            -- Approvals table for critical status changes
            CREATE TABLE IF NOT EXISTS triage_queue_approvals (
                job_id INTEGER NOT NULL,
                target_status TEXT CHECK(target_status IN ('completed', 'failed')),
                approved_by TEXT NOT NULL,
                approved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (job_id, target_status)
            );
        """)
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
        # Find the next pending job
        candidate = self.cursor.execute(
            """
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
            """
        ).fetchone()
        if not candidate:
            logger.debug("No pending jobs available for worker %s", worker_id)
            return None

        job_id = candidate[0]
        self.cursor.execute(
            """
            UPDATE triage_queue
            SET status = 'processing',
                started_at = CURRENT_TIMESTAMP,
                attempts = attempts + 1,
                lease_expires_at = datetime('now', '+15 minutes'),
                last_modified_by = ?
            WHERE id = ?
            """,
            (worker_id, job_id),
        )
        self.conn.commit()
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
            """
            UPDATE triage_queue
            SET last_heartbeat_at = CURRENT_TIMESTAMP,
                lease_expires_at = datetime('now', '+15 minutes')
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
        # Reset stale jobs that haven't exhausted attempts
        self.cursor.execute(
            """
            UPDATE triage_queue
            SET status = 'pending',
                started_at = NULL,
                lease_expires_at = NULL,
                last_modified_by = 'system'
            WHERE status = 'processing'
              AND lease_expires_at < CURRENT_TIMESTAMP
              AND attempts < ?
            """,
            (self.max_attempts,),
        )
        reset_count = self.cursor.rowcount

        # Fail stale jobs that have exhausted attempts
        stale_jobs = self.cursor.execute(
            """
            SELECT id, severity FROM triage_queue
            WHERE status = 'processing'
              AND lease_expires_at < CURRENT_TIMESTAMP
              AND attempts >= ?
            """,
            (self.max_attempts,),
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
            Whether the job succeeded. Defaults to True.
        reason : Optional[str], optional
            Reason for failure if success is False.
        changed_by : Optional[str], optional
            Identifier of the entity performing the completion. Defaults to 'system'.
        """
        actor = changed_by or 'system'
        # Fetch job details
        job = self.cursor.execute(
            "SELECT severity, attempts FROM triage_queue WHERE id = ?", (job_id,)
        ).fetchone()
        if not job:
            logger.warning("Job %d not found for completion", job_id)
            return
        severity, attempts = job
        if success:
            new_status = 'completed'
        else:
            new_status = 'failed' if attempts >= self.max_attempts else 'pending'

        # Validate approval for critical jobs
        if severity == 'critical' and new_status in ('completed', 'failed'):
            if not self._check_approval(job_id, new_status):
                raise RuntimeError(f"Approval required for critical job {job_id} to transition to {new_status}")

        if success:
            self.cursor.execute(
                """
                UPDATE triage_queue
                SET status = 'completed',
                    last_modified_by = ?
                WHERE id = ?
                """,
                (actor, job_id),
            )
            logger.info("Job %d completed successfully by %s", job_id, actor)
        else:
            self.cursor.execute(
                """
                UPDATE triage_queue
                SET status = CASE WHEN attempts >= ? THEN 'failed' ELSE 'pending' END,
                    shed_reason = ?,
                    last_modified_by = ?
                WHERE id = ?
                """,
                (self.max_attempts, reason or 'unspecified', actor, job_id),
            )
            logger.warning("Job %d marked as failed by %s: %s", job_id, actor, reason or 'unspecified')
        self.conn.commit()
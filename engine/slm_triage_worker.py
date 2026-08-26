import sqlite3
import time
import argparse
import requests
import json
import logging
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass

logger = logging.getLogger(__name__)

SEVERITY_PRIORITY = {
    'critical': 1,
    'high': 2,
    'medium': 3,
    'low': 4,
}
DEFAULT_PRIORITY = 5


@dataclass
class WorkerConfig:
    """Configuration for the triage worker."""
    db: str
    slm_url: str
    lease: int
    max_retries: int
    base_delay: float


def get_db(db_path: str) -> sqlite3.Connection:
    """Establishes a connection to the SQLite database.

    Args:
        db_path: The file path to the SQLite database.

    Returns:
        A sqlite3.Connection object configured with row_factory.

    Raises:
        RuntimeError: If the database connection fails.
    """
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        cursor = conn.cursor()
        
        # Ensure priority column exists
        cursor.execute("PRAGMA table_info(triage_queue)")
        columns = [row[1] for row in cursor.fetchall()]
        priority_column_added = False
        if 'priority' not in columns:
            cursor.execute("ALTER TABLE triage_queue ADD COLUMN priority INTEGER DEFAULT ?", (DEFAULT_PRIORITY,))
            # Populate priority for existing rows based on severity using single CASE statement
            cursor.execute("""
                UPDATE triage_queue 
                SET priority = CASE severity 
                    WHEN 'critical' THEN 1 
                    WHEN 'high' THEN 2 
                    WHEN 'medium' THEN 3 
                    WHEN 'low' THEN 4 
                    ELSE 5 
                END 
                WHERE priority IS NULL OR priority = ?
            """, (DEFAULT_PRIORITY,))
            priority_column_added = True
        
        # Create claim index using priority if it doesn't exist
        # Only recreate if we just added the priority column (schema migration) or index is missing
        cursor.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_triage_claim'")
        index_exists = cursor.fetchone() is not None
        
        if priority_column_added or not index_exists:
            cursor.execute("DROP INDEX IF EXISTS idx_triage_claim")
            cursor.execute("""
                CREATE INDEX idx_triage_claim 
                ON triage_queue(status, priority, created_at) 
                WHERE status = 'pending'
            """)
        
        conn.commit()
        return conn
    except Exception as e:
        logger.error(f"DB_ERROR: {e}")
        raise RuntimeError(f"Failed to connect to database: {e}")

def heartbeat(conn: sqlite3.Connection, job_id: int, lease_interval: int) -> None:
    """Updates the heartbeat and lease expiry for a specific job.

    Args:
        conn: The active sqlite3.Connection object.
        job_id: The ID of the job to update.
        lease_interval: The duration in seconds to extend the lease.
    """
    try:
        expiry = datetime.now(timezone.utc) + timedelta(seconds=lease_interval)
        conn.execute(
            "UPDATE triage_queue SET last_heartbeat_at = ?, lease_expires_at = ? WHERE id = ?",
            (datetime.now(timezone.utc), expiry, job_id)
        )
        conn.commit()
    except Exception as e:
        logger.error(f"HEARTBEAT_FAIL: {e}")

def reap_stale(conn: sqlite3.Connection) -> None:
    """Resets jobs that have exceeded their lease time back to 'pending'.

    Args:
        conn: The active sqlite3.Connection object.
    """
    conn.execute(
        "UPDATE triage_queue SET status = 'pending', lease_expires_at = NULL WHERE status = 'processing' AND lease_expires_at < ?",
        (datetime.now(timezone.utc),)
    )
    conn.commit()

def run_worker(config: WorkerConfig) -> None:
    """Main loop for the triage worker.

    Claims pending jobs, processes them via an SLM endpoint, and updates the database.

    Args:
        config: Worker configuration containing db path, slm_url, and lease duration.
    """
    conn = get_db(config.db)
    empty_queue_backoff = 1
    MAX_BACKOFF = 30
    
    while True:
        reap_stale(conn)
        
        # Claim job with priority logic
        row = conn.execute(
            """
                UPDATE triage_queue 
                SET status = 'processing', 
                    started_at = ?, 
                    attempts = attempts + 1, 
                    lease_expires_at = ? 
                WHERE id = (
                    SELECT id FROM triage_queue 
                    WHERE status = 'pending' 
                    ORDER BY priority ASC, created_at ASC 
                    LIMIT 1
                )
                RETURNING id, payload_ref
            """,
            (datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(seconds=config.lease))
        ).fetchone()
        conn.commit()
        
        if not row:
            time.sleep(empty_queue_backoff)
            empty_queue_backoff = min(empty_queue_backoff * 2, MAX_BACKOFF)
            continue
            
        # Job found, reset backoff
        empty_queue_backoff = 1
            
        job_id, payload = row['id'], row['payload_ref']
        
        # Retry logic with exponential backoff for SLM call
        max_retries = config.max_retries
        base_delay = config.base_delay
        last_exception = None
        
        for attempt in range(max_retries + 1):
            # Send heartbeat before each retry attempt (after the first) to extend lease during long processing
            if attempt > 0:
                heartbeat(conn, job_id, config.lease)
            
            try:
                # Call SLM Endpoint
                resp = requests.post(config.slm_url, json={"ref": payload}, timeout=30)
                
                # Retry on 5xx server errors
                if 500 <= resp.status_code < 600:
                    raise requests.exceptions.HTTPError(f"Server error: {resp.status_code}", response=resp)
                
                resp.raise_for_status()
                verdict = resp.json()
                
                # Send heartbeat after successful SLM call before writing verdict
                heartbeat(conn, job_id, config.lease)
                
                # Write verdict
                conn.execute(
                    "INSERT INTO verdicts (job_id, result, processed_at) VALUES (?, ?, ?)",
                    (job_id, json.dumps(verdict), datetime.now(timezone.utc))
                )
                conn.execute("UPDATE triage_queue SET status = 'completed' WHERE id = ?", (job_id,))
                conn.commit()
                break  # Success, exit retry loop
                
            except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
                last_exception = e
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"SLM call failed (attempt {attempt + 1}/{max_retries + 1}): {e}. Retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    logger.error(f"SLM call failed after {max_retries + 1} attempts: {e}")
                    conn.execute("UPDATE triage_queue SET status = 'failed', failure_reason = ? WHERE id = ?", (str(e), job_id))
                    conn.commit()
            except Exception as e:
                # Non-retryable exception (e.g., database error)
                logger.error(f"Non-retryable error processing job {job_id}: {e}")
                conn.execute("UPDATE triage_queue SET status = 'failed', failure_reason = ? WHERE id = ?", (str(e), job_id))
                conn.commit()
                break

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--slm-url", required=True)
    parser.add_argument("--lease", type=int, default=900)
    parser.add_argument("--max-retries", type=int, default=3, help="Maximum number of retry attempts for SLM calls")
    parser.add_argument("--base-delay", type=float, default=1.0, help="Base delay in seconds for exponential backoff")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    
    config = WorkerConfig(
        db=args.db,
        slm_url=args.slm_url,
        lease=args.lease,
        max_retries=args.max_retries,
        base_delay=args.base_delay
    )
    
    try:
        run_worker(config)
    except KeyboardInterrupt:
        pass
    except Exception:
        raise RuntimeError('Worker failed')
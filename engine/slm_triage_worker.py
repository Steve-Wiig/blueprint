"""
SLM Triage Worker module.

This module provides functionality to process triage jobs from a SQLite database,
interact with an SLM endpoint, and manage job states and heartbeats.
"""
import sqlite3
import time
import sys
import argparse
import requests
import json
from datetime import datetime, timedelta, timezone
from typing import Any

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
        # Create supporting index for priority claim query
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_triage_claim 
            ON triage_queue(status, severity, created_at) 
            WHERE status = 'pending'
        """)
        conn.commit()
        return conn
    except Exception as e:
        print(f"DB_ERROR: {e}")
        raise RuntimeError(f"Library code called exit(2)")

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
        print(f"HEARTBEAT_FAIL: {e}")

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

def run_worker(args: argparse.Namespace) -> None:
    """Main loop for the triage worker.

    Claims pending jobs, processes them via an SLM endpoint, and updates the database.

    Args:
        args: Parsed command-line arguments containing db path, slm_url, and lease duration.
    """
    conn = get_db(args.db)
    
    while True:
        reap_stale(conn)
        
        # Claim job with priority logic
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE triage_queue 
            SET status = 'processing', 
                started_at = ?, 
                attempts = attempts + 1, 
                lease_expires_at = ? 
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
            RETURNING id, payload_ref
        """, (datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(seconds=args.lease)))
        
        row = cursor.fetchone()
        conn.commit()
        
        if not row:
            time.sleep(5)
            continue
            
        job_id, payload = row['id'], row['payload_ref']
        
        try:
            # Call SLM Endpoint
            resp = requests.post(args.slm_url, json={"ref": payload}, timeout=30)
            verdict = resp.json()
            
            # Write verdict
            conn.execute(
                "INSERT INTO verdicts (job_id, result, processed_at) VALUES (?, ?, ?)",
                (job_id, json.dumps(verdict), datetime.now(timezone.utc))
            )
            conn.execute("UPDATE triage_queue SET status = 'completed' WHERE id = ?", (job_id,))
            conn.commit()
            
        except Exception as e:
            conn.execute("UPDATE triage_queue SET status = 'failed', failure_reason = ? WHERE id = ?", (str(e), job_id))
            conn.commit()
            
        time.sleep(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--slm-url", required=True)
    parser.add_argument("--lease", type=int, default=900)
    args = parser.parse_args()
    
    try:
        run_worker(args)
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception:
        sys.exit(1)
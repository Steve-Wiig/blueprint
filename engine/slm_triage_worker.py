import sqlite3
import time
import sys
import argparse
import requests
import json
from datetime import datetime, timedelta

def get_db(db_path):
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"DB_ERROR: {e}")
        sys.exit(2)

def heartbeat(conn, job_id, lease_interval):
    try:
        expiry = datetime.now() + timedelta(seconds=lease_interval)
        conn.execute(
            "UPDATE triage_queue SET last_heartbeat_at = ?, lease_expires_at = ? WHERE id = ?",
            (datetime.now(), expiry, job_id)
        )
        conn.commit()
    except Exception as e:
        print(f"HEARTBEAT_FAIL: {e}")

def reap_stale(conn):
    conn.execute(
        "UPDATE triage_queue SET status = 'pending', lease_expires_at = NULL WHERE status = 'processing' AND lease_expires_at < ?",
        (datetime.now(),)
    )
    conn.commit()

def run_worker(args):
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
        """, (datetime.now(), datetime.now() + timedelta(seconds=args.lease)))
        
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
                (job_id, json.dumps(verdict), datetime.now())
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
import sqlite3
import json
import uuid
import sys
import logging
from datetime import datetime, timezone

DB_PATH = "/var/lib/local-soc/triage_queue.db"
LOG_FILE = "/var/log/local-soc/intake.log"

logging.basicConfig(filename=LOG_FILE, level=logging.INFO)

def sanitize_payload(data):
    """Section 34 Sanitization Pipeline: Strict schema enforcement."""
    try:
        # Whitelist allowed keys to prevent injection/malformed data
        allowed_keys = {'agent', 'rule_id', 'description', 'src_ip', 'dst_ip'}
        sanitized_payload = {k: str(data.get(k, "N/A")) for k in allowed_keys}
        
        # Validate severity mapping
        raw_level = int(data.get("rule", {}).get("level", 3))
        severity = max(0, min(5, raw_level))
        
        return {
            "id": str(uuid.uuid4()),
            "severity": severity,
            "payload": sanitized_payload,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, None
    except Exception as e:
        return None, str(e)

def intake_adapter(raw_payload):
    """Section 35.2 Intake Flow."""
    try:
        data = json.loads(raw_payload)
    except json.JSONDecodeError:
        raise RuntimeError(f"Library code called sys.exit(2)")

    sanitized, err = sanitize_payload(data)
    
    if err:
        logging.error(f"Sanitization failed: {err}")
        raise RuntimeError(f"Library code called sys.exit(1)")

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO triage_queue (
                id, severity, payload, status, created_at, attempts
            ) VALUES (?, ?, ?, 'pending', ?, 0)
        """, (
            sanitized['id'],
            sanitized['severity'],
            json.dumps(sanitized['payload']),
            sanitized['timestamp']
        ))
        
        conn.commit()
        return 202
    except sqlite3.Error as e:
        logging.critical(f"Database error: {e}")
        raise RuntimeError(f"Library code called sys.exit(1)")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    # Simulate intake from stdin or webhook buffer
    try:
        input_data = sys.stdin.read()
        status_code = intake_adapter(input_data)
        sys.exit(0)
    except Exception:
        sys.exit(1)
import sqlite3
import json
import uuid
import sys
import logging
import os
from datetime import datetime, timezone
from typing import Any

DB_PATH = os.getenv('TRIAGE_DB_PATH', '/var/lib/local-soc/triage_queue.db')
LOG_FILE = os.getenv('TRIAGE_LOG_FILE', '/var/log/local-soc/intake.log')

logging.basicConfig(filename=LOG_FILE, level=logging.INFO)

_connection: sqlite3.Connection | None = None

def _get_connection() -> sqlite3.Connection:
    global _connection
    if _connection is None:
        _connection = sqlite3.connect(DB_PATH, check_same_thread=False)
        _connection.execute("PRAGMA journal_mode=WAL")
        _connection.execute("PRAGMA busy_timeout=5000")
    return _connection

def sanitize_payload(data: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    try:
        allowed_keys = {'agent', 'rule_id', 'description', 'src_ip', 'dst_ip'}
        sanitized_payload = {k: data.get(k) for k in allowed_keys if k in data}
        
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

def intake_adapter(raw_payload: str) -> int:
    try:
        data = json.loads(raw_payload)
    except json.JSONDecodeError:
        raise RuntimeError("Library code called exit(2)")

    sanitized, err = sanitize_payload(data)
    
    if err:
        logging.error(f"Sanitization failed: {err}")
        raise RuntimeError("Library code called exit(1)")

    conn = _get_connection()
    try:
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
        raise RuntimeError("Library code called exit(1)")

if __name__ == "__main__":
    try:
        input_data = sys.stdin.read()
        status_code = intake_adapter(input_data)
        sys.exit(0)
    except Exception:
        sys.exit(1)
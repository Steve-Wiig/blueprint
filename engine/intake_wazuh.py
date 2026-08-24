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

STATUS_PENDING = 'pending'

_connection: sqlite3.Connection | None = None

def _get_connection() -> sqlite3.Connection:
    global _connection
    if _connection is None:
        _connection = sqlite3.connect(DB_PATH, check_same_thread=False)
        _connection.execute("PRAGMA journal_mode=WAL")
        _connection.execute("PRAGMA busy_timeout=5000")
        _init_audit_table(_connection)
    return _connection

def _init_audit_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            alert_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            details TEXT NOT NULL
        )
    """)
    conn.commit()

def _audit_log(conn: sqlite3.Connection, event_type: str, alert_id: str, details: dict[str, Any]) -> None:
    conn.execute(
        "INSERT INTO audit_log (event_type, alert_id, timestamp, details) VALUES (?, ?, ?, ?)",
        (event_type, alert_id, datetime.now(timezone.utc).isoformat(), json.dumps(details))
    )

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
    """
    Process and intake a raw payload into the triage queue.

    Args:
        raw_payload: str - JSON string containing alert data to be sanitized and stored.

    Returns:
        int: HTTP status code 202 indicating the payload was accepted for processing.

    Raises:
        RuntimeError: If the raw payload cannot be decoded from JSON, or if sanitization fails.
    """
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
            ) VALUES (?, ?, ?, ?, ?, 0)
        """, (
            sanitized['id'],
            sanitized['severity'],
            json.dumps(sanitized['payload']),
            STATUS_PENDING,
            sanitized['timestamp']
        ))
        
        _audit_log(conn, 'intake', sanitized['id'], {
            'severity': sanitized['severity'],
            'payload': sanitized['payload'],
            'status': STATUS_PENDING
        })
        
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
"""
Wazuh Alert Intake Module

This module handles the ingestion and sanitization of Wazuh alert payloads
for the SOC automation platform. It provides functions to validate, sanitize,
and persist incoming alerts into a SQLite triage queue.

Functions:
    sanitize_payload: Validates and normalizes raw Wazuh alert data.
    intake_adapter: Processes raw JSON payloads and stores them in the database.
"""

import sqlite3
import json
import uuid
import sys
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, Optional

DB_PATH = os.getenv('TRIAGE_DB_PATH', '/var/lib/local-soc/triage_queue.db')
LOG_FILE = os.getenv('TRIAGE_LOG_FILE', '/var/log/local-soc/intake.log')

# Logging configuration
logging.basicConfig(filename=LOG_FILE, level=logging.INFO)

def sanitize_payload(data: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    Sanitize and validate incoming Wazuh alert payload.

    Enforces a strict schema by whitelisting allowed keys and preserving native
    data types for downstream processing. Validates and normalizes severity level.

    Args:
        data: Raw alert dictionary from Wazuh JSON input.

    Returns:
        A tuple of (sanitized_dict, error_message). On success, sanitized_dict
        contains 'id', 'severity', 'payload', 'timestamp' keys and error_message is None.
        On failure, returns (None, error_description).

    Behavior:
        - Whitelists keys: agent, rule_id, description, src_ip, dst_ip
        - Preserves original value types (no string coercion)
        - Extracts severity from data['rule']['level'], clamps to range 0-5
        - Generates UUIDv4 for event ID
        - Adds UTC ISO8601 timestamp
    """
    try:
        # Whitelist allowed keys to prevent injection/malformed data
        allowed_keys = {'agent', 'rule_id', 'description', 'src_ip', 'dst_ip'}
        sanitized_payload = {k: data.get(k) for k in allowed_keys if k in data}
        
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

def intake_adapter(raw_payload: str) -> int:
    """Section 35.2 Intake Flow."""
    try:
        data = json.loads(raw_payload)
    except json.JSONDecodeError:
        raise RuntimeError("Library code called exit(2)")

    sanitized, err = sanitize_payload(data)
    
    if err:
        logging.error(f"Sanitization failed: {err}")
        raise RuntimeError("Library code called exit(1)")

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
        raise RuntimeError("Library code called exit(1)")
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
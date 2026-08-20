"""
Module for ingesting and queuing Suricata EVE events into a SQLite database.

This module provides functionality to initialize a triage database, sanitize incoming
event data, and enqueue events for further processing.
"""

import json
import sqlite3
import os
import time
import logging
from datetime import datetime, timedelta
from typing import Any, Dict

DB_PATH = "/var/lib/soc/triage_queue.db"
LOG_PATH = "/var/log/soc/intake.log"

logging.basicConfig(filename=LOG_PATH, level=logging.INFO)

def init_db() -> None:
    """Initializes the SQLite database and creates the triage_queue table if it does not exist.

    Exits the program with status code 2 if database initialization fails.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS triage_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payload TEXT,
                severity TEXT,
                status TEXT DEFAULT 'pending',
                attempts INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                lease_expires_at TIMESTAMP,
                last_heartbeat_at TIMESTAMP,
                failure_reason TEXT
            )
        ''')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"CONFIG_ERROR: {e}")
        raise RuntimeError(f"Library code called exit(2)")

def sanitize_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Filters and sanitizes an event dictionary to include only allowed keys.

    Args:
        event: The raw event dictionary to sanitize.

    Returns:
        A dictionary containing only the allowed keys and a normalized severity level.
    """
    allowed_keys = {'timestamp', 'event_type', 'src_ip', 'dest_ip', 'proto', 'alert', 'severity'}
    sanitized = {k: v for k, v in event.items() if k in allowed_keys}
    if 'alert' in sanitized and isinstance(sanitized['alert'], dict):
        sanitized['severity'] = sanitized['alert'].get('severity', 3)
    else:
        sanitized['severity'] = 3
    return sanitized

def enqueue_event(event: Dict[str, Any]) -> bool:
    """Inserts a sanitized event into the triage_queue database.

    Args:
        event: The sanitized event dictionary to store.

    Returns:
        True if the insertion was successful, False otherwise.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO triage_queue (payload, severity) VALUES (?, ?)",
            (json.dumps(event), event['severity'])
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.error(f"Queue write failure: {e}")
        return False

def process_eve_file(filepath: str) -> int:
    """Reads an EVE JSON file line by line and enqueues each event.

    Args:
        filepath: The path to the EVE JSON file.

    Returns:
        0 if processing completes successfully. Exits with status 1 or 3 on failure.
    """
    if not os.path.exists(filepath):
        raise RuntimeError(f"Library code called exit(3)")
    
    try:
        with open(filepath, 'r') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    sanitized = sanitize_event(data)
                    if not enqueue_event(sanitized):
                        raise RuntimeError(f"Library code called exit(1)")
                except json.JSONDecodeError:
                    continue
        return 0
    except Exception as e:
        logging.error(f"Intake error: {e}")
        raise RuntimeError(f"Library code called exit(1)")

if __name__ == "__main__":
    init_db()
    # Example usage: process_eve_file("/var/log/suricata/eve.json")
    exit(0)
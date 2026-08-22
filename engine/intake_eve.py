"""
Module for ingesting and queuing Suricata EVE events into a SQLite database.

This module provides functionality to initialize a triage database, sanitize incoming
event data, and enqueue events for further processing.
"""

import json
import sqlite3
import os
import logging
from typing import Any, Dict, List, Optional

DB_PATH = "/var/lib/soc/triage_queue.db"
LOG_PATH = "/var/log/soc/intake.log"

logging.basicConfig(filename=LOG_PATH, level=logging.INFO)


def init_db() -> None:
    """Initializes the SQLite database and creates the triage_queue table if it does not exist.

    Raises:
        RuntimeError: If database initialization fails.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
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
            """
        )
        conn.commit()
    except Exception as e:
        logging.error(f"Database initialization error: {e}")
        raise RuntimeError("Library code called exit(2)")
    finally:
        conn.close()


def sanitize_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Filters and sanitizes an event dictionary to include only allowed keys.

    Args:
        event: The raw event dictionary to sanitize.

    Returns:
        A dictionary containing only the allowed keys and a normalized severity level.
    """
    allowed_keys = {"timestamp", "event_type", "src_ip", "dest_ip", "proto", "alert", "severity"}
    sanitized = {k: v for k, v in event.items() if k in allowed_keys}
    if "alert" in sanitized and isinstance(sanitized["alert"], dict):
        sanitized["severity"] = sanitized["alert"].get("severity", 3)
    else:
        sanitized["severity"] = 3
    return sanitized


def enqueue_event(event: Dict[str, Any], conn: Optional[sqlite3.Connection] = None) -> bool:
    """Inserts a sanitized event into the triage_queue database.

    Args:
        event: The sanitized event dictionary to store.
        conn: Optional shared SQLite connection. If None, a new connection is created.

    Returns:
        True if the insertion was successful, False otherwise.
    """
    try:
        own_conn = False
        if conn is None:
            conn = sqlite3.connect(DB_PATH)
            own_conn = True
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO triage_queue (payload, severity) VALUES (?, ?)",
            (json.dumps(event), event["severity"]),
        )
        if own_conn:
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
        0 if processing completes successfully.

    Raises:
        RuntimeError: If the file does not exist or a processing error occurs.
    """
    if not os.path.exists(filepath):
        raise RuntimeError("Library code called exit(3)")

    try:
        # Collect rows for bulk insert
        rows: List[tuple] = []
        with open(filepath, "r") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    sanitized = sanitize_event(data)
                    rows.append((json.dumps(sanitized), sanitized["severity"]))
                except json.JSONDecodeError:
                    continue

        if not rows:
            return 0

        conn = sqlite3.connect(DB_PATH)
        try:
            cursor = conn.cursor()
            cursor.executemany(
                "INSERT INTO triage_queue (payload, severity) VALUES (?, ?)", rows
            )
            conn.commit()
        except Exception as e:
            logging.error(f"Bulk queue write failure: {e}")
            raise RuntimeError("Library code called exit(1)")
        finally:
            conn.close()

        return 0
    except Exception as e:
        logging.error(f"Intake error: {e}")
        raise RuntimeError("Library code called exit(1)")


if __name__ == "__main__":
    init_db()
    # Example usage: process_eve_file("/var/log/suricata/eve.json")
    exit(0)
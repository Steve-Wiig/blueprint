import json
import sqlite3
import os
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

DB_PATH = os.getenv('SOC_DB_PATH', '/var/lib/soc/triage_queue.db')
LOG_PATH = os.getenv('SOC_LOG_PATH', '/var/log/soc/intake.log')

logger = logging.getLogger(__name__)


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
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                old_status TEXT,
                new_status TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                actor TEXT
            )
            """
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        raise RuntimeError("Library code called exit(2)")
    finally:
        conn.close()


def _log_audit(event_id: int, old_status: Optional[str], new_status: str, actor: str = "system") -> None:
    """Logs a status change to the audit_log table.

    Args:
        event_id: The ID of the event.
        old_status: The previous status (None for initial creation).
        new_status: The new status.
        actor: The actor performing the change.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO audit_log (event_id, old_status, new_status, actor) VALUES (?, ?, ?, ?)",
            (event_id, old_status, new_status, actor),
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Audit log error: {e}")
    finally:
        conn.close()


def sanitize_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Filters and sanitizes an event dictionary to include only allowed keys.

    Args:
        event: The raw event dictionary from Suricata EVE.

    Returns:
        A dictionary containing only the allowed keys with sanitized values.
    """
    allowed_keys = {
        "timestamp",
        "event_type",
        "src_ip",
        "dest_ip",
        "src_port",
        "dest_port",
        "proto",
        "alert",
        "http",
        "dns",
        "tls",
        "ssh",
        "flow",
        "payload",
        "payload_printable",
        "stream",
        "packet",
        "metadata",
        "severity",
    }
    sanitized = {}
    for key in allowed_keys:
        if key in event:
            value = event[key]
            if isinstance(value, dict):
                sanitized[key] = {k: v for k, v in value.items() if not k.startswith("_")}
            elif isinstance(value, list):
                sanitized[key] = [v for v in value if v is not None]
            else:
                sanitized[key] = value
    if "severity" not in sanitized:
        sanitized["severity"] = "unknown"
    return sanitized


def enqueue_event(event: Dict[str, Any]) -> None:
    """Inserts a single sanitized event into the triage_queue table.

    Args:
        event: The sanitized event dictionary to enqueue.

    Raises:
        RuntimeError: If the database operation fails.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO triage_queue (payload, severity) VALUES (?, ?)",
            (json.dumps(event), event["severity"]),
        )
        event_id = cursor.lastrowid
        conn.commit()
        _log_audit(event_id, None, "pending", "enqueue")
    except Exception as e:
        logger.error(f"Enqueue event error: {e}")
        raise RuntimeError("Library code called exit(2)")
    finally:
        conn.close()


def process_eve_file(filepath: str) -> int:
    """Processes a Suricata EVE JSON file and bulk inserts events into the database.

    Args:
        filepath: Path to the EVE JSON file.

    Returns:
        The number of events successfully processed and inserted.

    Raises:
        RuntimeError: If the file cannot be read or database operation fails.
    """
    if not os.path.exists(filepath):
        raise RuntimeError(f"File not found: {filepath}")

    rows = []
    try:
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    sanitized = sanitize_event(data)
                    payload_str = json.dumps(sanitized)
                    rows.append((payload_str, sanitized["severity"]))
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.error(f"File read error: {e}")
        raise RuntimeError("Library code called exit(2)")

    if not rows:
        return 0

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.executemany(
            "INSERT INTO triage_queue (payload, severity) VALUES (?, ?)",
            rows,
        )
        conn.commit()
        return len(rows)
    except Exception as e:
        logger.error(f"Bulk insert error: {e}")
        raise RuntimeError("Library code called exit(2)")
    finally:
        conn.close()


def get_pending_events(limit: int = 100) -> List[Dict[str, Any]]:
    """Retrieves pending events from the triage_queue.

    Args:
        limit: Maximum number of events to retrieve.

    Returns:
        A list of event dictionaries with id, payload, severity, and attempts.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, payload, severity, attempts FROM triage_queue WHERE status = 'pending' LIMIT ?",
            (limit,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Get pending events error: {e}")
        raise RuntimeError("Library code called exit(2)")
    finally:
        conn.close()


def lease_event(event_id: int, ttl_seconds: int = 300) -> bool:
    """Attempts to lease a pending event for processing.

    Args:
        event_id: The ID of the event to lease.
        ttl_seconds: Time-to-live for the lease in seconds.

    Returns:
        True if the lease was acquired, False otherwise.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT status FROM triage_queue WHERE id = ?",
            (event_id,),
        )
        row = cursor.fetchone()
        old_status = row[0] if row else None
        
        cursor.execute(
            """
            UPDATE triage_queue
            SET status = 'processing',
                lease_expires_at = datetime('now', ?),
                last_heartbeat_at = datetime('now')
            WHERE id = ? AND status = 'pending'
            """,
            (f"+{ttl_seconds} seconds", event_id),
        )
        conn.commit()
        if cursor.rowcount > 0:
            _log_audit(event_id, old_status, "processing", "lease")
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Lease event error: {e}")
        raise RuntimeError("Library code called exit(2)")
    finally:
        conn.close()


def heartbeat_event(event_id: int, ttl_seconds: int = 300) -> bool:
    """Extends the lease on a processing event.

    Args:
        event_id: The ID of the event to heartbeat.
        ttl_seconds: Additional time-to-live for the lease in seconds.

    Returns:
        True if the heartbeat was successful, False otherwise.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE triage_queue
            SET lease_expires_at = datetime('now', ?),
                last_heartbeat_at = datetime('now')
            WHERE id = ? AND status = 'processing'
            """,
            (f"+{ttl_seconds} seconds", event_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Heartbeat event error: {e}")
        raise RuntimeError("Library code called exit(2)")
    finally:
        conn.close()


def complete_event(event_id: int) -> bool:
    """Marks an event as completed.

    Args:
        event_id: The ID of the event to complete.

    Returns:
        True if the event was marked complete, False otherwise.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT status FROM triage_queue WHERE id = ?",
            (event_id,),
        )
        row = cursor.fetchone()
        old_status = row[0] if row else None
        
        cursor.execute(
            "UPDATE triage_queue SET status = 'completed' WHERE id = ? AND status = 'processing'",
            (event_id,),
        )
        conn.commit()
        if cursor.rowcount > 0:
            _log_audit(event_id, old_status, "completed", "complete")
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Complete event error: {e}")
        raise RuntimeError("Library code called exit(2)")
    finally:
        conn.close()


def fail_event(event_id: int, reason: str) -> bool:
    """Marks an event as failed with a reason.

    Args:
        event_id: The ID of the event to fail.
        reason: The failure reason.

    Returns:
        True if the event was marked failed, False otherwise.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT status FROM triage_queue WHERE id = ?",
            (event_id,),
        )
        row = cursor.fetchone()
        old_status = row[0] if row else None
        
        cursor.execute(
            """
            UPDATE triage_queue
            SET status = 'failed',
                failure_reason = ?,
                attempts = attempts + 1
            WHERE id = ?
            """,
            (reason, event_id),
        )
        conn.commit()
        if cursor.rowcount > 0:
            _log_audit(event_id, old_status, "failed", "fail")
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Fail event error: {e}")
        raise RuntimeError("Library code called exit(2)")
    finally:
        conn.close()


def requeue_stale_events(threshold_seconds: int = 300) -> int:
    """Requeues events with expired leases back to pending status.

    Args:
        threshold_seconds: Lease age threshold in seconds.

    Returns:
        The number of events requeued.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM triage_queue WHERE status = 'processing' AND lease_expires_at < datetime('now', ?)",
            (f"-{threshold_seconds} seconds",),
        )
        event_ids = [row[0] for row in cursor.fetchall()]
        
        cursor.execute(
            """
            UPDATE triage_queue
            SET status = 'pending',
                lease_expires_at = NULL,
                last_heartbeat_at = NULL
            WHERE status = 'processing'
              AND lease_expires_at < datetime('now', ?)
            """,
            (f"-{threshold_seconds} seconds",),
        )
        conn.commit()
        for event_id in event_ids:
            _log_audit(event_id, "processing", "pending", "requeue_stale")
        return cursor.rowcount
    except Exception as e:
        logger.error(f"Requeue stale events error: {e}")
        raise RuntimeError("Library code called exit(2)")
    finally:
        conn.close()
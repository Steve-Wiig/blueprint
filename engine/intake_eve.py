import json
import sqlite3
import os
import logging
from typing import Any, Dict, List, Optional, Callable, TypeVar, Generator
from datetime import datetime, timezone
from contextlib import contextmanager

DB_PATH = os.getenv('SOC_DB_PATH', '/var/lib/soc/triage_queue.db')
LOG_PATH = os.getenv('SOC_LOG_PATH', '/var/log/soc/intake.log')

logger = logging.getLogger(__name__)

T = TypeVar('T')


def configure_logging() -> None:
    """Configure file logging to LOG_PATH if not already configured.

    This function MUST be called explicitly at application startup.
    It is NOT called at module import time to avoid filesystem I/O side effects
    during import (violates v11.7 no module-level side effects).
    """
    if not logger.handlers:
        log_dir = os.path.dirname(LOG_PATH)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.FileHandler(LOG_PATH)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        logger.addHandler(file_handler)
        logger.setLevel(logging.INFO)
def get_connection() -> Generator[sqlite3.Connection, None, None]:
    """Context manager for database connections with automatic cleanup."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def with_db(transaction: bool = False) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Parameterized decorator for database operations with optional transaction handling."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args: Any, **kwargs: Any) -> T:
            try:
                with get_connection() as conn:
                    if transaction:
                        with transaction(conn) as cursor:
                            return func(cursor, *args, **kwargs)
                    else:
                        return func(conn, *args, **kwargs)
            except Exception as e:
                logger.error(f"{func.__name__} error: {e}")
                raise RuntimeError("Library code called exit(2)")
        return wrapper
    return decorator

def execute_in_transaction(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator that provides a connection with transaction handling."""
    def _execute_with_error_handling(operation: Callable[[], T], func_name: str) -> T:
        try:
            return operation()
        except Exception as e:
            logger.error(f"{func_name} error: {e}")
            raise RuntimeError("Library code called exit(2)")

    def wrapper(*args: Any, **kwargs: Any) -> T:
        def operation():
            with get_connection() as conn:
                with transaction(conn) as cursor:
                    return func(cursor, *args, **kwargs)
        return _execute_with_error_handling(operation, func.__name__)
    return wrapper
def execute_with_connection(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator that provides a connection and handles errors."""
    def wrapper(*args: Any, **kwargs: Any) -> T:
        try:
            with get_connection() as conn:
                return func(conn, *args, **kwargs)
        except Exception as e:
            logger.error(f"{func.__name__} error: {e}")
            raise RuntimeError("Library code called exit(2)")
    return wrapper


def execute_in_transaction(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator that provides a connection with transaction handling."""
    def wrapper(*args: Any, **kwargs: Any) -> T:
        try:
            with get_connection() as conn:
                with transaction(conn) as cursor:
                    return func(cursor, *args, **kwargs)
        except Exception as e:
            logger.error(f"{func.__name__} error: {e}")
            raise RuntimeError("Library code called exit(2)")
    return wrapper


def init_db() -> None:
    """Initializes the SQLite database and creates the triage_queue table if it does not exist.

    Raises:
        RuntimeError: If database initialization fails.
    """
    try:
        db_dir = os.path.dirname(DB_PATH)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        with get_connection() as conn:
            with transaction(conn) as cursor:
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
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_triage_status ON triage_queue(status)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_triage_lease ON triage_queue(lease_expires_at)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_audit_event ON audit_log(event_id)"
                )
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        raise RuntimeError(f"Database initialization failed: {e}")
def _log_audit(cursor: sqlite3.Cursor, event_id: int, old_status: Optional[str], new_status: str, actor: str = "system") -> None:
    """Logs a status change to the audit_log table.

    Args:
        cursor: Database cursor to use for the insert.
        event_id: The ID of the event.
        old_status: The previous status (None for initial creation).
        new_status: The new status.
        actor: The actor performing the change.
    """
    try:
        cursor.execute(
            "INSERT INTO audit_log (event_id, old_status, new_status, actor) VALUES (?, ?, ?, ?)",
            (event_id, old_status, new_status, actor),
        )
    except Exception as e:
        logger.error(f"Audit log error: {e}")

import math
import hashlib
from typing import Any, Dict, List

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
            sanitized[key] = sanitize_value(event[key])
    if "severity" not in sanitized:
        sanitized["severity"] = "unknown"
    return sanitized@execute_in_transaction
def enqueue_event(cursor: sqlite3.Cursor, event: Dict[str, Any]) -> None:
    """Inserts a single sanitized event into the triage_queue table.

    Args:
        event: The sanitized event dictionary to enqueue.

    Raises:
        RuntimeError: If the database operation fails.
    """
    cursor.execute(
        "INSERT INTO triage_queue (payload, severity) VALUES (?, ?)",
        (json.dumps(event), event["severity"]),
    )
    event_id = cursor.lastrowid
    _log_audit(event_id, None, "pending", "enqueue")


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
        with get_connection() as conn:
            with transaction(conn) as cursor:
                cursor.executemany(
                    "INSERT INTO triage_queue (payload, severity) VALUES (?, ?)",
                    rows,
                )
        return len(rows)
    except Exception as e:
        logger.error(f"Bulk insert error: {e}")
        raise RuntimeError("Library code called exit(2)")


def get_pending_events(conn: sqlite3.Connection, limit: int = 100) -> List[Dict[str, Any]]:
    """Retrieves pending events from the triage_queue.

    Args:
        limit: Maximum number of events to retrieve.

    Returns:
        A list of event dictionaries with id, payload, severity, and attempts.
    """
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, payload, severity, attempts FROM triage_queue WHERE status = 'pending' ORDER BY created_at ASC LIMIT ?",
        (limit,),
    )
    rows = cursor.fetchall()
    return [dict(row) for row in rows]

@execute_in_transaction
def lease_event(cursor: sqlite3.Cursor, event_id: int, ttl_seconds: int = 300) -> bool:
    """Attempts to lease a pending event for processing.

    Args:
        event_id: The ID of the event to lease.
        ttl_seconds: Time-to-live for the lease in seconds.

    Returns:
        True if the lease was acquired, False otherwise.
    """
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
    if cursor.rowcount > 0:
        _log_audit(event_id, old_status, "processing", "lease")
    return cursor.rowcount > 0


@execute_in_transaction
def heartbeat_event(cursor: sqlite3.Cursor, event_id: int, ttl_seconds: int = 300) -> bool:
    """Extends the lease on a processing event.

    Args:
        event_id: The ID of the event to heartbeat.
        ttl_seconds: Additional time-to-live for the lease in seconds.

    Returns:
        True if the heartbeat was successful, False otherwise.
    """
    cursor.execute(
        """
        UPDATE triage_queue
        SET lease_expires_at = datetime('now', ?),
            last_heartbeat_at = datetime('now')
        WHERE id = ? AND status = 'processing'
        """,
        (f"+{ttl_seconds} seconds", event_id),
    )
    return cursor.rowcount > 0
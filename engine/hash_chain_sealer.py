import sys
import os
import hashlib
import logging
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple, Optional, Generator

import psycopg2
from psycopg2.extras import execute_values

DEFAULT_LOCK_ID = 37001
DEFAULT_BATCH_SIZE = 10000
GENESIS_HASH = (
    "0000000000000000000000000000000000000000000000000000000000000000"
)

logger = logging.getLogger(__name__)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "message", "pathname", "process", "processName",
                "relativeCreated", "thread", "threadName", "exc_info",
                "exc_text", "stack_info"
            }:
                log_data[key] = value
        return json.dumps(log_data)


def _acquire_lock(cur: psycopg2.extensions.cursor, lock_id: int) -> None:
    cur.execute("SELECT pg_advisory_lock(%s)", (lock_id,))


def _release_lock(cur: Optional[psycopg2.extensions.cursor], lock_id: int) -> None:
    if cur:
        try:
            cur.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
        except Exception:
            pass


def get_last_chain_state(cur: psycopg2.extensions.cursor) -> Tuple[int, str]:
    cur.execute(
        """
        SELECT COALESCE((
            SELECT chain_seq FROM audit_chain ORDER BY chain_seq DESC LIMIT 1
        ), 0) as last_seq,
        COALESCE((
            SELECT row_hash FROM audit_chain ORDER BY chain_seq DESC LIMIT 1
        ), %s) as prev_hash
        """,
        (GENESIS_HASH,),
    )
    row = cur.fetchone()
    return row[0], row[1]


def create_pending_cursor(conn: psycopg2.extensions.connection) -> psycopg2.extensions.cursor:
    pending_cur = conn.cursor(name="pending_cursor", withhold=True)
    pending_cur.execute(
        """
        SELECT h.id, h.ts, h.payload_sha256
        FROM handoffs h
        WHERE NOT EXISTS (SELECT 1 FROM audit_chain a WHERE a.row_id = h.id)
        ORDER BY h.ts ASC, h.id ASC
        """
    )
    return pending_cur


def fetch_pending_batches(
    pending_cur: psycopg2.extensions.cursor,
    batch_size: int,
) -> Generator[List[Tuple], None, None]:
    while True:
        pending_rows = pending_cur.fetchmany(batch_size)
        if not pending_rows:
            break
        yield pending_rows


def compute_chain_hashes(
    batch: List[Tuple],
    last_seq: int,
    prev_hash: str,
) -> Tuple[List[Tuple], int, str]:
    rows_to_insert = []
    for row_id, row_ts, payload_sha in batch:
        last_seq += 1
        canonical_data = f"{last_seq}{prev_hash}{payload_sha}".encode("utf-8")
        row_hash = hashlib.sha256(canonical_data).hexdigest()
        rows_to_insert.append(
            (
                last_seq,
                "handoffs",
                row_id,
                row_ts,
                payload_sha,
                prev_hash,
                row_hash,
            )
        )
        prev_hash = row_hash
    return rows_to_insert, last_seq, prev_hash


def insert_chain_links(cur: psycopg2.extensions.cursor, rows_to_insert: List[Tuple]) -> None:
    insert_query = """
        INSERT INTO audit_chain
        (chain_seq, table_name, row_id, row_ts, canonical_payload_sha256,
         previous_hash, row_hash)
        VALUES %s
    """
    execute_values(cur, insert_query, rows_to_insert)


def _close_cursor_safely(cur: Optional[psycopg2.extensions.cursor]) -> None:
    if cur:
        try:
            cur.close()
        except Exception:
            pass


def _close_connection_safely(conn: Optional[psycopg2.extensions.connection]) -> None:
    if conn:
        try:
            conn.close()
        except Exception:
            pass


def seal_audit_chain_with_connection(
    conn: psycopg2.extensions.connection,
    lock_id: int = DEFAULT_LOCK_ID,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> None:
    cur = None
    pending_cur = None
    lock_acquired = False
    last_seq = 0
    pending_count = 0
    try:
        cur = conn.cursor()

        _acquire_lock(cur, lock_id)
        lock_acquired = True

        last_seq, prev_hash = get_last_chain_state(cur)

        pending_cur = create_pending_cursor(conn)

        for batch in fetch_pending_batches(pending_cur, batch_size):
            pending_count = len(batch)
            rows_to_insert, last_seq, prev_hash = compute_chain_hashes(
                batch, last_seq, prev_hash
            )
            insert_chain_links(cur, rows_to_insert)
            conn.commit()

    except Exception as e:
        logger.error(
            "Sealer failed",
            extra={
                "lock_id": lock_id,
                "batch_size": batch_size,
                "pending_count": pending_count,
                "last_seq": last_seq,
            },
            exc_info=True,
        )
        if conn:
            conn.rollback()
        raise RuntimeError(f"Sealer failed: {e}") from e
    finally:
        _release_lock(cur, lock_id) if lock_acquired else None
        _close_cursor_safely(pending_cur)
        _close_cursor_safely(cur)


def seal_audit_chain(
    db_config: Dict[str, Any],
    lock_id: int = DEFAULT_LOCK_ID,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> None:
    conn = None
    try:
        conn = psycopg2.connect(**db_config)
        seal_audit_chain_with_connection(conn, lock_id, batch_size)
    finally:
        _close_connection_safely(conn)


def load_config() -> Dict[str, Any]:
    required_vars = ["SOC_DBNAME", "SOC_USER"]
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    db_config = {
        "dbname": os.getenv("SOC_DBNAME"),
        "user": os.getenv("SOC_USER"),
    }
    if password := os.getenv("SOC_PASSWORD"):
        db_config["password"] = password
    if host := os.getenv("SOC_HOST"):
        db_config["host"] = host
    if port := os.getenv("SOC_PORT"):
        db_config["port"] = int(port)

    batch_size = DEFAULT_BATCH_SIZE
    if batch_size_env := os.getenv("SOC_BATCH_SIZE"):
        try:
            batch_size = int(batch_size_env)
        except ValueError:
            pass

    return {"db_config": db_config, "batch_size": batch_size}


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)


def main() -> None:
    configure_logging()
    config = load_config()
    seal_audit_chain(config["db_config"], batch_size=config["batch_size"])


if __name__ == "__main__":
    main()
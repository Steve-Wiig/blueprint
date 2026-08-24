"""Module for sealing audit chains using cryptographic hashing.

This module provides functionality to process pending handoff records,
link them into a cryptographic chain, and persist them to a PostgreSQL database.
"""

import sys
import os
import hashlib
from typing import Dict, Any

import psycopg2
from psycopg2.extras import execute_values

# Default constants
DEFAULT_LOCK_ID = 37001
DEFAULT_BATCH_SIZE = 1000
GENESIS_HASH = (
    "0000000000000000000000000000000000000000000000000000000000000000"
)


def seal_audit_chain(
    db_config: Dict[str, Any],
    lock_id: int = DEFAULT_LOCK_ID,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> None:
    """Processes pending handoff records and seals them into an audit chain.

    This function acquires a session-level advisory lock on the database to ensure atomicity,
    identifies unlinked records, computes a SHA-256 hash based on the previous
    chain link and current payload, and inserts the result into the audit_chain table.
    Commits after each batch to reduce transaction size and lock contention.

    Args:
        db_config: A dictionary containing database connection parameters
            compatible with psycopg2.connect().
        lock_id: Advisory lock identifier used to serialize processing.
        batch_size: Number of rows to fetch and insert per batch.

    Returns:
        None. Raises RuntimeError on failure.
    """
    conn = None
    cur = None
    pending_cur = None
    lock_acquired = False
    try:
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()

        # Acquire a session-level advisory lock to guarantee exclusive processing
        cur.execute("SELECT pg_advisory_lock(%s)", (lock_id,))
        lock_acquired = True

        # Determine the last sequence number in the chain
        cur.execute("SELECT COALESCE(MAX(chain_seq), 0) FROM audit_chain")
        last_seq = cur.fetchone()[0]

        # Resolve the previous hash (genesis if chain is empty)
        if last_seq == 0:
            prev_hash = GENESIS_HASH
        else:
            cur.execute(
                "SELECT row_hash FROM audit_chain WHERE chain_seq = %s",
                (last_seq,),
            )
            prev_hash = cur.fetchone()[0]

        # Use a server‑side cursor WITH HOLD to avoid loading all pending rows into memory
        # and allow commits between batches.
        pending_cur = conn.cursor(name="pending_cursor", withhold=True)
        pending_cur.execute(
            """
            SELECT h.id, h.ts, h.payload_sha256
            FROM handoffs h
            WHERE NOT EXISTS (SELECT 1 FROM audit_chain a WHERE a.row_id = h.id)
            ORDER BY h.ts ASC, h.id ASC
            """
        )

        while True:
            pending_rows = pending_cur.fetchmany(batch_size)
            if not pending_rows:
                break

            rows_to_insert = []
            for row_id, row_ts, payload_sha in pending_rows:
                last_seq += 1
                canonical_data = f"{last_seq}{prev_hash}{payload_sha}".encode(
                    "utf-8"
                )
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

            insert_query = """
                INSERT INTO audit_chain
                (chain_seq, table_name, row_id, row_ts, canonical_payload_sha256,
                 previous_hash, row_hash)
                VALUES %s
            """
            execute_values(cur, insert_query, rows_to_insert)
            conn.commit()

        # Clean up cursors
        if pending_cur:
            pending_cur.close()
        cur.close()
        conn.close()

    except Exception as e:
        print(f"Sealer Error: {e}", file=sys.stderr)
        if conn:
            conn.rollback()
        raise RuntimeError(f"Sealer failed: {e}")
    finally:
        # Ensure advisory lock is released even on error
        if lock_acquired and cur:
            try:
                cur.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
            except Exception:
                pass
        if pending_cur:
            try:
                pending_cur.close()
            except Exception:
                pass
        if cur:
            try:
                cur.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def main() -> None:
    db_config = {}
    if dbname := os.getenv("SOC_DBNAME"):
        db_config["dbname"] = dbname
    if user := os.getenv("SOC_USER"):
        db_config["user"] = user
    seal_audit_chain(db_config)


if __name__ == "__main__":
    main()
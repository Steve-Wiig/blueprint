"""Module for sealing audit chains using cryptographic hashing.

This module provides functionality to process pending handoff records,
link them into a cryptographic chain, and persist them to a PostgreSQL database.
"""

import sys
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

    This function acquires an advisory lock on the database to ensure atomicity,
    identifies unlinked records, computes a SHA-256 hash based on the previous
    chain link and current payload, and inserts the result into the audit_chain table.

    Args:
        db_config: A dictionary containing database connection parameters
            compatible with psycopg2.connect().
        lock_id: Advisory lock identifier used to serialize processing.
        batch_size: Number of rows to fetch and insert per batch.

    Returns:
        None. Raises RuntimeError on failure.
    """
    try:
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()

        # Acquire an advisory lock to guarantee exclusive processing
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (lock_id,))

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

        # Use a server‑side cursor to avoid loading all pending rows into memory
        pending_cur = conn.cursor(name="pending_cursor")
        pending_cur.execute(
            """
            SELECT h.id, h.ts, h.payload_sha256
            FROM handoffs h
            LEFT JOIN audit_chain a ON a.row_id = h.id
            WHERE a.row_id IS NULL
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

        # Clean up cursors and commit transaction
        pending_cur.close()
        conn.commit()
        cur.close()
        conn.close()

    except Exception as e:
        print(f"Sealer Error: {e}", file=sys.stderr)
        raise RuntimeError(f"Sealer failed: {e}")


def main() -> None:
    seal_audit_chain({"dbname": "soc_ledger", "user": "sealer_role"})


if __name__ == "__main__":
    main()
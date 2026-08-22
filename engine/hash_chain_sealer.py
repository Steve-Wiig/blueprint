"""Module for sealing audit chains using cryptographic hashing.

This module provides functionality to process pending handoff records,
link them into a cryptographic chain, and persist them to a PostgreSQL database.
"""

import sys
import hashlib
from typing import Dict, Any

import psycopg2
from psycopg2.extras import execute_values


def seal_audit_chain(db_config: Dict[str, Any]) -> None:
    """Processes pending handoff records and seals them into an audit chain.

    This function acquires an advisory lock on the database to ensure atomicity,
    identifies unlinked records, computes a SHA-256 hash based on the previous
    chain link and current payload, and inserts the result into the audit_chain table.

    Args:
        db_config: A dictionary containing database connection parameters
            compatible with psycopg2.connect().

    Returns:
        None. Raises RuntimeError on failure.
    """
    GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000"
    LOCK_ID = 37001

    try:
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()

        # Acquire an advisory lock to guarantee exclusive processing
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))

        # Determine the last sequence number in the chain
        cur.execute("SELECT COALESCE(MAX(chain_seq), 0) FROM audit_chain")
        last_seq = cur.fetchone()[0]

        # Resolve the previous hash (genesis if chain is empty)
        if last_seq == 0:
            prev_hash = GENESIS_HASH
        else:
            cur.execute(
                "SELECT row_hash FROM audit_chain WHERE chain_seq = %s", (last_seq,)
            )
            prev_hash = cur.fetchone()[0]

        # Efficiently fetch handoff rows that are not yet linked in audit_chain
        cur.execute(
            """
            SELECT h.id, h.ts, h.payload_sha256
            FROM handoffs h
            LEFT JOIN audit_chain a ON a.row_id = h.id
            WHERE a.row_id IS NULL
            ORDER BY h.ts ASC, h.id ASC
            """
        )
        pending_rows = cur.fetchall()

        rows_to_insert = []
        for row_id, row_ts, payload_sha in pending_rows:
            last_seq += 1

            canonical_data = f"{last_seq}{prev_hash}{payload_sha}".encode("utf-8")
            row_hash = hashlib.sha256(canonical_data).hexdigest()

            rows_to_insert.append(
                (
                    last_seq,
                    'handoffs',
                    row_id,
                    row_ts,
                    payload_sha,
                    prev_hash,
                    row_hash,
                )
            )

            prev_hash = row_hash

        # Batch insert rows into audit_chain table
        insert_query = """
            INSERT INTO audit_chain
            (chain_seq, table_name, row_id, row_ts, canonical_payload_sha256,
             previous_hash, row_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        execute_values(cur, insert_query, rows_to_insert)

        conn.commit()
        cur.close()
        conn.close()

    except Exception as e:
        print(f"Sealer Error: {e}", file=sys.stderr)
        raise RuntimeError(f"Sealer failed: {e}")


if __name__ == "__main__":
    seal_audit_chain({"dbname": "soc_ledger", "user": "sealer_role"})
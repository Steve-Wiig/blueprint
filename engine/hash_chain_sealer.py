"""Module for sealing audit chains using cryptographic hashing.

This module provides functionality to process pending handoff records,
link them into a cryptographic chain, and persist them to a PostgreSQL database.
"""

import psycopg2
import hashlib
import sys
from typing import Dict, Any

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

        cur.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))

        cur.execute("SELECT COALESCE(MAX(chain_seq), 0) FROM audit_chain")
        last_seq = cur.fetchone()[0]
        
        if last_seq == 0:
            prev_hash = GENESIS_HASH
        else:
            cur.execute("SELECT row_hash FROM audit_chain WHERE chain_seq = %s", (last_seq,))
            prev_hash = cur.fetchone()[0]

        cur.execute("""
            SELECT id, ts, payload_sha256 
            FROM handoffs 
            WHERE id NOT IN (SELECT row_id FROM audit_chain)
            ORDER BY ts ASC, id ASC
        """)
        pending_rows = cur.fetchall()

        for row in pending_rows:
            row_id, row_ts, payload_sha = row
            last_seq += 1
            
            canonical_data = f"{last_seq}{prev_hash}{payload_sha}".encode('utf-8')
            row_hash = hashlib.sha256(canonical_data).hexdigest()

            cur.execute("""
                INSERT INTO audit_chain 
                (chain_seq, table_name, row_id, row_ts, canonical_payload_sha256, previous_hash, row_hash)
                VALUES (%s, 'handoffs', %s, %s, %s, %s, %s)
            """, (last_seq, row_id, row_ts, payload_sha, prev_hash, row_hash))
            
            prev_hash = row_hash

        conn.commit()
        cur.close()
        conn.close()

    except Exception as e:
        print(f"Sealer Error: {e}", file=sys.stderr)
        raise RuntimeError(f"Sealer failed: {e}")

if __name__ == "__main__":
    seal_audit_chain({"dbname": "soc_ledger", "user": "sealer_role"})
import psycopg2
import hashlib
import sys

def seal_audit_chain(db_config):
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
        sys.exit(0)

    except Exception as e:
        print(f"Sealer Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    seal_audit_chain({"dbname": "soc_ledger", "user": "sealer_role"})
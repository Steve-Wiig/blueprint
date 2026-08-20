import sqlite3
import psycopg2
import argparse
import sys
import json

def get_db_connections(pg_dsn, sqlite_path):
    try:
        pg_conn = psycopg2.connect(pg_dsn)
        sq_conn = sqlite3.connect(sqlite_path)
        return pg_conn, sq_conn
    except Exception as e:
        print(f"Connection error: {e}")
        sys.exit(2)

def check_quota(sq_conn, provider):
    cursor = sq_conn.cursor()
    cursor.execute("SELECT remaining FROM quota_ledger WHERE provider = ?", (provider,))
    row = cursor.fetchone()
    return row[0] if row else 0

def update_quota(sq_conn, provider, cost):
    cursor = sq_conn.cursor()
    cursor.execute("UPDATE quota_ledger SET remaining = remaining - ? WHERE provider = ?", (cost, provider))
    sq_conn.commit()

def process_jobs(pg_conn, sq_conn):
    pg_cur = pg_conn.cursor()
    pg_cur.execute("SELECT id, ioc_value, provider FROM enrichment_jobs WHERE status = 'PENDING'")
    jobs = pg_cur.fetchall()

    for job_id, ioc, provider in jobs:
        quota = check_quota(sq_conn, provider)
        if quota <= 0:
            continue
        
        try:
            # Mock enrichment logic
            result = {"status": "enriched", "data": f"mock_data_for_{ioc}"}
            
            pg_cur.execute(
                "UPDATE enrichment_jobs SET status = 'COMPLETED', result = %s WHERE id = %s",
                (json.dumps(result), job_id)
            )
            update_quota(sq_conn, provider, 1)
            pg_conn.commit()
        except Exception:
            pg_conn.rollback()
            sys.exit(1)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-dsn", required=True)
    parser.add_argument("--sqlite-path", required=True)
    args = parser.parse_args()

    pg_conn, sq_conn = get_db_connections(args.pg_dsn, args.sqlite_path)
    
    try:
        process_jobs(pg_conn, sq_conn)
    finally:
        pg_conn.close()
        sq_conn.close()
    
    sys.exit(0)

if __name__ == "__main__":
    main()
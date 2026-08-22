"""Module for scheduling and processing enrichment jobs using PostgreSQL and SQLite."""

import sqlite3
import psycopg2
import argparse
import json
from typing import Tuple

def get_db_connections(pg_dsn: str, sqlite_path: str) -> Tuple[psycopg2.extensions.connection, sqlite3.Connection]:
    """Establishes connections to PostgreSQL and SQLite databases.

    Args:
        pg_dsn: The Data Source Name for the PostgreSQL database.
        sqlite_path: The file path to the SQLite database.

    Returns:
        A tuple containing the PostgreSQL connection and the SQLite connection.
    """
    try:
        pg_conn = psycopg2.connect(pg_dsn)
        sq_conn = sqlite3.connect(sqlite_path)
        return pg_conn, sq_conn
    except Exception as e:
        print(f"Connection error: {e}")
        raise RuntimeError("Failed to establish database connections")

def check_quota(sq_conn: sqlite3.Connection, provider: str) -> int:
    """Checks the remaining quota for a specific provider in the SQLite database.

    Args:
        sq_conn: The SQLite database connection.
        provider: The name of the enrichment provider.

    Returns:
        The remaining quota as an integer.
    """
    cursor = sq_conn.cursor()
    cursor.execute("SELECT remaining FROM quota_ledger WHERE provider = ?", (provider,))
    row = cursor.fetchone()
    return row[0] if row else 0

def update_quota(sq_conn: sqlite3.Connection, provider: str, cost: int) -> None:
    """Decrements the quota for a specific provider in the SQLite database.

    Args:
        sq_conn: The SQLite database connection.
        provider: The name of the enrichment provider.
        cost: The amount to decrement from the quota.
    """
    cursor = sq_conn.cursor()
    cursor.execute("UPDATE quota_ledger SET remaining = remaining - ? WHERE provider = ?", (cost, provider))
    sq_conn.commit()

def process_jobs(pg_conn: psycopg2.extensions.connection, sq_conn: sqlite3.Connection) -> None:
    """Fetches pending enrichment jobs and processes them if quota is available.

    Args:
        pg_conn: The PostgreSQL database connection.
        sq_conn: The SQLite database connection.
    """
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
        except Exception as e:
            pg_conn.rollback()
            raise RuntimeError("Failed to process enrichment job") from e

def main() -> None:
    """Parses command line arguments and initiates the job processing workflow."""
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

if __name__ == "__main__":
    main()
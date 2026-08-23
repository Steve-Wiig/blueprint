import argparse
import json
import sqlite3
import psycopg2
from typing import Tuple, Dict, List

def get_db_connections(pg_dsn: str, sqlite_path: str) -> Tuple[psycopg2.extensions.connection, sqlite3.Connection]:
    """Establishes connections to PostgreSQL and SQLite databases.

    Args:
        pg_dsn: The Data Source Name for the PostgreSQL database.
        sqlite_path: The file path to the SQLite database. Use ':memory:' for in‑memory DB.

    Returns:
        A tuple containing the PostgreSQL connection and the SQLite connection.
    """
    try:
        pg_conn = psycopg2.connect(pg_dsn)
        sq_conn = sqlite3.connect(sqlite_path)
        return pg_conn, sq_conn
    except Exception as e:
        print(f"Connection error: {e}")
        raise RuntimeError("Failed to establish database connections") from e

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

def get_provider_cost(sq_conn: sqlite3.Connection, provider: str) -> int:
    """Retrieves the cost per enrichment for a provider.

    Args:
        sq_conn: The SQLite database connection.
        provider: The name of the enrichment provider.

    Returns:
        The cost as an integer. Defaults to 1 if not specified.
    """
    cursor = sq_conn.cursor()
    cursor.execute("SELECT cost FROM provider_costs WHERE provider = ?", (provider,))
    row = cursor.fetchone()
    return row[0] if row else 1

def update_quota(sq_conn: sqlite3.Connection, provider: str, cost: int) -> None:
    """Decrements the quota for a specific provider in the SQLite database.

    Args:
        sq_conn: The SQLite database connection.
        provider: The name of the enrichment provider.
        cost: The amount to decrement from the quota.
    """
    cursor = sq_conn.cursor()
    cursor.execute(
        "UPDATE quota_ledger SET remaining = remaining - ? WHERE provider = ?",
        (cost, provider)
    )
    sq_conn.commit()

def _fetch_provider_data(sq_conn: sqlite3.Connection, providers: List[str]) -> Tuple[Dict[str, int], Dict[str, int]]:
    """Fetches quota and cost for multiple providers in bulk.

    Args:
        sq_conn: The SQLite database connection.
        providers: List of provider names.

    Returns:
        Tuple of (quota_dict, cost_dict) keyed by provider.
    """
    if not providers:
        return {}, {}
    
    placeholders = ','.join(['?'] * len(providers))
    cursor = sq_conn.cursor()
    
    cursor.execute(f"SELECT provider, remaining FROM quota_ledger WHERE provider IN ({placeholders})", providers)
    quota_dict = {row[0]: row[1] for row in cursor.fetchall()}
    
    cursor.execute(f"SELECT provider, cost FROM provider_costs WHERE provider IN ({placeholders})", providers)
    cost_dict = {row[0]: row[1] for row in cursor.fetchall()}
    
    return quota_dict, cost_dict

def process_jobs(pg_conn: psycopg2.extensions.connection, sq_conn: sqlite3.Connection) -> None:
    """Fetches pending enrichment jobs and processes them if quota is available.

    Args:
        pg_conn: The PostgreSQL database connection.
        sq_conn: The SQLite database connection.
    """
    pg_cur = pg_conn.cursor()
    pg_cur.execute(
        "SELECT id, ioc_value, provider FROM enrichment_jobs WHERE status = 'PENDING'"
    )
    jobs = pg_cur.fetchall()

    if not jobs:
        return

    providers = list({job[2] for job in jobs})
    quota_cache, cost_cache = _fetch_provider_data(sq_conn, providers)

    for job_id, ioc, provider in jobs:
        quota = quota_cache.get(provider, 0)
        cost = cost_cache.get(provider, 1)
        if quota < cost:
            continue

        try:
            # Mock enrichment logic
            result = {"status": "enriched", "data": f"mock_data_for_{ioc}"}

            pg_cur.execute(
                "UPDATE enrichment_jobs SET status = 'COMPLETED', result = %s WHERE id = %s",
                (json.dumps(result), job_id)
            )
            update_quota(sq_conn, provider, cost)
            quota_cache[provider] = quota - cost
            pg_conn.commit()
        except Exception as e:
            pg_conn.rollback()
            raise RuntimeError("Failed to process enrichment job") from e

def main() -> None:
    """Parses command line arguments and initiates the job processing workflow."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-dsn", required=True, help="PostgreSQL DSN")
    parser.add_argument(
        "--sqlite-path",
        default=":memory:",
        help="Path to SQLite DB file; defaults to in‑memory DB for testing"
    )
    args = parser.parse_args()

    pg_conn, sq_conn = get_db_connections(args.pg_dsn, args.sqlite_path)

    try:
        process_jobs(pg_conn, sq_conn)
    finally:
        pg_conn.close()
        sq_conn.close()

if __name__ == "__main__":
    main()
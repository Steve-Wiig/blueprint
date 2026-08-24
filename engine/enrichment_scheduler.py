"""Enrichment Scheduler Module

This module provides reusable functions for processing enrichment jobs from PostgreSQL
using quota tracking in SQLite. It can be imported as a library or executed as a script.

Public API (safe to import and use):
    - get_db_connections: Establish PostgreSQL and SQLite connections
    - check_quota: Check remaining quota for a provider (deprecated)
    - get_provider_cost: Get cost per enrichment for a provider (deprecated)
    - update_quota: Decrement quota for a provider
    - process_jobs: Process pending enrichment jobs in batches
    - sanitize: Redact sensitive fields from enrichment results

Script-only entrypoint:
    - main: Command-line entry point (guarded by if __name__ == "__main__")

Usage as script:
    python enrichment_scheduler.py --pg-dsn "postgresql://..." [--sqlite-path ":memory:"]

Usage as library:
    from enrichment_scheduler import get_db_connections, process_jobs
    pg_conn, sq_conn = get_db_connections(pg_dsn, sqlite_path)
    process_jobs(pg_conn, sq_conn)
"""

import argparse
import json
import sqlite3
import warnings
import psycopg2
from datetime import datetime, timezone
from typing import Tuple, Dict, List, Optional, Any


def sanitize(data: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively sanitize a dictionary by redacting sensitive fields.

    Args:
        data: The dictionary to sanitize.

    Returns:
        A new dictionary with sensitive values redacted.
    """
    sensitive_patterns = [
        'secret', 'token', 'password', 'key', 'api_key', 'apikey',
        'access_token', 'refresh_token', 'client_secret', 'private_key'
    ]

    def _sanitize(obj: Any) -> Any:
        if isinstance(obj, dict):
            result = {}
            for k, v in obj.items():
                if any(pattern in k.lower() for pattern in sensitive_patterns):
                    result[k] = "***REDACTED***"
                else:
                    result[k] = _sanitize(v)
            return result
        elif isinstance(obj, list):
            return [_sanitize(item) for item in obj]
        else:
            return obj

    return _sanitize(data)


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


def check_quota(
    sq_conn: sqlite3.Connection,
    provider: str,
    cache: Optional[Dict[str, int]] = None
) -> int:
    """Checks the remaining quota for a specific provider.

    If a cache dictionary is supplied and contains the provider, the cached value is returned
    to avoid an extra database query.

    .. deprecated:: 1.0
        Use `_fetch_provider_data` for bulk quota checks instead.

    Args:
        sq_conn: The SQLite database connection.
        provider: The name of the enrichment provider.
        cache: Optional dict mapping providers to their remaining quota.

    Returns:
        The remaining quota as an integer.
    """
    warnings.warn(
        "check_quota is deprecated and will be removed in a future version. "
        "Use _fetch_provider_data for bulk quota checks.",
        DeprecationWarning,
        stacklevel=2
    )
    if cache is not None and provider in cache:
        return cache[provider]

    cursor = sq_conn.cursor()
    cursor.execute(
        "SELECT remaining FROM quota_ledger WHERE provider = ?",
        (provider,)
    )
    row = cursor.fetchone()
    return row[0] if row else 0


def get_provider_cost(
    sq_conn: sqlite3.Connection,
    provider: str,
    cache: Optional[Dict[str, int]] = None
) -> int:
    """Retrieves the cost per enrichment for a provider.

    If a cache dictionary is supplied and contains the provider, the cached value is returned
    to avoid an extra database query.

    .. deprecated:: 1.0
        Use `_fetch_provider_data` for bulk cost checks instead.

    Args:
        sq_conn: The SQLite database connection.
        provider: The name of the enrichment provider.
        cache: Optional dict mapping providers to their cost.

    Returns:
        The cost as an integer. Defaults to 1 if not specified.
    """
    warnings.warn(
        "get_provider_cost is deprecated and will be removed in a future version. "
        "Use _fetch_provider_data for bulk cost checks.",
        DeprecationWarning,
        stacklevel=2
    )
    if cache is not None and provider in cache:
        return cache[provider]

    cursor = sq_conn.cursor()
    cursor.execute(
        "SELECT cost FROM provider_costs WHERE provider = ?",
        (provider,)
    )
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


def _fetch_provider_data(
    sq_conn: sqlite3.Connection,
    providers: List[str]
) -> Tuple[Dict[str, int], Dict[str, int]]:
    """Fetches quota and cost for multiple providers in bulk using a single JOIN query.

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

    cursor.execute(
        f"""
        SELECT q.provider, q.remaining, c.cost
        FROM quota_ledger q
        LEFT JOIN provider_costs c ON q.provider = c.provider
        WHERE q.provider IN ({placeholders})
        """,
        providers
    )
    quota_dict: Dict[str, int] = {}
    cost_dict: Dict[str, int] = {}
    for row in cursor.fetchall():
        provider, remaining, cost = row
        quota_dict[provider] = remaining
        cost_dict[provider] = cost if cost is not None else 1

    return quota_dict, cost_dict


def process_jobs(
    pg_conn: psycopg2.extensions.connection,
    sq_conn: sqlite3.Connection
) -> None:
    """Fetches pending enrichment jobs in batches and processes them if quota is available.

    Args:
        pg_conn: The PostgreSQL database connection.
        sq_conn: The SQLite database connection.
    """
    BATCH_SIZE = 1000
    last_id = 0
    quota_cache: Dict[str, int] = {}
    cost_cache: Dict[str, int] = {}

    while True:
        pg_cur = pg_conn.cursor()
        pg_cur.execute(
            "SELECT id, ioc_value, provider FROM enrichment_jobs WHERE status = 'PENDING' AND id > %s ORDER BY id LIMIT %s",
            (last_id, BATCH_SIZE)
        )
        jobs = pg_cur.fetchall()
        if not jobs:
            break

        # Collect unique providers in this batch that are not yet cached
        providers_in_batch = {provider for _, _, provider in jobs}
        providers_needed = [p for p in providers_in_batch if p not in quota_cache]
        if providers_needed:
            quota_dict, cost_dict = _fetch_provider_data(sq_conn, providers_needed)
            quota_cache.update(quota_dict)
            cost_cache.update(cost_dict)

        for job_id, ioc, provider in jobs:
            last_id = job_id  # advance pagination marker
            quota = quota_cache.get(provider, 0)
            cost = cost_cache.get(provider, 1)

            if quota < cost:
                continue  # Not enough quota; skip this job.

            try:
                # Mock enrichment logic
                result = {"status": "enriched", "data": f"mock_data_for_{ioc}"}
                sanitized_result = sanitize(result)
                result_json = json.dumps(sanitized_result)
                processed_at = datetime.now(timezone.utc)

                # Append-only audit log before updating job status
                pg_cur.execute(
                    "INSERT INTO enrichment_audit_log (job_id, status, result, processed_at) VALUES (%s, %s, %s, %s)",
                    (job_id, 'COMPLETED', result_json, processed_at)
                )
                pg_cur.execute(
                    "UPDATE enrichment_jobs SET status = 'COMPLETED', result = %s WHERE id = %s",
                    (result_json, job_id)
                )
                update_quota(sq_conn, provider, cost)

                # Update in‑memory cache to reflect the consumed quota.
                quota_cache[provider] = quota - cost

                pg_conn.commit()
            except Exception as e:
                pg_conn.rollback()
                raise RuntimeError("Failed to process enrichment job") from e

    sq_conn.commit()


def main() -> None:
    """Parses command line arguments and initiates the job processing workflow.

    This function is the entry point when the module is executed as a script.
    It is not intended to be called when importing this module as a library.
    """
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
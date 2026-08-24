"""
Enrichment job processor.

This module is designed to be executed as a standalone script, not imported as a library.
The public API is restricted to the `main` function via __all__.
"""

import argparse
import hashlib
import json
import logging
import sqlite3
import warnings
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Tuple, Dict, List, Optional, Any

import psycopg2


logger = logging.getLogger(__name__)

__all__ = ['main']


class JobStatus(str, Enum):
    """Enumeration of possible job statuses."""
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class EnrichmentProvider(ABC):
    """Abstract base class for enrichment providers.

    Implementations must provide a `process` method that takes an IOC value
    and returns a dictionary with enrichment results.
    """

    @abstractmethod
    def process(self, ioc: str) -> Dict[str, Any]:
        """Process an IOC and return enrichment data.

        Args:
            ioc: The indicator of compromise to enrich.

        Returns:
            A dictionary containing enrichment results.
        """
        pass


class MockEnrichmentProvider(EnrichmentProvider):
    """Default mock enrichment provider for testing and development."""

    def process(self, ioc: str) -> Dict[str, Any]:
        """Return mock enrichment data for the given IOC."""
        return {"status": "enriched", "data": f"mock_data_for_{ioc}"}


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
        logger.exception("Connection error")
        raise RuntimeError("Failed to establish database connections") from e


def _fetch_provider_values(
    sq_conn: sqlite3.Connection,
    providers: List[str],
    table: str,
    column: str,
    cursor: Optional[sqlite3.Cursor] = None
) -> Dict[str, int]:
    """Fetch provider-value pairs from a table for the given providers.

    Args:
        sq_conn: The SQLite database connection.
        providers: List of provider names.
        table: The table to query.
        column: The column to retrieve.
        cursor: Optional cursor to reuse. If not provided, a new one is created.

    Returns:
        A dictionary mapping provider to the column value.
    """
    if not providers:
        return {}
    placeholders = ','.join(['?'] * len(providers))
    own_cursor = False
    if cursor is None:
        cursor = sq_conn.cursor()
        own_cursor = True
    try:
        cursor.execute(
            f"SELECT provider, {column} FROM {table} WHERE provider IN ({placeholders})",
            providers
        )
        return {row[0]: row[1] for row in cursor.fetchall()}
    finally:
        if own_cursor:
            cursor.close()


def check_quota(
    sq_conn: sqlite3.Connection,
    provider: str,
    cache: Optional[Dict[str, int]] = None,
    cursor: Optional[sqlite3.Cursor] = None
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
        cursor: Optional cursor to reuse.

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

    quota_dict = _fetch_provider_values(sq_conn, [provider], 'quota_ledger', 'remaining', cursor)
    return quota_dict.get(provider, 0)


def get_provider_cost(
    sq_conn: sqlite3.Connection,
    provider: str,
    cache: Optional[Dict[str, int]] = None,
    cursor: Optional[sqlite3.Cursor] = None
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
        cursor: Optional cursor to reuse.

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

    cost_dict = _fetch_provider_values(sq_conn, [provider], 'provider_costs', 'cost', cursor)
    return cost_dict.get(provider, 1)


def update_quota(
    sq_conn: sqlite3.Connection,
    provider: str,
    cost: int,
    cursor: Optional[sqlite3.Cursor] = None
) -> None:
    """Decrements the quota for a specific provider in the SQLite database.

    Args:
        sq_conn: The SQLite database connection.
        provider: The name of the enrichment provider.
        cost: The amount to decrement from the quota.
        cursor: Optional cursor to reuse.
    """
    own_cursor = False
    if cursor is None:
        cursor = sq_conn.cursor()
        own_cursor = True
    try:
        cursor.execute(
            "UPDATE quota_ledger SET remaining = remaining - ? WHERE provider = ?",
            (cost, provider)
        )
    finally:
        if own_cursor:
            cursor.close()


def _fetch_provider_data(
    sq_conn: sqlite3.Connection,
    providers: List[str],
    cursor: Optional[sqlite3.Cursor] = None
) -> Tuple[Dict[str, int], Dict[str, int]]:
    """Fetches quota and cost for multiple providers in bulk.

    Args:
        sq_conn: The SQLite database connection.
        providers: List of provider names.
        cursor: Optional cursor to reuse.

    Returns:
        Tuple of (quota_dict, cost_dict) keyed by provider.
    """
    if not providers:
        return {}, {}

    quota_dict = _fetch_provider_values(sq_conn, providers, 'quota_ledger', 'remaining', cursor)
    cost_dict = _fetch_provider_values(sq_conn, providers, 'provider_costs', 'cost', cursor)

    # Ensure cost_dict has entries for all providers in quota_dict, defaulting to 1
    for provider in quota_dict:
        if provider not in cost_dict:
            cost_dict[provider] = 1

    # Return only providers that have quota (i.e., are in quota_dict)
    filtered_cost_dict = {p: cost_dict[p] for p in quota_dict}
    return quota_dict, filtered_cost_dict


def process_jobs(
    pg_conn: psycopg2.extensions.connection,
    sq_conn: sqlite3.Connection,
    provider: Optional[EnrichmentProvider] = None
) -> None:
    """Fetches pending enrichment jobs in batches and processes them if quota is available.

    Each job attempt (success or failure) is recorded in an append-only audit log with
    job_id, provider, ioc_hash, quota_cost, status, timestamp, and error_message.

    Args:
        pg_conn: The PostgreSQL database connection.
        sq_conn: The SQLite database connection.
        provider: An optional EnrichmentProvider instance. Defaults to MockEnrichmentProvider.
    """
    if provider is None:
        provider = MockEnrichmentProvider()

    BATCH_SIZE = 1000
    last_id = 0
    quota_cache: Dict[str, int] = {}
    cost_cache: Dict[str, int] = {}

    # Create a single SQLite cursor for reuse within this function
    sq_cur = sq_conn.cursor()
    try:
        while True:
            pg_cur = pg_conn.cursor()
            pg_cur.execute(
                "SELECT id, ioc_value, provider FROM enrichment_jobs WHERE status = %s AND id > %s ORDER BY id LIMIT %s",
                (JobStatus.PENDING.value, last_id, BATCH_SIZE)
            )
            jobs = pg_cur.fetchall()
            if not jobs:
                break

            # Collect unique providers in this batch that are not yet cached
            providers_in_batch = {provider_name for _, _, provider_name in jobs}
            providers_needed = [p for p in providers_in_batch if p not in quota_cache]
            if providers_needed:
                quota_dict, cost_dict = _fetch_provider_data(sq_conn, providers_needed, sq_cur)
                quota_cache.update(quota_dict)
                cost_cache.update(cost_dict)

            for job_id, ioc, provider_name in jobs:
                last_id = job_id  # advance pagination marker
                quota = quota_cache.get(provider_name, 0)
                cost = cost_cache.get(provider_name, 1)

                # Compute IOC hash for audit trail
                ioc_hash = hashlib.sha256(ioc.encode()).hexdigest()
                processed_at = datetime.now(timezone.utc)
                error_message = None
                status = JobStatus.FAILED.value
                result_json = None

                try:
                    if quota < cost:
                        error_message = "Insufficient quota"
                        # Append-only audit log for quota exhaustion
                        pg_cur.execute(
                            "INSERT INTO enrichment_audit_log (job_id, provider, ioc_hash, quota_cost, status, timestamp, error_message) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                            (job_id, provider_name, ioc_hash, cost, JobStatus.FAILED.value, processed_at, error_message)
                        )
                        pg_cur.execute(
                            "UPDATE enrichment_jobs SET status = %s WHERE id = %s",
                            (JobStatus.FAILED.value, job_id)
                        )
                        pg_conn.commit()
                        sq_conn.commit()
                        continue

                    # Use injected enrichment provider
                    result = provider.process(ioc)
                    sanitized_result = sanitize(result)
                    result_json = json.dumps(sanitized_result)
                    status = JobStatus.COMPLETED.value

                    # Append-only audit log for successful completion
                    pg_cur.execute(
                        "INSERT INTO enrichment_audit_log (job_id, provider, ioc_hash, quota_cost, status, timestamp, error_message, result) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        (job_id, provider_name, ioc_hash, cost, status, processed_at, error_message, result_json)
                    )
                    pg_cur.execute(
                        "UPDATE enrichment_jobs SET status = %s, result = %s WHERE id = %s",
                        (status, result_json, job_id)
                    )
                    update_quota(sq_conn, provider_name, cost, sq_cur)

                    # Update in‑memory cache to reflect the consumed quota.
                    quota_cache[provider_name] = quota - cost

                except Exception as e:
                    error_message = str(e)
                    status = JobStatus.FAILED.value
                    # Append-only audit log for processing failure
                    pg_cur.execute(
                        "INSERT INTO enrichment_audit_log (job_id, provider, ioc_hash, quota_cost, status, timestamp, error_message) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                        (job_id, provider_name, ioc_hash, cost, status, processed_at, error_message)
                    )
                    pg_cur.execute(
                        "UPDATE enrichment_jobs SET status = %s WHERE id = %s",
                        (status, job_id)
                    )

                # Commit each job's audit record and status update immediately for durability
                pg_conn.commit()
                sq_conn.commit()

    finally:
        sq_cur.close()


def main() -> None:
    """Parses command line arguments and initiates the job processing workflow.

    This function is the entry point when the module is executed as a script.
    It is not intended to be called when imported as a library.
    """
    parser = argparse.ArgumentParser(description="Process enrichment jobs.")
    parser.add_argument("--pg-dsn", required=True, help="PostgreSQL DSN")
    parser.add_argument("--sqlite-path", default=":memory:", help="SQLite database path")
    args = parser.parse_args()

    pg_conn, sq_conn = get_db_connections(args.pg_dsn, args.sqlite_path)
    try:
        process_jobs(pg_conn, sq_conn)
    finally:
        pg_conn.close()
        sq_conn.close()


if __name__ == "__main__":
    main()
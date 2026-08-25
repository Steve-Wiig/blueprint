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


class ProviderNotConfiguredError(RuntimeError):
    """Raised when an enrichment provider is not configured in the quota ledger."""
    pass


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


def _fetch_job_batch(
    pg_conn: psycopg2.extensions.connection,
    last_id: int,
    batch_size: int
) -> List[Tuple[int, str, str]]:
    """Fetch a batch of pending enrichment jobs.

    Args:
        pg_conn: The PostgreSQL database connection.
        last_id: The last processed job ID for pagination.
        batch_size: Maximum number of jobs to fetch.

    Returns:
        List of tuples (job_id, ioc_value, provider_name).
    """
    pg_cur = pg_conn.cursor()
    pg_cur.execute(
        "SELECT id, ioc_value, provider FROM enrichment_jobs WHERE status = %s AND id > %s ORDER BY id LIMIT %s",
        (JobStatus.PENDING.value, last_id, batch_size)
    )
    return pg_cur.fetchall()


def _check_batch_quota(
    sq_conn: sqlite3.Connection,
    sq_cur: sqlite3.Cursor,
    providers_in_batch: set,
    quota_cache: Dict[str, int],
    cost_cache: Dict[str, int]
) -> None:
    """Check and cache quota for providers in the current batch.

    Args:
        sq_conn: The SQLite database connection.
        sq_cur: Reusable SQLite cursor.
        providers_in_batch: Set of provider names in the current batch.
        quota_cache: Cache dictionary for quota values.
        cost_cache: Cache dictionary for cost values.

    Raises:
        ProviderNotConfiguredError: If any provider is not configured in quota_ledger.
    """
    providers_needed = [p for p in providers_in_batch if p not in quota_cache]
    if providers_needed:
        quota_dict, cost_dict = _fetch_provider_data(sq_conn, providers_needed, sq_cur)
        quota_cache.update(quota_dict)
        cost_cache.update(cost_dict)

    for provider_name in providers_in_batch:
        if provider_name not in quota_cache:
            raise ProviderNotConfiguredError(
                f"Provider '{provider_name}' not configured in quota_ledger. "
                "Add the provider to quota_ledger before processing jobs."
            )


def _process_single_job(
    provider: EnrichmentProvider,
    ioc: str,
    provider_name: str,
    quota: int,
    cost: int
) -> Tuple[str, Optional[str], Optional[Dict[str, Any]]]:
    """Process a single enrichment job.

    Args:
        provider: The enrichment provider instance.
        ioc: The indicator of compromise to enrich.
        provider_name: Name of the provider.
        quota: Available quota for the provider.
        cost: Cost per enrichment for the provider.

    Returns:
        Tuple of (status, error_message, result_json).
    """
    if quota < cost:
        return JobStatus.FAILED.value, "Insufficient quota", None

    try:
        result = provider.process(ioc)
        result_json = json.dumps(sanitize(result))
        return JobStatus.COMPLETED.value, None, result_json
    except Exception as e:
        logger.exception("Enrichment failed for job")
        return JobStatus.FAILED.value, str(e), None


def _write_audit_log(
    pg_cur: psycopg2.extensions.cursor,
    job_id: int,
    provider_name: str,
    ioc_hash: str,
    quota_cost: int,
    status: str,
    processed_at: datetime,
    error_message: Optional[str]
) -> None:
    """Write an audit log entry for a job attempt.

    Args:
        pg_cur: PostgreSQL cursor.
        job_id: The job ID.
        provider_name: Name of the enrichment provider.
        ioc_hash: SHA256 hash of the IOC.
        quota_cost: Quota cost for this job.
        status: Job status (COMPLETED or FAILED).
        processed_at: Timestamp of processing.
        error_message: Error message if failed, None otherwise.
    """
    pg_cur.execute(
        "INSERT INTO enrichment_audit_log (job_id, provider, ioc_hash, quota_cost, status, timestamp, error_message) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (job_id, provider_name, ioc_hash, quota_cost, status, processed_at, error_message)
    )


def _update_job_status(
    pg_cur: psycopg2.extensions.cursor,
    job_id: int,
    status: str,
    result_json: Optional[str]
) -> None:
    """Update the job status in the database.

    Args:
        pg_cur: PostgreSQL cursor.
        job_id: The job ID.
        status: New job status.
        result_json: Enrichment result JSON if completed, None otherwise.
    """
    if result_json is not None:
        pg_cur.execute(
            "UPDATE enrichment_jobs SET status = %s, result = %s WHERE id = %s",
            (status, result_json, job_id)
        )
    else:
        pg_cur.execute(
            "UPDATE enrichment_jobs SET status = %s WHERE id = %s",
            (status, job_id)
        )


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

    sq_cur = sq_conn.cursor()
    try:
        while True:
            jobs = _fetch_job_batch(pg_conn, last_id, BATCH_SIZE)
            if not jobs:
                break

            providers_in_batch = {provider_name for _, _, provider_name in jobs}
            _check_batch_quota(sq_conn, sq_cur, providers_in_batch, quota_cache, cost_cache)

            pg_cur = pg_conn.cursor()
            try:
                for job_id, ioc, provider_name in jobs:
                    last_id = job_id
                    quota = quota_cache.get(provider_name, 0)
                    cost = cost_cache.get(provider_name, 1)

                    ioc_hash = hashlib.sha256(ioc.encode()).hexdigest()
                    processed_at = datetime.now(timezone.utc)

                    status, error_message, result_json = _process_single_job(
                        provider, ioc, provider_name, quota, cost
                    )

                    _write_audit_log(
                        pg_cur, job_id, provider_name, ioc_hash, cost,
                        status, processed_at, error_message
                    )

                    _update_job_status(pg_cur, job_id, status, result_json)

                    if status == JobStatus.COMPLETED.value:
                        update_quota(sq_conn, provider_name, cost, sq_cur)
                        quota_cache[provider_name] = quota - cost

                pg_conn.commit()
            except Exception:
                pg_conn.rollback()
                raise
            finally:
                pg_cur.close()
    finally:
        sq_cur.close()


def main() -> None:
    """Main entry point for the enrichment job processor."""
    parser = argparse.ArgumentParser(description="Process enrichment jobs")
    parser.add_argument("--pg-dsn", required=True, help="PostgreSQL DSN")
    parser.add_argument("--sqlite-path", required=True, help="SQLite database path")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    args = parser.parse_args()

    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    pg_conn, sq_conn = get_db_connections(args.pg_dsn, args.sqlite_path)
    try:
        process_jobs(pg_conn, sq_conn)
    finally:
        pg_conn.close()
        sq_conn.close()


if __name__ == "__main__":
    main()
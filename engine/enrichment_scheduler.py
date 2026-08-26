import argparse
import hashlib
import json
import logging
import signal
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

    Raises:
        ValueError: If the provider has insufficient quota or is not found.
    """
    own_cursor = False
    if cursor is None:
        cursor = sq_conn.cursor()
        own_cursor = True
    try:
        cursor.execute(
            "UPDATE quota_ledger SET remaining = remaining - ? WHERE provider = ? AND remaining >= ?",
            (cost, provider, cost)
        )
        if cursor.rowcount == 0:
            cursor.execute("SELECT remaining FROM quota_ledger WHERE provider = ?", (provider,))
            row = cursor.fetchone()
            if row is None:
                raise ValueError(f"Provider '{provider}' not found in quota_ledger")
            else:
                raise ValueError(f"Insufficient quota for provider '{provider}': {row[0]} remaining, {cost} required")
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
    cost_cache: Dict[str, int],
    cache_timestamps: Optional[Dict[str, datetime]] = None,
    cache_ttl_seconds: int = 300
) -> None:
    """Check and cache quota for providers in the current batch.

    Args:
        sq_conn: The SQLite database connection.
        sq_cur: Reusable SQLite cursor.
        providers_in_batch: Set of provider names in the current batch.
        quota_cache: Cache dictionary for quota values.
        cost_cache: Cache dictionary for cost values.
        cache_timestamps: Optional dict mapping providers to when they were cached.
        cache_ttl_seconds: Time-to-live for cache entries in seconds (default 300).

    Raises:
        ProviderNotConfiguredError: If any provider is not configured in quota_ledger.
    """
    now = datetime.now(timezone.utc)
    
    # Determine which providers need fetching: missing from cache or stale
    providers_needed = []
    for provider in providers_in_batch:
        if provider not in quota_cache:
            providers_needed.append(provider)
        elif cache_timestamps is not None and provider in cache_timestamps:
            age = (now - cache_timestamps[provider]).total_seconds()
            if age > cache_ttl_seconds:
                providers_needed.append(provider)
    
    if providers_needed:
        quota_dict, cost_dict = _fetch_provider_data(sq_conn, providers_needed, sq_cur)
        quota_cache.update(quota_dict)
        cost_cache.update(cost_dict)
        if cache_timestamps is not None:
            for provider in providers_needed:
                cache_timestamps[provider] = now

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
        provider_name: Name of the provider for logging.
        quota: Current remaining quota for the provider.
        cost: Cost per enrichment for the provider.

    Returns:
        Tuple of (status, error_message, enrichment_data).
    """
    if quota < cost:
        return JobStatus.FAILED.value, f"Insufficient quota: {quota} remaining, {cost} required", None

    try:
        result = provider.process(ioc)
        return JobStatus.COMPLETED.value, None, result
    except Exception as e:
        logger.exception("Error processing job for provider %s, IOC %s", provider_name, ioc)
        return JobStatus.FAILED.value, str(e), None


def _audit_log(
    sq_conn: sqlite3.Connection,
    job_id: int,
    old_status: str,
    new_status: str,
    provider: str,
    ioc: str,
    error: Optional[str] = None,
    enrichment_data: Optional[Dict[str, Any]] = None,
    cursor: Optional[sqlite3.Cursor] = None
) -> None:
    """Append-only audit log for job status changes.

    Args:
        sq_conn: The SQLite database connection.
        job_id: The enrichment job ID.
        old_status: Previous job status.
        new_status: New job status.
        provider: Provider name.
        ioc: IOC value.
        error: Optional error message if failed.
        enrichment_data: Optional enrichment result data.
        cursor: Optional cursor to reuse.
    """
    own_cursor = False
    if cursor is None:
        cursor = sq_conn.cursor()
        own_cursor = True
    try:
        cursor.execute(
            """INSERT INTO enrichment_audit_log 
               (job_id, old_status, new_status, provider, ioc, error, enrichment_data, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id,
                old_status,
                new_status,
                provider,
                ioc,
                error,
                json.dumps(sanitize(enrichment_data)) if enrichment_data else None,
                datetime.now(timezone.utc).isoformat()
            )
        )
    finally:
        if own_cursor:
            cursor.close()


def _approval_gate_check(
    pg_conn: psycopg2.extensions.connection,
    job_id: int,
    provider: str,
    ioc: str,
    enrichment_data: Dict[str, Any]
) -> bool:
    """Approval gate stub for mutations - checks if job requires manual approval.

    Args:
        pg_conn: The PostgreSQL database connection.
        job_id: The enrichment job ID.
        provider: Provider name.
        ioc: IOC value.
        enrichment_data: Enrichment result data.

    Returns:
        True if approved (or no approval needed), False if requires manual review.
    """
    # Stub implementation - in production, this would check approval policies
    # e.g., high-risk IOCs, new providers, sensitive data patterns
    pg_cur = pg_conn.cursor()
    pg_cur.execute(
        "SELECT requires_approval FROM approval_policies WHERE provider = %s",
        (provider,)
    )
    row = pg_cur.fetchone()
    if row and row[0]:
        logger.info("Job %d requires manual approval for provider %s", job_id, provider)
        return False
    return True


def _update_job_status(
    pg_conn: psycopg2.extensions.connection,
    job_id: int,
    status: str,
    error: Optional[str] = None,
    enrichment_data: Optional[Dict[str, Any]] = None,
    cursor: Optional[psycopg2.extensions.cursor] = None
) -> None:
    """Update job status in PostgreSQL.

    Args:
        pg_conn: The PostgreSQL database connection.
        job_id: The enrichment job ID.
        status: New status value.
        error: Optional error message.
        enrichment_data: Optional enrichment result data.
        cursor: Optional cursor to reuse.
    """
    own_cursor = False
    if cursor is None:
        cursor = pg_conn.cursor()
        own_cursor = True
    try:
        if enrichment_data is not None:
            cursor.execute(
                "UPDATE enrichment_jobs SET status = %s, error = %s, enrichment_data = %s, updated_at = %s WHERE id = %s",
                (status, error, json.dumps(sanitize(enrichment_data)), datetime.now(timezone.utc), job_id)
            )
        else:
            cursor.execute(
                "UPDATE enrichment_jobs SET status = %s, error = %s, updated_at = %s WHERE id = %s",
                (status, error, datetime.now(timezone.utc), job_id)
            )
    finally:
        if own_cursor:
            cursor.close()


def process_jobs(
    pg_conn: psycopg2.extensions.connection,
    sq_conn: sqlite3.Connection,
    provider: EnrichmentProvider,
    batch_size: int = 100,
    max_jobs: Optional[int] = None,
    cache_ttl_seconds: int = 300
) -> int:
    """Process pending enrichment jobs in batches.

    Args:
        pg_conn: PostgreSQL connection.
        sq_conn: SQLite connection.
        provider: Enrichment provider instance.
        batch_size: Number of jobs to fetch per batch.
        max_jobs: Maximum total jobs to process (None for unlimited).
        cache_ttl_seconds: Cache TTL for quota/cost lookups.

    Returns:
        Number of jobs processed.
    """
    last_id = 0
    total_processed = 0
    quota_cache: Dict[str, int] = {}
    cost_cache: Dict[str, int] = {}
    cache_timestamps: Dict[str, datetime] = {}

    sq_cur = sq_conn.cursor()
    pg_cur = pg_conn.cursor()

    try:
        while True:
            if max_jobs is not None and total_processed >= max_jobs:
                break

            jobs = _fetch_job_batch(pg_conn, last_id, batch_size)
            if not jobs:
                break

            providers_in_batch = {job[2] for job in jobs}
            _check_batch_quota(
                sq_conn, sq_cur, providers_in_batch,
                quota_cache, cost_cache, cache_timestamps, cache_ttl_seconds
            )

            for job_id, ioc, provider_name in jobs:
                if max_jobs is not None and total_processed >= max_jobs:
                    break

                quota = quota_cache.get(provider_name, 0)
                cost = cost_cache.get(provider_name, 1)

                old_status = JobStatus.PENDING.value
                new_status, error, enrichment_data = _process_single_job(
                    provider, ioc, provider_name, quota, cost
                )

                # Approval gate for completed jobs
                if new_status == JobStatus.COMPLETED.value and enrichment_data:
                    if not _approval_gate_check(pg_conn, job_id, provider_name, ioc, enrichment_data):
                        new_status = JobStatus.PENDING.value
                        error = "Pending manual approval"
                        enrichment_data = None

                # Update quota if successful
                if new_status == JobStatus.COMPLETED.value:
                    try:
                        update_quota(sq_conn, provider_name, cost, sq_cur)
                        quota_cache[provider_name] -= cost
                    except ValueError as e:
                        new_status = JobStatus.FAILED.value
                        error = str(e)
                        enrichment_data = None

                # Update job status in PostgreSQL
                _update_job_status(pg_conn, job_id, new_status, error, enrichment_data, pg_cur)

                # Audit log
                _audit_log(
                    sq_conn, job_id, old_status, new_status,
                    provider_name, ioc, error, enrichment_data, sq_cur
                )

                total_processed += 1
                last_id = job_id

            pg_conn.commit()
            sq_conn.commit()

    except Exception:
        pg_conn.rollback()
        sq_conn.rollback()
        raise
    finally:
        sq_cur.close()
        pg_cur.close()

    return total_processed


def setup_signal_handlers() -> None:
    """Set up signal handlers for graceful shutdown."""
    def signal_handler(signum: int, frame: Any) -> None:
        logger.info("Received signal %d, shutting down gracefully", signum)
        raise KeyboardInterrupt()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)


def main() -> int:
    """Main entry point for the enrichment worker.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    parser = argparse.ArgumentParser(description="IOC Enrichment Worker")
    parser.add_argument("--pg-dsn", required=True, help="PostgreSQL DSN")
    parser.add_argument("--sqlite-path", default=":memory:", help="SQLite database path")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size for job processing")
    parser.add_argument("--max-jobs", type=int, help="Maximum jobs to process")
    parser.add_argument("--cache-ttl", type=int, default=300, help="Cache TTL in seconds")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    setup_signal_handlers()

    try:
        pg_conn, sq_conn = get_db_connections(args.pg_dsn, args.sqlite_path)
    except RuntimeError as e:
        logger.error("Failed to connect to databases: %s", e)
        return 1

    provider = MockEnrichmentProvider()

    try:
        processed = process_jobs(
            pg_conn, sq_conn, provider,
            batch_size=args.batch_size,
            max_jobs=args.max_jobs,
            cache_ttl_seconds=args.cache_ttl
        )
        logger.info("Processed %d jobs", processed)
        return 0
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 130
    except Exception as e:
        logger.exception("Unexpected error")
        return 1
    finally:
        pg_conn.close()
        sq_conn.close()


if __name__ == "__main__":
    exit(main())
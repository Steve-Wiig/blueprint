import argparse
import hashlib
import json
import logging
import signal
import sqlite3
import time
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from functools import wraps
from typing import Tuple, Dict, List, Optional, Any, Callable

import psycopg2


logger = logging.getLogger(__name__)


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


def sanitize(data: Dict[str, Any], sensitive_patterns: Optional[List] = None) -> Dict[str, Any]:
    """Recursively sanitize a dictionary by redacting sensitive fields.

    Args:
        data: The dictionary to sanitize.
        sensitive_patterns: List of substring patterns or compiled regex objects
            to detect sensitive keys. If None, uses default organizational patterns.

    Returns:
        A new dictionary with sensitive values redacted.
    """
    if sensitive_patterns is None:
        sensitive_patterns = [
            'secret', 'token', 'password', 'key', 'api_key', 'apikey',
            'access_token', 'refresh_token', 'client_secret', 'private_key'
        ]

    def _is_sensitive(key: str) -> bool:
        for pat in sensitive_patterns:
            if isinstance(pat, re.Pattern):
                if pat.search(key):
                    return True
            else:
                if pat in key.lower():
                    return True
        return False

    def _sanitize(obj: Any) -> Any:
        if isinstance(obj, dict):
            result = {}
            for k, v in obj.items():
                if _is_sensitive(k):
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

    Note: This function must NOT be called at module level as it would create
    database connections on import, violating the no-module-level-side-effects rule.
    It should only be called inside main() or an explicit initialization function.

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
    cursor: sqlite3.Cursor
) -> Dict[str, int]:
    """Fetch provider-value pairs from a table for the given providers.

    Args:
        sq_conn: The SQLite database connection.
        providers: List of provider names.
        table: The table to query.
        column: The column to retrieve.
        cursor: Reusable cursor to execute the query. Caller must manage cursor lifecycle.

    Returns:
        A dictionary mapping provider to the column value.
    """
    if not providers:
        return {}
    placeholders = ','.join(['?'] * len(providers))
    cursor.execute(
        f"SELECT provider, {column} FROM {table} WHERE provider IN ({placeholders})",
        providers
    )
    return {row[0]: row[1] for row in cursor.fetchall()}


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


_quota_cache: Dict[str, Tuple[Dict[str, int], Dict[str, int], float]] = {}
_CACHE_TTL_SECONDS = 60


def _fetch_provider_data(
    sq_conn: sqlite3.Connection,
    providers: List[str],
    cursor: sqlite3.Cursor
) -> Tuple[Dict[str, int], Dict[str, int]]:
    """Fetches quota and cost for multiple providers in bulk.

    Args:
        sq_conn: The SQLite database connection.
        providers: List of provider names.
        cursor: Reusable cursor to execute queries. Caller must manage cursor lifecycle.

    Returns:
        Tuple of (quota_dict, cost_dict) keyed by provider.
    """
    if not providers:
        return {}, {}

    cache_key = tuple(sorted(providers))
    now = time.time()
    if cache_key in _quota_cache:
        quota_dict, cost_dict, cached_at = _quota_cache[cache_key]
        if now - cached_at < _CACHE_TTL_SECONDS:
            return quota_dict, cost_dict

    quota_dict = _fetch_provider_values(sq_conn, providers, 'quota_ledger', 'remaining', cursor)
    cost_dict = _fetch_provider_values(sq_conn, providers, 'provider_costs', 'cost', cursor)

    _quota_cache[cache_key] = (quota_dict, cost_dict, now)
    return quota_dict, cost_dict


def _check_batch_quota(
    sq_conn: sqlite3.Connection,
    providers_in_batch: List[str],
    providers_needed: List[str],
    cursor: sqlite3.Cursor
) -> None:
    """Validates that all providers in the batch have sufficient quota.

    Merges quota/cost fetch and validation into a single pass to avoid
    redundant iteration and N+1 query patterns.

    Args:
        sq_conn: The SQLite database connection.
        providers_in_batch: All providers referenced in the batch.
        providers_needed: Subset of providers that actually need quota checked.
        cursor: Reusable cursor to execute queries. Caller must manage cursor lifecycle.

    Raises:
        ProviderNotConfiguredError: If a provider is not in quota_ledger.
        ValueError: If a provider has insufficient quota.
    """
    if not providers_in_batch:
        return

    quota_dict, cost_dict = _fetch_provider_data(sq_conn, providers_in_batch, cursor)

    for provider in providers_in_batch:
        if provider not in quota_dict:
            raise ProviderNotConfiguredError(f"Provider '{provider}' not configured in quota_ledger")

        if provider in providers_needed:
            cost = cost_dict.get(provider, 0)
            remaining = quota_dict[provider]
            if remaining < cost:
                raise ValueError(
                    f"Insufficient quota for provider '{provider}': {remaining} remaining, {cost} required"
                )
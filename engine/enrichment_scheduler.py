import argparse
import hashlib
import json
import logging
import signal
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Tuple, Dict, List, Optional, Any

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
    cost_dict
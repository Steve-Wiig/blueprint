import argparse
import hashlib
import json
import logging
import os
import signal
import sqlite3
import time
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from functools import wraps
from typing import Tuple, Dict, List, Optional, Any, Callable, Union

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


_HIGH_ENTROPY_PATTERN = re.compile(r'[A-Za-z0-9+/=]{32,}')
_DEFAULT_SENSITIVE_PATTERNS = [
    'secret', 'token', 'password', 'key', 'api_key', 'apikey',
    'access_token', 'refresh_token', 'client_secret', 'private_key',
    _HIGH_ENTROPY_PATTERN
]
_ENV_SENSITIVE_PATTERNS = 'SENSITIVE_PATTERNS'


def _load_sensitive_patterns_from_env() -> List[Union[str, re.Pattern]]:
    """Load sensitive patterns from environment variable.

    The environment variable should contain a JSON array of strings.
    Strings starting with 'regex:' are compiled as regex patterns.

    Returns:
        List of pattern strings and compiled regex patterns.
    """
    env_value = os.getenv(_ENV_SENSITIVE_PATTERNS)
    if not env_value:
        return []
    try:
        patterns = json.loads(env_value)
        result = []
        for pat in patterns:
            if isinstance(pat, str) and pat.startswith('regex:'):
                result.append(re.compile(pat[6:]))
            else:
                result.append(pat)
        return result
    except (json.JSONDecodeError, re.error) as e:
        logger.warning("Failed to parse SENSITIVE_PATTERNS env var: %s", e)
        return []


def sanitize(data: Dict[str, Any], sensitive_patterns: Optional[List[Union[str, re.Pattern]]] = None) -> Dict[str, Any]:
    """Recursively sanitize a dictionary by redacting sensitive fields.

    Args:
        data: The dictionary to sanitize.
        sensitive_patterns: List of substring patterns or compiled regex objects
            to detect sensitive keys. If None, uses default organizational patterns
            plus any patterns loaded from the SENSITIVE_PATTERNS environment variable.

    Returns:
        A new dictionary with sensitive values redacted.
    """
    if sensitive_patterns is None:
        sensitive_patterns = _DEFAULT_SENSITIVE_PATTERNS.copy()
        sensitive_patterns.extend(_load_sensitive_patterns_from_env())

    string_patterns = [p for p in sensitive_patterns if isinstance(p, str)]
    regex_patterns = [p for p in sensitive_patterns if isinstance(p, re.Pattern)]

    cache_key = tuple(string_patterns)
    if not hasattr(sanitize, '_string_regex_cache') or sanitize._string_regex_cache.get('key') != cache_key:
        if string_patterns:
            compiled = re.compile('|'.join(map(re.escape, string_patterns)), re.IGNORECASE)
        else:
            compiled = None
        sanitize._string_regex_cache = {'key': cache_key, 'regex': compiled}
    compiled_string_regex = sanitize._string_regex_cache['regex']

    def _is_sensitive(key: str) -> bool:
        key_lower = key.lower()
        if compiled_string_regex and compiled_string_regex.search(key_lower):
            return True
        for pat in regex_patterns:
            if pat.search(key):
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


_CACHE_TTL_SECONDS = 60
_fetch_cache: Dict[Tuple, Tuple[Any, float]] = {}


def _ttl_cache_get(key: Tuple) -> Optional[Any]:
    now = time.time()
    if key in _fetch_cache:
        value, cached_at = _fetch_cache[key]
        if now - cached_at < _CACHE_TTL_SECONDS:
            return value
    return None


def _ttl_cache_set(key: Tuple, value: Any) -> None:
    _fetch_cache[key] = (value, time.time())


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
    cache_key = (table, column, tuple(sorted(providers)))
    cached = _ttl_cache_get(cache_key)
    if cached is not None:
        return cached
    placeholders = ','.join(['?'] * len(providers))
    cursor.execute(
        f"SELECT provider, {column} FROM {table} WHERE provider IN ({placeholders})",
        providers
    )
    result = {row[0]: row[1] for row in cursor.fetchall()}
    _ttl_cache_set(cache_key, result)
    return result


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


def _check_batch_quota(
    sq_conn: sqlite3.Connection,
    providers_in_batch: List[str],
    providers_needed: List[str],
    cursor: sqlite3.Cursor
) -> None:
    """Validates that all providers in the batch have sufficient quota.

    Fetches quota for all providers in batch to verify configuration,
    fetches cost only for providers that need quota checked, then validates
    in a single pass to avoid redundant iteration and N+1 query patterns.

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

    quota_dict = _fetch_provider_values(sq_conn, providers_in_batch, 'quota_ledger', 'remaining', cursor)
    cost_dict = _fetch_provider_values(sq_conn, providers_needed, 'provider_costs', 'cost', cursor) if providers_needed else {}

    for provider in providers_in_batch:
        if provider not in quota_dict:
            raise ProviderNotConfiguredError(f"Provider '{provider}' not configured in quota_ledger")

        if provider in providers_needed:
            cost = cost_dict.get(provider, 0)
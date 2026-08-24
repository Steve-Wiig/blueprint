import json
import logging
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Iterable, List, Tuple

import psycopg2
from psycopg2.extras import execute_values

logger = logging.getLogger(__name__)


class IOCType(Enum):
    IPV4 = "ipv4"
    DOMAIN = "domain"
    URL = "url"
    SHA256 = "sha256"
    EMAIL = "email"


_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", re.IGNORECASE)
_DOMAIN_RE = re.compile(r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b", re.IGNORECASE)
_URL_RE = re.compile(r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+", re.IGNORECASE)
_SHA256_RE = re.compile(r"\b[a-fA-F0-9]{64}\b", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", re.IGNORECASE)

_PATTERNS = {
    IOCType.IPV4: _IPV4_RE,
    IOCType.DOMAIN: _DOMAIN_RE,
    IOCType.URL: _URL_RE,
    IOCType.SHA256: _SHA256_RE,
    IOCType.EMAIL: _EMAIL_RE,
}


def _iter_strings(obj: Any) -> Iterable[str]:
    """Recursively yield every string value found in a nested structure.

    Args:
        obj: The object to traverse (dict, list, or str).

    Yields:
        str: Each string value encountered during traversal.
    """
    if isinstance(obj, dict):
        for value in obj.values():
            yield from _iter_strings(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_strings(item)
    elif isinstance(obj, str):
        yield obj


def extract_iocs(sanitized_alert_json: Dict[str, Any]) -> int:
    """
    Extracts IOCs from sanitized alert payloads and persists to PostgreSQL.

    Compliant with LOCAL-SOC-SLM Blueprint v11.6.0 Section 30.

    Args:
        sanitized_alert_json: A dictionary containing the alert data to be parsed.

    Returns:
        int: 0 if successful or no IOCs found, 1 for general extraction errors,
            2 for database-related errors.
    """
    try:
        matches_by_type: Dict[IOCType, set] = {ioc_type: set() for ioc_type in _PATTERNS}

        for text in _iter_strings(sanitized_alert_json):
            for ioc_type, regex in _PATTERNS.items():
                matches_by_type[ioc_type].update(regex.findall(text))

        extracted: List[Tuple[str, str, str, datetime]] = []
        now = datetime.now(timezone.utc)
        for ioc_type, matches in matches_by_type.items():
            for match in matches:
                extracted.append((match, ioc_type.value, "pending", now))

        if not extracted:
            return 0

        conn = psycopg2.connect("dbname=soc_memory user=orchestrator")
        cur = conn.cursor()

        query = """
            INSERT INTO iocs (value, type, enrichment_status, first_seen)
            VALUES %s
            ON CONFLICT (value) DO UPDATE SET last_seen = EXCLUDED.first_seen
        """
        execute_values(cur, query, extracted)

        audit_records = [(value, ioc_type, "insert", now) for value, ioc_type, _, _ in extracted]
        audit_query = """
            INSERT INTO ioc_audit (value, type, action, timestamp)
            VALUES %s
        """
        execute_values(cur, audit_query, audit_records)

        conn.commit()
        cur.close()
        conn.close()
        return 0

    except psycopg2.Error as e:
        logger.error("Database error: %s", e)
        return 2
    except Exception as e:
        logger.error("Extraction error: %s", e)
        return 1


if __name__ == "__main__":
    result = extract_iocs({})
    print(result)
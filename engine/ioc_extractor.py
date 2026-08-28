import json
import logging
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Tuple

import psycopg2
from psycopg2.extras import execute_values

logger = logging.getLogger(__name__)


def _get_pg_conn():
    """Get or create a cached PostgreSQL connection."""
    conn = getattr(_get_pg_conn, "_conn", None)
    if conn is None or conn.closed:
        _get_pg_conn._conn = psycopg2.connect("dbname=soc_memory user=orchestrator")
    return _get_pg_conn._conn


class IOCType(Enum):
    IPV4 = "ipv4"
    DOMAIN = "domain"
    URL = "url"
    SHA256 = "sha256"
    EMAIL = "email"


_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_DOMAIN_RE = re.compile(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b", re.IGNORECASE)
_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_SHA256_RE = re.compile(r"\b[a-fA-F0-9]{64}\b")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

_IOC_PATTERNS = [
    (IOCType.IPV4, _IPV4_RE),
    (IOCType.DOMAIN, _DOMAIN_RE),
    (IOCType.URL, _URL_RE),
    (IOCType.SHA256, _SHA256_RE),
    (IOCType.EMAIL, _EMAIL_RE),
]


def _extract_alert_id(alert_json: Dict[str, Any]) -> str:
    """Extract alert ID from sanitized alert JSON using common field names."""
    for key in ("alert_id", "alertId", "id", "alert_id_str"):
        if key in alert_json and alert_json[key]:
            return str(alert_json[key])
    return "unknown"


def extract_iocs_from_text(text: str) -> Dict[IOCType, set]:
    """
    Extract IOCs from text using regex patterns.

    Args:
        text: Text to search for IOCs.

    Returns:
        Dictionary mapping IOCType to set of matched values.
    """
    matches_by_type: Dict[IOCType, set] = {ioc_type: set() for ioc_type in IOCType}
    for ioc_type, pattern in _IOC_PATTERNS:
        for match in pattern.finditer(text):
            matches_by_type[ioc_type].add(match.group(0))
    return matches_by_type


def deduplicate_iocs(matches_by_type: Dict[IOCType, set]) -> List[Tuple[str, str, str, datetime]]:
    """
    Deduplicate IOCs and prepare for persistence.

    Args:
        matches_by_type: Dictionary mapping IOCType to set of matched values.

    Returns:
        List of tuples (value, type, enrichment_status, first_seen).
    """
    seen = datetime.now(timezone.utc)
    extracted: List[Tuple[str, str, str, datetime]] = []
    for ioc_type, matches in matches_by_type.items():
        for match in matches:
            extracted.append((match, ioc_type.value, "pending", seen))
    return extracted


def persist_iocs(extracted: List[Tuple[str, str, str, datetime]]) -> None:
    """
    Persist IOCs to PostgreSQL with audit trail.

    Args:
        extracted: List of tuples (value, type, enrichment_status, first_seen).

    Raises:
        RuntimeError: If database operations fail.
    """
    if not extracted:
        return

    conn = _get_pg_conn()
    cur = conn.cursor()

    query = """
        WITH ins AS (
            INSERT INTO iocs (value, type, enrichment_status, first_seen)
            VALUES %s
            ON CONFLICT (value) DO UPDATE SET last_seen = EXCLUDED.first_seen
            RETURNING value, type, first_seen
        )
        INSERT INTO ioc_audit (value, type, action, timestamp)
        SELECT value, type, 'insert', first_seen FROM ins;
    """
    execute_values(cur, query, extracted)

    conn.commit()
    cur.close()


def audit_iocs(alert_id: str, ioc_count: int, timestamp: datetime) -> None:
    """
    Log IOC extraction audit information.

    Args:
        alert_id: Alert identifier.
        ioc_count: Number of IOCs extracted.
        timestamp: Extraction timestamp.
    """
    logger.info(
        "IOC extraction audit: alert_id=%s ioc_count=%s timestamp=%s",
        alert_id,
        ioc_count,
        timestamp.isoformat(),
    )


def extract_iocs(sanitized_alert_json: Dict[str, Any]) -> int:
    """
    Extracts IOCs from sanitized alert payloads and persists to PostgreSQL.

    Compliant with LOCAL-SOC-SLM Blueprint v11.6.0 Section 30.

    Args:
        sanitized_alert_json: A dictionary containing the alert data to be parsed.

    Returns:
        int: 0 if successful or no IOCs found.

    Raises:
        RuntimeError: If extraction or database operations fail.
    """
    try:
        serialized = json.dumps(sanitized_alert_json, ensure_ascii=False)
        matches_by_type = extract_iocs_from_text(serialized)
        extracted = deduplicate_iocs(matches_by_type)

        if not extracted:
            return 0

        alert_id = _extract_alert_id(sanitized_alert_json)
        ioc_count = len(extracted)
        seen = datetime.now(timezone.utc)

        persist_iocs(extracted)
        audit_iocs(alert_id, ioc_count, seen)

        return 0

    except psycopg2.Error as e:
        logger.exception("Database error")
        raise RuntimeError("Database error") from e
    except (TypeError, ValueError, AttributeError, KeyError) as e:
        logger.exception("Extraction error")
        raise RuntimeError("Extraction failed") from e


if __name__ == "__main__":
    result = extract_iocs({})
    print(result)
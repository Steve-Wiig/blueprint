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


_COMBINED_RE = re.compile(
    r"(?P<ipv4>\b(?:\d{1,3}\.){3}\d{1,3}\b)"
    r"|(?P<domain>\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b)"
    r"|(?P<url>https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+)"
    r"|(?P<sha256>\b[a-fA-F0-9]{64}\b)"
    r"|(?P<email>\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b)",
    re.IGNORECASE,
)

_GROUP_TO_IOC = {
    "ipv4": IOCType.IPV4,
    "domain": IOCType.DOMAIN,
    "url": IOCType.URL,
    "sha256": IOCType.SHA256,
    "email": IOCType.EMAIL,
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


def _extract_alert_id(alert_json: Dict[str, Any]) -> str:
    """Extract alert ID from sanitized alert JSON using common field names."""
    for key in ("alert_id", "alertId", "id", "alert_id_str"):
        if key in alert_json and alert_json[key]:
            return str(alert_json[key])
    return "unknown"


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
        matches_by_type: Dict[IOCType, set] = {ioc_type: set() for ioc_type in IOCType}

        for text in _iter_strings(sanitized_alert_json):
            for match in _COMBINED_RE.finditer(text):
                for group_name, ioc_type in _GROUP_TO_IOC.items():
                    value = match.group(group_name)
                    if value:
                        matches_by_type[ioc_type].add(value)
                        break

        extracted: List[Tuple[str, str, str, datetime]] = []
        now = datetime.now(timezone.utc)
        for ioc_type, matches in matches_by_type.items():
            for match in matches:
                extracted.append((match, ioc_type.value, "pending", now))

        if not extracted:
            return 0

        alert_id = _extract_alert_id(sanitized_alert_json)
        ioc_count = len(extracted)

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

        logger.info(
            "IOC extraction audit: alert_id=%s ioc_count=%s timestamp=%s",
            alert_id,
            ioc_count,
            now.isoformat(),
        )
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
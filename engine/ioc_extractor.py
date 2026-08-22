import json
import re
from datetime import datetime, timezone
from typing import Any, Dict

import psycopg2
from psycopg2.extras import execute_values

_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", re.IGNORECASE)
_DOMAIN_RE = re.compile(r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b", re.IGNORECASE)
_URL_RE = re.compile(r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+", re.IGNORECASE)
_SHA256_RE = re.compile(r"\b[a-fA-F0-9]{64}\b", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", re.IGNORECASE)

_PATTERNS = {
    "ipv4": _IPV4_RE,
    "domain": _DOMAIN_RE,
    "url": _URL_RE,
    "sha256": _SHA256_RE,
    "email": _EMAIL_RE,
}


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
        payload_str = json.dumps(sanitized_alert_json)
        extracted = []

        for ioc_type, regex in _PATTERNS.items():
            matches = set(regex.findall(payload_str))
            for match in matches:
                extracted.append((match, ioc_type, "pending", datetime.now(timezone.utc)))

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

        conn.commit()
        cur.close()
        conn.close()
        return 0

    except psycopg2.Error as e:
        print(f"Database error: {e}")
        return 2
    except Exception as e:
        print(f"Extraction error: {e}")
        return 1


if __name__ == "__main__":
    result = extract_iocs({})
    print(result)
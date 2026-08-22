"""
Module for extracting Indicators of Compromise (IOCs) from alert payloads.

This module provides functionality to parse sanitized alert JSON objects for
various IOC types (IPv4, domains, URLs, SHA256 hashes, and emails) and
persists them into a PostgreSQL database, maintaining a 90‑day retention policy.

NOTE: The 90‑day cleanup is now expected to be handled by an external scheduled
job (e.g., cron, pg_cron, or a partitioning strategy) rather than on every
extraction call to avoid unnecessary load and potential table locks.
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict

import psycopg2
from psycopg2.extras import execute_values


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
        # Regex patterns for IOC extraction
        patterns = {
            "ipv4": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
            "domain": r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b",
            "url": r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+",
            "sha256": r"\b[a-fA-F0-9]{64}\b",
            "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        }

        extracted = []
        for ioc_type, pattern in patterns.items():
            matches = set(re.findall(pattern, str(sanitized_alert_json), re.IGNORECASE))
            for match in matches:
                extracted.append((match, ioc_type, "pending", datetime.now(timezone.utc)))

        if not extracted:
            return 0

        conn = psycopg2.connect("dbname=soc_memory user=orchestrator")
        cur = conn.cursor()

        # Insert extracted IOCs
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
    exit(extract_iocs({}))
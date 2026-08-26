"""Security Onion Case Writeback Adapter.

LOCAL-SOC-SLM Blueprint v11.6.0 - Appendix Q.4
"""

import argparse
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Callable

import requests

# Module-level session for HTTP connection pooling (TCP keepalive)
_HTTP_SESSION = requests.Session()


DRAFT_CASE_ID = 'DRAFT_ID_000'
DEFAULT_LEDGER_PATH = 'handoffs_ledger.log'


def configure_logging() -> None:
    """Configure logging for the application."""
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


def sanitize_input(data: Any) -> Dict[str, str]:
    """Sanitizes input dictionary by truncating keys and values.

    Args:
        data: The input data to sanitize.

    Returns:
        A dictionary with keys truncated to 64 chars and values to 2048 chars.
    """
    if not isinstance(data, dict):
        return {}
    return {str(k)[:64]: str(v)[:2048] for k, v in data.items()}


def create_case_draft(sanitized: Dict[str, str]) -> str:
    """Creates a draft case by logging and returning a mock ID.

    Args:
        sanitized: The sanitized payload.

    Returns:
        A draft case identifier.
    """
    logging.info(f"DRAFT MODE: Payload sanitized: {sanitized}")
    return DRAFT_CASE_ID


def create_case_live(api_url: str, api_key: str, sanitized: Dict[str, str]) -> str:
    """Creates a case via the Security Onion API.

    Args:
        api_url: The base URL of the API.
        api_key: The authorization token.
        sanitized: The sanitized payload.

    Returns:
        The ID of the created case.

    Raises:
        RuntimeError: If the API request fails.
    """
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        response = _HTTP_SESSION.post(f"{api_url}/api/cases", json=sanitized, headers=headers, timeout=10)
        response.raise_for_status()
        case_id = response.json().get("id")
        return case_id
    except Exception as e:
        logging.error(f"API Failure: {e}")
        raise RuntimeError(f"Library code called exit(1)")


def _get_case_creator(draft_mode: bool) -> Callable[..., str]:
    """Factory function to get the appropriate case creator.

    Args:
        draft_mode: If True, returns draft creator; otherwise live creator.

    Returns:
        A callable that creates a case.
    """
    if draft_mode:
        return lambda sanitized: create_case_draft(sanitized)
    return lambda api_url, api_key, sanitized: create_case_live(api_url, api_key, sanitized)


def create_case(api_url: str, api_key: str, payload: Dict[str, Any], draft_mode: bool) -> str:
    """Creates a case via the Security Onion API (backward compatible).

    Args:
        api_url: The base URL of the API.
        api_key: The authorization token.
        payload: The case data to submit.
        draft_mode: If True, skips API call and returns a mock ID.

    Returns:
        The ID of the created case or a draft identifier.

    Raises:
        RuntimeError: If the API request fails.
    """
    sanitized = sanitize_input(payload)
    creator = _get_case_creator(draft_mode)
    
    if draft_mode:
        return creator(sanitized)
    return creator(api_url, api_key, sanitized)


def write_to_ledger(payload_ref: str, case_id: str) -> None:
    """Writes the case transaction to the local handoff ledger.

    Args:
        payload_ref: The reference identifier from the payload.
        case_id: The ID of the created case.

    Raises:
        RuntimeError: If the ledger file cannot be written to.
    """
    try:
        with open(DEFAULT_LEDGER_PATH, "a") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()} | {payload_ref} | {case_id}\n")
    except IOError:
        raise RuntimeError(f"Library code called exit(2)")


def main() -> None:
    """Parses command line arguments and executes the case writeback process."""
    configure_logging()
    
    parser = argparse.ArgumentParser(description="SO Case Writeback Adapter")
    parser.add_argument("--url", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--payload", required=True, help="JSON string of case data")
    parser.add_argument("--draft", action="store_true")
    
    args = parser.parse_args()

    try:
        data = json.loads(args.payload)
    except json.JSONDecodeError:
        raise RuntimeError(f"Library code called exit(2)")

    case_id = create_case(args.url, args.key, data, args.draft)
    
    if not args.draft:
        write_to_ledger(data.get("ref", "N/A"), case_id)
    
    print(f"SUCCESS: {case_id}")
    raise RuntimeError(f"Library code called exit(0)")


if __name__ == "__main__":
    main()
"""TheHive Case Writeback Adapter (v11.6.0)

Automates writing case data from JSON payloads into TheHive with mode-specific
modifications and handoff logging.

Example:
    >>> from thehive_writeback import main
    >>> # main("--case-data '{\"id\": 1}' --api-key 'xxxxx' --url 'https://thehive.example.com' --mode draft")

Raises:
    RuntimeError: If JSON decoding fails, the API request fails, or the case ID is missing.
"""

import argparse
import os
import requests
import json
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union
from engine.sanitization_pipeline import sanitize_payload

REQUIRED_CASE_FIELDS = {'title', 'description'}

_logger: Optional[logging.Logger] = None
_log_path: Optional[Path] = None


def _setup_logger(log_path: Path) -> logging.Logger:
    """Configure and return a logger for handoff events."""
    global _logger
    logger = logging.getLogger("thehive_writeback.handoff")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # Clear existing handlers to avoid duplicates
    logger.handlers.clear()

    handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)

    _logger = logger
    return logger


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        argparse.Namespace: Parsed arguments including case_data, api_key, url,
            mode, and log_path.

    Raises:
        SystemExit: If required arguments are missing (handled by argparse).
    """
    parser = argparse.ArgumentParser(description="TheHive Case Writeback Adapter v11.6.0")
    parser.add_argument("--case-data", required=True, help="JSON string of case data")
    parser.add_argument("--api-key", required=True, help="TheHive API Key")
    parser.add_argument("--url", required=True, help="TheHive Base URL")
    parser.add_argument("--mode", choices=['draft', 'live'], default='draft', help="Adapter mode")
    parser.add_argument("--log-path", help="Path to the handoff log file (overrides HANDOFF_LOG_PATH env var and default)")
    return parser.parse_args()


def build_payload(raw_data: Any, mode: str) -> Any:
    """Apply mode-specific modifications and sanitize payload.

    Args:
        raw_data: Dictionary containing case data to be modified.
        mode: Operation mode, either 'draft' or 'live'.

    Returns:
        Dict: Sanitized payload ready for TheHive API submission.

    Raises:
        ValueError: If sanitize_payload raises an error due to invalid input.
    """
    if mode == 'draft':
        raw_data['status'] = 'Open'
        raw_data['tags'] = raw_data.get('tags', []) + ['draft-mode']
    return sanitize_payload(raw_data)


def call_thehive_api(url: str, api_key: str, payload: Any) -> str:
    """Create case in TheHive and return case ID.

    Args:
        url: TheHive base URL instance root.
        api_key: Authentication token for TheHive API.
        payload: Sanitized case payload dictionary.

    Returns:
        str: Case ID assigned by TheHive upon successful creation.

    Raises:
        RuntimeError: If response status is not 200 or 201, or if case ID
            is absent from response JSON.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    response = requests.post(
        f"{url}/api/case",
        json=payload,
        headers=headers,
        timeout=30
    )
    if response.status_code not in [200, 201]:
        raise RuntimeError(f"TheHive API error: {response.status_code} - {response.text}")
    case_id = response.json().get('id')
    if not case_id:
        raise RuntimeError("TheHive API response missing case ID")
    return case_id


def log_handoff(log_path: Path, case_id: str, mode: str) -> None:
    """Log successful case creation to handoff log.

    Args:
        log_path: Path to the handoff log file.
        case_id: Case ID returned from TheHive API.
        mode: Adapter mode string ('draft' or 'live').
    """
    global _logger, _log_path

    if _logger is None or _log_path != log_path:
        _setup_logger(log_path)
        _log_path = log_path

    now = datetime.now(timezone.utc)
    _logger.info(f"{now.isoformat()}|REF:{case_id}|STATUS:SUCCESS|MODE:{mode}")


def main() -> Union[str, int]:
    """Orchestrate the case writeback process.

    Returns:
        str: Case ID on success.
        int: Exit code on failure (1=validation/API error, 2=JSON decode error, 3=request exception)

    Example:
        >>> import argparse
        >>> from thehive_writeback import parse_args
        >>> # args = parse_args("--case-data '{\"id\":1}' --api-key 'key' --url 'https://hive.example.com' --mode draft")
    """
    args = parse_args()

    log_path = Path(args.log_path) if args.log_path else Path(os.environ.get("HANDOFF_LOG_PATH", "handoff_log.txt"))

    try:
        raw_data: Any = json.loads(args.case_data)
    except json.JSONDecodeError:
        return 2

    # Validate required fields
    missing = REQUIRED_CASE_FIELDS - set(raw_data.keys())
    if missing:
        print(f"Missing required fields: {missing}", file=sys.stderr)
        return 1

    sanitized_data = build_payload(raw_data, args.mode)

    try:
        case_id = call_thehive_api(args.url, args.api_key, sanitized_data)
        log_handoff(log_path, case_id, args.mode)
        return case_id
    except requests.exceptions.RequestException:
        return 3
    except RuntimeError:
        return 1


if __name__ == "__main__":
    result = main()
    if isinstance(result, str):
        sys.exit(0)
    else:
        sys.exit(result)
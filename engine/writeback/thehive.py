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

"""
TheHive Case Writeback Adapter

This module provides functionality to create cases in TheHive platform
from structured case data. It handles payload sanitization, API communication,
and audit logging for SOC automation workflows.

Usage:
    python -m thehive_writeback.handoff --case-data '{"title": "...", "description": "..."}' \
        --api-key <key> --url <url> [--mode draft|live] [--log-path <path>]

Environment Variables:
    HANDOFF_LOG_PATH: Default path for handoff log file (default: handoff_log.txt)
"""

REQUIRED_CASE_FIELDS = {'title', 'description'}


def _setup_logger(log_path: Path) -> logging.Logger:
    """Configure a file logger for handoff audit trail.

    Args:
        log_path: Path to the log file.

    Returns:
        Configured logger instance with file handler.
    """
    logger_name = f"thehive_writeback.handoff.{log_path}"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()
    handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    return logger


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the TheHive writeback adapter.

    Returns:
        Parsed arguments namespace with attributes:
        - case_data: JSON string of case data
        - api_key: TheHive API key
        - url: TheHive base URL
        - mode: Operation mode ('draft' or 'live')
        - log_path: Optional path to handoff log file
    """
    parser = argparse.ArgumentParser(description="TheHive Case Writeback Adapter v11.6.0")
    parser.add_argument("--case-data", required=True, help="JSON string of case data")
    parser.add_argument("--api-key", required=True, help="TheHive API Key")
    parser.add_argument("--url", required=True, help="TheHive Base URL")
    parser.add_argument("--mode", choices=['draft', 'live'], default='draft', help="Adapter mode")
    parser.add_argument("--log-path", help="Path to the handoff log file (overrides HANDOFF_LOG_PATH env var and default)")
    return parser.parse_args()


def build_payload(raw_data: Any, mode: str) -> Any:
    """Build and sanitize the case payload for TheHive API.

    This function creates a copy of the input data to avoid mutating
    the caller's original dictionary.

    Args:
        raw_data: Raw case data dictionary.
        mode: Operation mode ('draft' or 'live').

    Returns:
        Sanitized payload ready for TheHive API submission.

    Raises:
        ValueError: If sanitization fails due to invalid data.
    """
    data = dict(raw_data)
    if mode == 'draft':
        data['status'] = 'Open'
        data['tags'] = data.get('tags', []) + ['draft-mode']
    return sanitize_payload(data)


def call_thehive_api(url: str, api_key: str, payload: Any) -> str:
    """Create a case in TheHive via REST API.

    Args:
        url: TheHive base URL (e.g., 'https://thehive.example.com').
        api_key: TheHive API key for authentication.
        payload: Sanitized case payload dictionary.

    Returns:
        TheHive case ID string.

    Raises:
        RuntimeError: If API returns error status or missing case ID in response.
        requests.exceptions.RequestException: If network request fails.
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
    """Log successful case creation to handoff audit file.

    Args:
        log_path: Path to the handoff log file.
        case_id: TheHive case ID that was created.
        mode: Operation mode ('draft' or 'live').

    Returns:
        None
    """
    logger = _setup_logger(log_path)
    now = datetime.now(timezone.utc)
    logger.info(f"{now.isoformat()}|REF:{case_id}|STATUS:SUCCESS|MODE:{mode}")


def main() -> Union[str, int]:
    """Main entry point for TheHive case writeback adapter.

    Parses arguments, validates input, creates case in TheHive,
    and logs the handoff result.

    Returns:
        Case ID string on success, or integer exit code on failure:
        - 1: Missing required fields or TheHive API error
        - 2: Invalid JSON in case-data
        - 3: Network/request exception

    Raises:
        SystemExit: Not raised directly; returns exit codes for caller to handle.
    """
    args = parse_args()
    log_path = Path(args.log_path) if args.log_path else Path(os.environ.get("HANDOFF_LOG_PATH", "handoff_log.txt"))
    try:
        raw_data: Any = json.loads(args.case_data)
    except json.JSONDecodeError:
        return 2
    missing = REQUIRED_CASE_FIELDS - set(raw_data.keys())
    if missing:
        print(f"Missing required fields: {missing}", file=sys.stderr)
        return 1
    sanitized_data = build_payload(raw_data, args.mode)
    try:
        case_id = call_thehive_api(args.url, args.api_key, sanitized_data)
        log_handoff(log_path, case_id, args.mode)
        return case_id
    except requests.exceptions.RequestException as e:
        error_logger = logging.getLogger("thehive_writeback.handoff.error")
        error_logger.setLevel(logging.ERROR)
        if not error_logger.handlers:
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
            error_logger.addHandler(handler)
        error_logger.exception("TheHive API request failed for URL %s with payload %s", args.url, sanitized_data)
        return 3
    except RuntimeError:
        return 1


if __name__ == "__main__":
    result = main()
    if isinstance(result, str):
        sys.exit(0)
    else:
        sys.exit(result)
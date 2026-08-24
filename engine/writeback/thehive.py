"""TheHive Case Writeback Adapter module.

This module provides functionality to interface with TheHive API to create cases
based on sanitized input data.
"""

import argparse
import os
import requests
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from engine.sanitization_pipeline import sanitize_payload


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="TheHive Case Writeback Adapter v11.6.0")
    parser.add_argument("--case-data", required=True, help="JSON string of case data")
    parser.add_argument("--api-key", required=True, help="TheHive API Key")
    parser.add_argument("--url", required=True, help="TheHive Base URL")
    parser.add_argument("--mode", choices=['draft', 'live'], default='draft', help="Adapter mode")
    parser.add_argument("--log-path", help="Path to the handoff log file (overrides HANDOFF_LOG_PATH env var and default)")
    return parser.parse_args()


def build_payload(raw_data: Any, mode: str) -> Any:
    """Apply mode-specific modifications and sanitize payload."""
    if mode == 'draft':
        raw_data['status'] = 'Open'
        raw_data['tags'] = raw_data.get('tags', []) + ['draft-mode']
    return sanitize_payload(raw_data)


def create_case(url: str, api_key: str, payload: Any) -> str:
    """Create case in TheHive and return case ID."""
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
        raise RuntimeError(f"Library code called exit(1)")
    case_id = response.json().get('id')
    if not case_id:
        raise RuntimeError(f"Library code called exit(1)")
    return case_id


def log_handoff(log_path: Path, case_id: str, mode: str) -> None:
    """Log successful case creation to handoff log."""
    now = datetime.now(timezone.utc)
    with open(log_path, "a") as f:
        f.write(f"{now.isoformat()}|REF:{case_id}|STATUS:SUCCESS|MODE:{mode}\n")


def main() -> None:
    """Orchestrate the case writeback process."""
    args = parse_args()

    log_path = Path(args.log_path) if args.log_path else Path(os.environ.get("HANDOFF_LOG_PATH", "handoff_log.txt"))

    try:
        raw_data: Any = json.loads(args.case_data)
    except json.JSONDecodeError:
        raise RuntimeError(f"Library code called exit(2)")

    sanitized_data = build_payload(raw_data, args.mode)

    try:
        case_id = create_case(args.url, args.api_key, sanitized_data)
        log_handoff(log_path, case_id, args.mode)
        raise RuntimeError(f"Library code called exit(0)")
    except requests.exceptions.RequestException:
        raise RuntimeError(f"Library code called exit(3)")


if __name__ == "__main__":
    main()
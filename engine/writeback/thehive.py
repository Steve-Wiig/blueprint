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


def _setup_logger(log_path: Path) -> logging.Logger:
    logger = logging.getLogger("thehive_writeback.handoff")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()
    handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    return logger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TheHive Case Writeback Adapter v11.6.0")
    parser.add_argument("--case-data", required=True, help="JSON string of case data")
    parser.add_argument("--api-key", required=True, help="TheHive API Key")
    parser.add_argument("--url", required=True, help="TheHive Base URL")
    parser.add_argument("--mode", choices=['draft', 'live'], default='draft', help="Adapter mode")
    parser.add_argument("--log-path", help="Path to the handoff log file (overrides HANDOFF_LOG_PATH env var and default)")
    return parser.parse_args()


def build_payload(raw_data: Any, mode: str) -> Any:
    if mode == 'draft':
        raw_data['status'] = 'Open'
        raw_data['tags'] = raw_data.get('tags', []) + ['draft-mode']
    return sanitize_payload(raw_data)


def call_thehive_api(url: str, api_key: str, payload: Any) -> str:
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
    global _logger
    if _logger is None:
        _logger = _setup_logger(log_path)
    now = datetime.now(timezone.utc)
    _logger.info(f"{now.isoformat()}|REF:{case_id}|STATUS:SUCCESS|MODE:{mode}")


def main() -> Union[str, int]:
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
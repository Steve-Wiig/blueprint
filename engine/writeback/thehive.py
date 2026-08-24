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

def main() -> None:
    """Parses command line arguments and executes the case writeback process.

    The function reads case data, sanitizes it, applies mode-specific modifications,
    and attempts to post the data to TheHive API. Exits with status codes:
    0: Success
    1: API Error
    2: JSON Decode Error
    3: Request Exception
    """
    parser = argparse.ArgumentParser(description="TheHive Case Writeback Adapter v11.6.0")
    parser.add_argument("--case-data", required=True, help="JSON string of case data")
    parser.add_argument("--api-key", required=True, help="TheHive API Key")
    parser.add_argument("--url", required=True, help="TheHive Base URL")
    parser.add_argument("--mode", choices=['draft', 'live'], default='draft', help="Adapter mode")
    parser.add_argument("--log-path", help="Path to the handoff log file (overrides HANDOFF_LOG_PATH env var and default)")

    args = parser.parse_args()

    # Determine log path: argument > environment variable > default
    log_path = Path(args.log_path) if args.log_path else Path(os.environ.get("HANDOFF_LOG_PATH", "handoff_log.txt"))

    try:
        raw_data: Any = json.loads(args.case_data)
    except json.JSONDecodeError:
        raise RuntimeError(f"Library code called exit(2)")

    sanitized_data = sanitize_payload(raw_data)
    
    if args.mode == 'draft':
        sanitized_data['status'] = 'Open'
        sanitized_data['tags'] = sanitized_data.get('tags', []) + ['draft-mode']

    headers = {
        "Authorization": f"Bearer {args.api_key}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(
            f"{args.url}/api/case",
            json=sanitized_data,
            headers=headers,
            timeout=30
        )
        
        if response.status_code in [200, 201]:
            case_id = response.json().get('id')
            now = datetime.now(timezone.utc)
            with open(log_path, "a") as f:
                f.write(f"{now.isoformat()}|REF:{case_id}|STATUS:SUCCESS|MODE:{args.mode}\n")
            raise RuntimeError(f"Library code called exit(0)")
        else:
            raise RuntimeError(f"Library code called exit(1)")
            
    except requests.exceptions.RequestException:
        raise RuntimeError(f"Library code called exit(3)")

if __name__ == "__main__":
    main()
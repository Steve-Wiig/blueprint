#!/usr/bin/env python3
# CI Gate: Queue Backpressure Check
# Verifies that the message broker/queue system respects flow control limits
# defined in the LOCAL-SOC-SLM Blueprint v11.6.0.

import os
import sys
import argparse
import logging
import requests
import json
from enum import Enum
from datetime import datetime, timezone

# Blueprint v11.6.0 Constants (configurable via environment variables)
MAX_QUEUE_DEPTH = int(os.getenv('MAX_QUEUE_DEPTH', '1000'))
BACKPRESSURE_THRESHOLD = float(os.getenv('BACKPRESSURE_THRESHOLD', '0.85'))
QUEUE_API_ENDPOINT = os.getenv('QUEUE_API_ENDPOINT', '/api/v1/queue/status')

class ExitCode(Enum):
    SUCCESS = 0
    API_ERROR = 1
    CONFIG_ERROR = 2
    TOKEN_MISSING = 3
    API_RESPONSE_ERROR = 4

class UTCFormatter(logging.Formatter):
    """Custom formatter that uses timezone-aware UTC timestamps."""
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()

handler = logging.StreamHandler()
handler.setFormatter(UTCFormatter(
    fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S%z'
))
logging.basicConfig(level=logging.INFO, handlers=[handler])
logger = logging.getLogger(__name__)

def check_backpressure(lab_url: str | None, dry_run: bool = False) -> int:
    """
    Queries the queue status and validates that backpressure signals
    are active if the queue depth exceeds the threshold.
    """
    if not lab_url:
        logger.error("CONFIG ERROR: LAB_URL not defined")
        return ExitCode.CONFIG_ERROR.value

    if dry_run:
        logger.info("DRY-RUN: Skipping network request. Simulating healthy queue.")
        return ExitCode.SUCCESS.value

    try:
        # [LAB-VERIFY] Queue status requires internal service token
        token = os.getenv("QUEUE_SERVICE_TOKEN")
        if not token:
            logger.error("ENV_NOT_AVAILABLE: QUEUE_SERVICE_TOKEN missing")
            return ExitCode.TOKEN_MISSING.value

        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{lab_url.rstrip('/')}{QUEUE_API_ENDPOINT}", 
                                headers=headers, timeout=5, verify=True)
        
        if response.status_code != 200:
            logger.error("FAIL: Queue API returned %s", response.status_code)
            return ExitCode.API_ERROR.value

        data = response.json()
        current_depth = data.get("depth", 0)
        backpressure_active = data.get("backpressure_active", False)

        # Logic: If depth > threshold, backpressure MUST be active
        if current_depth > int(MAX_QUEUE_DEPTH * BACKPRESSURE_THRESHOLD):
            if not backpressure_active:
                logger.error("FAIL: Backpressure not triggered at depth %s", current_depth)
                return ExitCode.API_ERROR.value
        
        logger.info("PASS: Queue depth %s within operational limits.", current_depth)
        return ExitCode.SUCCESS.value

    except requests.RequestException as e:
        logger.error("FAIL: Connection error: %s", e)
        return ExitCode.API_ERROR.value
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
        logger.error("FAIL: Response parsing error: %s", e)
        return ExitCode.API_RESPONSE_ERROR.value
    except Exception as e:
        logger.error("FAIL: Unexpected error: %s", e)
        return ExitCode.API_ERROR.value

def main() -> int:
    """Entry point for CI gate. Returns 0 on success, non-zero on failure."""
    parser = argparse.ArgumentParser(description="Queue Backpressure CI Gate")
    parser.add_argument("--dry-run", action="store_true", help="Skip network checks")
    args = parser.parse_args()

    lab_url = os.getenv("LAB_URL")
    return check_backpressure(lab_url, args.dry_run)

if __name__ == "__main__":
    try:
        exit_code = main()
        if exit_code != 0:
            raise RuntimeError(f"CI gate failed with exit code {exit_code}")
    except Exception as e:
        logger.error("CI gate execution failed: %s", e)
        raise
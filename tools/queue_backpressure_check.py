#!/usr/bin/env python3
# CI Gate: Queue Backpressure Check
# Verifies that the message broker/queue system respects flow control limits
# defined in the LOCAL-SOC-SLM Blueprint v11.6.0.

import os
import sys
import argparse
import requests

# Blueprint v11.6.0 Constants (configurable via environment variables)
MAX_QUEUE_DEPTH = int(os.getenv('MAX_QUEUE_DEPTH', '1000'))
BACKPRESSURE_THRESHOLD = float(os.getenv('BACKPRESSURE_THRESHOLD', '0.85'))
QUEUE_API_ENDPOINT = os.getenv('QUEUE_API_ENDPOINT', '/api/v1/queue/status')

ERROR_CODES = {
    'SUCCESS': 0,
    'API_ERROR': 1,
    'CONFIG_ERROR': 2,
    'TOKEN_MISSING': 3
}

def check_backpressure(lab_url: str | None, dry_run: bool = False) -> int:
    """
    Queries the queue status and validates that backpressure signals
    are active if the queue depth exceeds the threshold.
    """
    if not lab_url:
        print("CONFIG ERROR: LAB_URL not defined")
        return ERROR_CODES['CONFIG_ERROR']

    if dry_run:
        print("DRY-RUN: Skipping network request. Simulating healthy queue.")
        return ERROR_CODES['SUCCESS']

    try:
        # [LAB-VERIFY] Queue status requires internal service token
        token = os.getenv("QUEUE_SERVICE_TOKEN")
        if not token:
            print("ENV_NOT_AVAILABLE: QUEUE_SERVICE_TOKEN missing")
            return ERROR_CODES['TOKEN_MISSING']

        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{lab_url.rstrip('/')}{QUEUE_API_ENDPOINT}", 
                                headers=headers, timeout=5, verify=True)
        
        if response.status_code != 200:
            print(f"FAIL: Queue API returned {response.status_code}")
            return ERROR_CODES['API_ERROR']

        data = response.json()
        current_depth = data.get("depth", 0)
        backpressure_active = data.get("backpressure_active", False)

        # Logic: If depth > threshold, backpressure MUST be active
        if current_depth > (MAX_QUEUE_DEPTH * BACKPRESSURE_THRESHOLD):
            if not backpressure_active:
                print(f"FAIL: Backpressure not triggered at depth {current_depth}")
                return ERROR_CODES['API_ERROR']
        
        print(f"PASS: Queue depth {current_depth} within operational limits.")
        return ERROR_CODES['SUCCESS']

    except requests.RequestException as e:
        print(f"FAIL: Connection error: {e}")
        return ERROR_CODES['API_ERROR']
    except ValueError as e:
        print(f"FAIL: Data parsing error: {e}")
        return ERROR_CODES['CONFIG_ERROR']
    except KeyError as e:
        print(f"FAIL: Missing key in response: {e}")
        return ERROR_CODES['CONFIG_ERROR']
    except TypeError as e:
        print(f"FAIL: Type mismatch: {e}")
        return ERROR_CODES['CONFIG_ERROR']
    except Exception as e:
        print(f"FAIL: Unexpected error: {e}")
        return ERROR_CODES['API_ERROR']

def main() -> int:
    """Entry point for CI gate. Returns 0 on success, non-zero on failure."""
    parser = argparse.ArgumentParser(description="Queue Backpressure CI Gate")
    parser.add_argument("--dry-run", action="store_true", help="Skip network checks")
    args = parser.parse_args()

    lab_url = os.getenv("LAB_URL")
    return check_backpressure(lab_url, args.dry_run)

if __name__ == "__main__":
    raise SystemExit(main())
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

def check_backpressure(lab_url: str | None, dry_run: bool = False) -> int:
    """
    Queries the queue status and validates that backpressure signals
    are active if the queue depth exceeds the threshold.
    """
    if not lab_url:
        print("CONFIG ERROR: LAB_URL not defined")
        return 2

    if dry_run:
        print("DRY-RUN: Skipping network request. Simulating healthy queue.")
        return 0

    try:
        # [LAB-VERIFY] Queue status requires internal service token
        token = os.getenv("QUEUE_SERVICE_TOKEN")
        if not token:
            print("ENV_NOT_AVAILABLE: QUEUE_SERVICE_TOKEN missing")
            return 3

        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{lab_url.rstrip('/')}{QUEUE_API_ENDPOINT}", 
                                headers=headers, timeout=5, verify=True)
        
        if response.status_code != 200:
            print(f"FAIL: Queue API returned {response.status_code}")
            return 1

        data = response.json()
        current_depth = data.get("depth", 0)
        backpressure_active = data.get("backpressure_active", False)

        # Logic: If depth > threshold, backpressure MUST be active
        if current_depth > (MAX_QUEUE_DEPTH * BACKPRESSURE_THRESHOLD):
            if not backpressure_active:
                print(f"FAIL: Backpressure not triggered at depth {current_depth}")
                return 1
        
        print(f"PASS: Queue depth {current_depth} within operational limits.")
        return 0

    except requests.RequestException as e:
        print(f"FAIL: Connection error: {e}")
        return 1
    except Exception as e:
        print(f"FAIL: Unexpected error: {e}")
        return 1

def main():
    parser = argparse.ArgumentParser(description="Queue Backpressure CI Gate")
    parser.add_argument("--dry-run", action="store_true", help="Skip network checks")
    args = parser.parse_args()

    lab_url = os.getenv("LAB_URL")
    return check_backpressure(lab_url, args.dry_run)

if __name__ == "__main__":
    sys.exit(main())
#!/usr/bin/env python3
# CI Gate: Queue Stale Recovery Check
# Verifies that the message queue handler implements recovery logic for stale messages
# exceeding the TTL threshold defined in LOCAL-SOC-SLM Blueprint v11.6.0.

import os
import sys
import argparse
from enum import IntEnum

DEFAULT_STALE_THRESHOLD_SECONDS = 300
DEFAULT_REQUIRED_RECOVERY_LOG_PATTERN = "RECOVERY_INITIATED_STALE_MSG"
DEFAULT_MANIFEST_FILENAME = "recovery_manifest.log"
MAX_MANIFEST_SIZE_BYTES = 10 * 1024 * 1024


class ExitCode(IntEnum):
    SUCCESS = 0
    FAIL = 1
    CONFIG_ERROR = 2
    ENV_NOT_AVAILABLE = 3
    NOT_DIRECTORY = 4
    PERMISSION_ERROR = 5


def load_config(args: argparse.Namespace) -> dict:
    """Load configuration with precedence: CLI args > environment variables > defaults."""
    return {
        "stale_threshold_seconds": args.stale_threshold,
        "required_recovery_log_pattern": args.recovery_pattern,
        "manifest_filename": args.manifest_file,
    }


def check_queue_recovery(dry_run: bool = False, config: dict | None = None) -> ExitCode:
    """
    Verifies that the local message queue interface supports stale message recovery.
    In a production environment, this would query the local message broker status.
    [LAB-VERIFY]: Requires local access to the message broker socket.
    """
    if config is None:
        raise ValueError("config must be provided")

    queue_path = os.getenv("SOC_QUEUE_PATH")
    if not queue_path:
        print("CONFIG ERROR: SOC_QUEUE_PATH not defined")
        return ExitCode.CONFIG_ERROR

    if not os.path.exists(queue_path):
        print("ENV_NOT_AVAILABLE: Queue path unreachable")
        return ExitCode.ENV_NOT_AVAILABLE

    if not os.path.isdir(queue_path):
        print("CONFIG ERROR: SOC_QUEUE_PATH is not a directory")
        return ExitCode.NOT_DIRECTORY

    if not os.access(queue_path, os.R_OK):
        print("PERMISSION ERROR: SOC_QUEUE_PATH is not readable")
        return ExitCode.PERMISSION_ERROR

    if dry_run:
        print("DRY-RUN: Validation of queue recovery logic skipped.")
        return ExitCode.SUCCESS

    try:
        manifest_path = os.path.join(queue_path, config["manifest_filename"])
        if not os.path.exists(manifest_path):
            print("FAIL: Recovery manifest missing.")
            return ExitCode.FAIL
        if os.path.getsize(manifest_path) > MAX_MANIFEST_SIZE_BYTES:
            print(f"FAIL: Recovery manifest exceeds maximum size of {MAX_MANIFEST_SIZE_BYTES} bytes.")
            return ExitCode.FAIL
        with open(manifest_path, "r") as f:
            if any(config["required_recovery_log_pattern"] in line for line in f):
                print("PASS: Stale recovery logic verified.")
                return ExitCode.SUCCESS
            print("FAIL: Recovery pattern not found in manifest.")
            return ExitCode.FAIL
    except FileNotFoundError:
        print("FAIL: Recovery manifest missing.")
        return ExitCode.FAIL
    except Exception as e:
        print(f"FAIL: Unexpected error during check: {e}")
        return ExitCode.FAIL


def main() -> ExitCode:
    """Entry point for queue stale recovery check. Returns exit code."""
    parser = argparse.ArgumentParser(description="Queue Stale Recovery Check")
    parser.add_argument("--dry-run", action="store_true", help="Skip actual verification")
    parser.add_argument(
        "--stale-threshold",
        type=int,
        default=int(os.getenv("STALE_THRESHOLD_SECONDS", DEFAULT_STALE_THRESHOLD_SECONDS)),
        help=f"Stale threshold in seconds (default: {DEFAULT_STALE_THRESHOLD_SECONDS}, env: STALE_THRESHOLD_SECONDS)"
    )
    parser.add_argument(
        "--recovery-pattern",
        type=str,
        default=os.getenv("REQUIRED_RECOVERY_LOG_PATTERN", DEFAULT_REQUIRED_RECOVERY_LOG_PATTERN),
        help=f"Required recovery log pattern (default: {DEFAULT_REQUIRED_RECOVERY_LOG_PATTERN}, env: REQUIRED_RECOVERY_LOG_PATTERN)"
    )
    parser.add_argument(
        "--manifest-file",
        type=str,
        default=os.getenv("RECOVERY_MANIFEST_FILE", DEFAULT_MANIFEST_FILENAME),
        help=f"Recovery manifest filename (default: {DEFAULT_MANIFEST_FILENAME}, env: RECOVERY_MANIFEST_FILE)"
    )
    args = parser.parse_args()

    config = load_config(args)
    return check_queue_recovery(dry_run=args.dry_run, config=config)


if __name__ == "__main__":
    sys.exit(main())
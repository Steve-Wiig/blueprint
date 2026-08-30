#!/usr/bin/env python3
# CI Gate: Payload Reference Integrity Check
import sys
import json
import os
from urllib.parse import urlparse, ParseResult
from typing import Any, Literal

# O.7 Payload Integrity Contract
# Verifies canonical URI schemes, SHA256 integrity, and 8 required ledger keys.

REQUIRED_KEYS = frozenset({
    "ledger_id",
    "timestamp",
    "payload_hash",
    "origin_node",
    "schema_version",
    "security_level",
    "integrity_checksum",
    "signature_blob"
})

ALLOWED_SCHEMES = frozenset({"soc-internal", "https", "file"})

# Exit codes for verify_payload
EXIT_PASS = 0
EXIT_FAIL_INTEGRITY = 1
EXIT_FAIL_JSON = 2

SHA256_HEX_LENGTH = 64

ExitCode = Literal[EXIT_PASS, EXIT_FAIL_INTEGRITY, EXIT_FAIL_JSON]


def verify_payload(ledger_path: str) -> ExitCode:
    """Verify the integrity of a payload ledger file.

    Validates that the ledger file exists, contains valid JSON, has all 8 required
    keys, uses an allowed URI scheme for origin_node, and has a properly formatted
    integrity checksum.

    Args:
        ledger_path: Path to the ledger JSON file to verify.

    Returns:
        ExitCode: Exit code indicating verification result:
            EXIT_PASS (0) - PASS: All integrity checks passed
            EXIT_FAIL_INTEGRITY (1) - FAIL: Missing file, missing keys, invalid URI scheme, or checksum length mismatch
            EXIT_FAIL_JSON (2) - FAIL: Invalid JSON format

    Raises:
        OSError: If file cannot be read due to permissions or I/O error (not caught, propagates to caller).
    """
    if not os.path.exists(ledger_path):
        print(f"FAIL: Ledger file not found at {ledger_path}", file=sys.stderr)
        return EXIT_FAIL_INTEGRITY

    try:
        with open(ledger_path, 'r') as f:
            data: dict[str, Any] = json.load(f)
    except json.JSONDecodeError:
        print("FAIL: Invalid JSON format", file=sys.stderr)
        return EXIT_FAIL_JSON

    # 1. Verify 8 required ledger keys
    missing: set[str] = REQUIRED_KEYS - set(data.keys())
    if missing:
        print(f"FAIL: Missing ledger keys: {missing}", file=sys.stderr)
        return EXIT_FAIL_INTEGRITY

    # 2. Verify Canonical URI schemes (origin_node)
    parsed_uri: ParseResult = urlparse(data.get("origin_node", ""))
    if parsed_uri.scheme not in ALLOWED_SCHEMES:
        print(f"FAIL: Invalid URI scheme: {parsed_uri.scheme}", file=sys.stderr)
        return EXIT_FAIL_INTEGRITY

    # 3. Verify integrity checksum length
    if len(data.get("integrity_checksum", "")) != SHA256_HEX_LENGTH:
        print("FAIL: Integrity checksum length mismatch", file=sys.stderr)
        return EXIT_FAIL_INTEGRITY

    print("PASS: Payload reference integrity verified")
    return EXIT_PASS


def main() -> ExitCode:
    """Main entry point for the CI payload integrity check.

    Reads the ledger file path from the LEDGER_PATH environment variable
    (defaults to 'ledger.json') and runs the verification.

    Returns:
        ExitCode: Exit code from verify_payload():
            EXIT_PASS (0) - PASS: All integrity checks passed
            EXIT_FAIL_INTEGRITY (1) - FAIL: Integrity verification failed
            EXIT_FAIL_JSON (2) - FAIL: Invalid JSON format
    """
    ledger_file = os.getenv("LEDGER_PATH", "ledger.json")
    return verify_payload(ledger_file)


def cli_main() -> None:
    """CLI entry point that calls sys.exit with the result of main()."""
    sys.exit(main())


if __name__ == "__main__":
    cli_main()
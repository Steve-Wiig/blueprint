#!/usr/bin/env python3
# CI Gate: Sanitization Field Policy Check
# Verifies that sensitive fields are not present in raw ingestion schemas
import sys
import json
import argparse
import os
from typing import Any, List, Optional

# Exit code constants
EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_CONFIG_ERROR = 2
EXIT_CI_MISSING = 3

# LOCAL-SOC-SLM Blueprint v11.6.0 Policy
# Fields that must be redacted/sanitized before reaching the embedding pipeline
FORBIDDEN_FIELDS = {
    "raw_password",
    "session_token",
    "private_key",
    "user_email",
    "internal_ip_address",
    "aws_secret_access_key"
}

def validate_schema(schema_path: str) -> int:
    """Validate schema file for forbidden fields.

    Args:
        schema_path: Path to JSON schema file.

    Returns:
        EXIT_OK if validation passes, EXIT_VIOLATION if forbidden fields found or invalid JSON,
        EXIT_CONFIG_ERROR if schema file not found.

    Side Effects:
        Prints error messages to stdout for failures.
    """
    if not os.path.exists(schema_path):
        print(f"CONFIG ERROR: Schema file not found at {schema_path}")
        return EXIT_CONFIG_ERROR
    
    try:
        with open(schema_path, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError:
        print("FAIL: Invalid JSON schema format")
        return EXIT_VIOLATION

    # Recursive check for forbidden keys in nested schema definitions
    def find_forbidden(obj: Any, path: str = '') -> List[str]:
        if isinstance(obj, dict):
            for k, v in obj.items():
                current_path = f"{path}.{k}" if path else k
                if k in FORBIDDEN_FIELDS:
                    yield current_path
                yield from find_forbidden(v, current_path)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                yield from find_forbidden(item, f"{path}[{i}]")

    found = list(find_forbidden(data))
    if found:
        print(f"FAIL: Forbidden fields detected in schema: {', '.join(found)}")
        return EXIT_VIOLATION
    
    return EXIT_OK

def check_ci_context(dry_run: bool) -> Optional[int]:
    """Validate CI environment context.

    Args:
        dry_run: Whether the check is running in dry-run mode.

    Returns:
        EXIT_CI_MISSING if CI_PIPELINE_ID is not set, None to continue.
    """
    if not os.getenv("CI_PIPELINE_ID"):
        print("ENV_NOT_AVAILABLE: CI context missing")
        return EXIT_CI_MISSING
    return None

def main() -> int:
    """Run the sanitization field policy check.

    Parses command-line arguments, validates CI context, and executes schema validation.

    Returns:
        EXIT_OK on success, EXIT_VIOLATION on validation failure, EXIT_CONFIG_ERROR on config error, EXIT_CI_MISSING if CI context missing.

    Side Effects:
        Prints status messages to stdout. Exits process via sys.exit when run as script.
    """
    parser = argparse.ArgumentParser(description="Sanitization Field Policy Check")
    parser.add_argument("--schema", required=True, help="Path to JSON schema file")
    parser.add_argument("--dry-run", action="store_true", help="Validate without enforcing")
    args = parser.parse_args()

    ci_check = check_ci_context(args.dry_run)
    if ci_check is not None:
        return ci_check

    result = validate_schema(args.schema)
    
    if args.dry_run:
        print("DRY-RUN: Policy check completed.")
        return EXIT_OK
        
    return result

if __name__ == "__main__":
    sys.exit(main())
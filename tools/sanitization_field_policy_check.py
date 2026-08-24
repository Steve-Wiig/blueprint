#!/usr/bin/env python3
# CI Gate: Sanitization Field Policy Check
# Verifies that sensitive fields are not present in raw ingestion schemas
import sys
import json
import argparse
import os
from typing import Any, List, Optional, Set

# Exit code constants
EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_CONFIG_ERROR = 2
EXIT_CI_MISSING = 3

# DEFAULT FORBIDDEN FIELDS - used as fallback when no policy file or env var is provided
DEFAULT_FORBIDDEN_FIELDS = {
    "raw_password",
    "session_token",
    "private_key",
    "user_email",
    "internal_ip_address",
    "aws_secret_access_key"
}

# MAX_SCHEMA_SIZE limits the file size for standard JSON parsing to avoid OOM on large schemas.
# Files exceeding this threshold (100MB) will trigger a warning recommending ijson for streaming parsing.
MAX_SCHEMA_SIZE = 100 * 1024 * 1024  # 100 MB


def load_forbidden_fields(policy_file: Optional[str] = None, env_var: str = "FORBIDDEN_FIELDS") -> Set[str]:
    """Load forbidden fields from a policy file, environment variable, or defaults.

    Args:
        policy_file: Path to JSON file containing a list of forbidden field names.
        env_var: Environment variable name containing JSON list of forbidden fields.

    Returns:
        A set of forbidden field names.
    """
    if policy_file:
        if os.path.exists(policy_file):
            with open(policy_file, 'r') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return set(data)
                if isinstance(data, set):
                    return data
        print(f"WARNING: Policy file not found at {policy_file}, falling back to defaults.")
    env_value = os.getenv(env_var)
    if env_value:
        try:
            data = json.loads(env_value)
            if isinstance(data, list):
                return set(data)
            if isinstance(data, set):
                return data
        except json.JSONDecodeError:
            print(f"WARNING: Environment variable {env_var} contains invalid JSON, falling back to defaults.")
    return DEFAULT_FORBIDDEN_FIELDS


def validate_schema(schema_path: str, forbidden_fields: Optional[Set[str]] = None) -> int:
    """Validate schema file for forbidden fields.

    Args:
        schema_path: Path to JSON schema file.
        forbidden_fields: Set of field names to check against. If None, uses defaults loaded from config.

    Returns:
        EXIT_OK if validation passes, EXIT_VIOLATION if forbidden fields found or invalid JSON,
        EXIT_CONFIG_ERROR if schema file not found.

    Side Effects:
        Prints error messages to stdout for failures.
    """
    if forbidden_fields is None:
        forbidden_fields = load_forbidden_fields()

    if not os.path.exists(schema_path):
        print(f"CONFIG ERROR: Schema file not found at {schema_path}")
        return EXIT_CONFIG_ERROR

    try:
        if os.path.getsize(schema_path) > MAX_SCHEMA_SIZE:
            print(f"WARNING: Schema file is {os.path.getsize(schema_path) // (1024*1024)}MB, "
                  "exceeding the recommended 100MB limit. "
                  "This may cause OOM with standard JSON parsing. "
                  "Consider using ijson for iterative parsing.")
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
                if k in forbidden_fields:
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
    parser.add_argument("--policy-file", help="Path to JSON file containing forbidden fields (overrides env var and defaults)")
    args = parser.parse_args()

    ci_check = check_ci_context(args.dry_run)
    if ci_check is not None:
        return ci_check

    forbidden_fields = load_forbidden_fields(policy_file=args.policy_file)
    result = validate_schema(args.schema, forbidden_fields=forbidden_fields)

    if args.dry_run:
        print("DRY-RUN: Policy check completed.")
        return EXIT_OK

    return result

if __name__ == "__main__":
    sys.exit(main())
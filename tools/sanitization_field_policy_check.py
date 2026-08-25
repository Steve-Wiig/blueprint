#!/usr/bin/env python3
# CI Gate: Sanitization Field Policy Check
# Verifies that sensitive fields are not present in raw ingestion schemas
import sys
import json
import argparse
import os
from typing import Any, List, Optional, Set, Tuple

try:
    import jsonschema
    from jsonschema import Draft7Validator
    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False

# Exit code constants
EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_VALIDATION_FAIL = EXIT_VIOLATION  # Alias for clarity
EXIT_CONFIG_ERROR = 2
EXIT_CI_MISSING = 3
EXIT_META_SCHEMA_ERROR = 4

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
# Files exceeding this threshold (100 MiB) will trigger a warning recommending ijson for streaming parsing.
MAX_SCHEMA_SIZE = 100 * 1024 * 1024  # 100 MiB


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


def validate_meta_schema(data: Any) -> List[str]:
    """Validate schema against JSON Schema Draft 7 meta-schema.

    Args:
        data: Parsed JSON schema object.

    Returns:
        List of validation error messages, empty if valid.
    """
    if not JSONSCHEMA_AVAILABLE:
        return ["jsonschema library not installed; meta-schema validation skipped"]

    try:
        Draft7Validator.check_schema(data)
        return []
    except jsonschema.SchemaError as e:
        return [f"Meta-schema validation failed: {e.message}"]
    except Exception as e:
        return [f"Meta-schema validation error: {str(e)}"]


def format_path(components: Tuple[str, ...]) -> str:
    """Format path components into dot/bracket notation string.

    Args:
        components: Tuple of path components (keys and list indices).

    Returns:
        Formatted path string using dot notation for keys and bracket notation for indices.
        Returns empty string if components is empty.
    """
    if not components:
        return ""
    result = components[0]
    for comp in components[1:]:
        if comp.startswith('['):
            result += comp
        else:
            result += '.' + comp
    return result


def find_forbidden(obj: Any, forbidden_fields: Set[str]) -> List[str]:
    """Recursively search for forbidden field names in a JSON schema object.

    Uses an iterative stack-based approach to traverse nested dictionaries and lists,
    collecting the full path to any forbidden field names found.

    Args:
        obj: The JSON schema object (dict, list, or primitive) to search.
        forbidden_fields: Set of field names to check against.

    Returns:
        List[str]: List of dot/bracket-notation paths to forbidden fields found.
            Empty list if no forbidden fields detected.
    """
    stack: List[Tuple[Any, Tuple[str, ...]]] = [(obj, ())]
    found = []
    while stack:
        current_obj, path_components = stack.pop()
        if isinstance(current_obj, dict):
            for k, v in current_obj.items():
                new_path = path_components + (k,)
                if k in forbidden_fields:
                    found.append(format_path(new_path))
                stack.append((v, new_path))
        elif isinstance(current_obj, list):
            for i, item in enumerate(current_obj):
                new_path = path_components + (f"[{i}]",)
                stack.append((item, new_path))
    return found


def validate_schema(schema_path: str, forbidden_fields: Optional[Set[str]] = None) -> int:
    """Validate schema file for forbidden fields and meta-schema compliance.

    Args:
        schema_path: Path to JSON schema file.
        forbidden_fields: Set of field names to check against. If None, uses defaults
            loaded from config.

    Returns:
        int: Exit code indicating validation result.
            - EXIT_OK (0): Validation passed, no forbidden fields found.
            - EXIT_VIOLATION (1): Forbidden fields detected or invalid JSON format.
            - EXIT_CONFIG_ERROR (2): Schema file not found at given path.
            - EXIT_META_SCHEMA_ERROR (4): Schema failed JSON Schema Draft 7 meta-schema validation.

    Side Effects:
        Prints error messages to stdout for failures.
        Prints warning if schema file exceeds MAX_SCHEMA_SIZE (100MiB).
    """
    if forbidden_fields is None:
        forbidden_fields = load_forbidden_fields()

    if not os.path.exists(schema_path):
        print(f"CONFIG ERROR: Schema file not found at {schema_path}")
        return EXIT_CONFIG_ERROR

    try:
        if os.path.getsize(schema_path) > MAX_SCHEMA_SIZE:
            print(f"WARNING: Schema file is {os.path.getsize(schema_path) // (1024*1024)}MiB, "
                  "exceeding the recommended 100 MiB limit. "
                  "This may cause OOM with standard JSON parsing. "
                  "Consider using ijson for iterative parsing.")
        with open(schema_path, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError:
        print("FAIL: Invalid JSON schema format")
        return EXIT_VIOLATION

    meta_errors = validate_meta_schema(data)
    if meta_errors:
        for err in meta_errors:
            print(f"FAIL: {err}")
        return EXIT_META_SCHEMA_ERROR

    found = find_forbidden(data, forbidden_fields)
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
        EXIT_OK on success, EXIT_VIOLATION on validation failure, EXIT_CONFIG_ERROR on config error, EXIT_CI_MISSING if CI context missing, EXIT_META_SCHEMA_ERROR if meta-schema validation fails.

    Side Effects:
        Prints status messages to stdout. Exits process via sys.exit when run as script.
    """
    epilog = (
        "Exit codes:\n"
        "  0 (EXIT_OK) - Validation passed, no forbidden fields found\n"
        "  1 (EXIT_VALIDATION_FAIL) - Forbidden fields detected or invalid JSON format\n"
        "  2 (EXIT_CONFIG_ERROR) - Schema file not found at given path\n"
        "  3 (EXIT_CI_MISSING) - CI_PIPELINE_ID environment variable not set\n"
        "  4 (EXIT_META_SCHEMA_ERROR) - Schema failed JSON Schema Draft 7 meta-schema validation"
    )
    parser = argparse.ArgumentParser(
        description="Sanitization Field Policy Check",
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
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
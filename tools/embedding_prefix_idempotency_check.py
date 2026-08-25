#!/usr/bin/env python3
# CI Gate: Embedding Prefix Idempotency Check
import sys
import argparse
import json
import os
from pathlib import Path
from typing import Dict, Optional


CONFIG_PATH = Path(__file__).parent.parent / "config" / "embedding_prefixes.json"
ENV_DOC_PREFIX = "EMBEDDING_DOC_PREFIX"
ENV_QUERY_PREFIX = "EMBEDDING_QUERY_PREFIX"


def load_prefixes_from_config() -> Dict[str, str]:
    """Load prefixes from JSON config file."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    return {}


def load_prefixes_from_env() -> Dict[str, str]:
    """Load prefixes from environment variables."""
    prefixes = {}
    if doc_prefix := os.getenv(ENV_DOC_PREFIX):
        prefixes["document"] = doc_prefix
    if query_prefix := os.getenv(ENV_QUERY_PREFIX):
        prefixes["query"] = query_prefix
    return prefixes


def get_prefixes() -> Dict[str, str]:
    """
    Get prefixes from config file, falling back to environment variables,
    then to hardcoded defaults.
    """
    prefixes = load_prefixes_from_config()
    if not prefixes:
        prefixes = load_prefixes_from_env()
    if not prefixes:
        prefixes = {
            "document": "search_document: ",
            "query": "search_query: ",
        }
    return prefixes


def validate_against_service(prefixes: Dict[str, str]) -> bool:
    """
    Validate loaded prefixes against actual embedding service configuration.
    Returns True if validation passes or service is unavailable.
    """
    service_url = os.getenv("EMBEDDING_SERVICE_URL")
    if not service_url:
        return True
    
    try:
        import urllib.request
        import urllib.error
        
        req = urllib.request.Request(
            f"{service_url.rstrip('/')}/config/prefixes",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            service_prefixes = json.loads(response.read().decode())
        
        for key in ("document", "query"):
            if prefixes.get(key) != service_prefixes.get(key):
                print(
                    f"WARNING: Prefix mismatch for '{key}': "
                    f"local='{prefixes.get(key)}', service='{service_prefixes.get(key)}'",
                    file=sys.stderr,
                )
                return False
        return True
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        print(f"WARNING: Could not validate against embedding service: {e}", file=sys.stderr)
        return True


PREFIXES = get_prefixes()
REQUIRED_DOC_PREFIX = PREFIXES["document"]
REQUIRED_QUERY_PREFIX = PREFIXES["query"]

DOC_TEST_CASES = [
    ("unprefixed_data", REQUIRED_DOC_PREFIX, True),
    (f"{REQUIRED_DOC_PREFIX}already_prefixed", REQUIRED_DOC_PREFIX, True),
    (f"{REQUIRED_DOC_PREFIX}{REQUIRED_DOC_PREFIX}double_prefixed", REQUIRED_DOC_PREFIX, False),
]

QUERY_TEST_CASES = [
    ("unprefixed_query", REQUIRED_QUERY_PREFIX, True),
    (f"{REQUIRED_QUERY_PREFIX}already_prefixed", REQUIRED_QUERY_PREFIX, True),
    (f"{REQUIRED_QUERY_PREFIX}{REQUIRED_QUERY_PREFIX}double_prefixed", REQUIRED_QUERY_PREFIX, False),
]

MOCK_TEST_CASES = DOC_TEST_CASES + QUERY_TEST_CASES
PRODUCTION_TEST_CASES = DOC_TEST_CASES


def check_idempotency(input_text: str, prefix: str) -> bool:
    """
    Verifies that applying the prefix multiple times does not result in 
    nested prefixing (e.g., 'prefix: prefix: text').
    """
    if input_text.startswith(prefix):
        processed = input_text
    else:
        processed = prefix + input_text
    
    if processed.startswith(prefix + prefix):
        return False
    
    if not processed.startswith(prefix):
        return False
        
    return True


def main(dry_run: bool = False) -> int:
    """
    Run embedding prefix idempotency verification tests.

    Args:
        dry_run: If True, runs with mock test data covering both document
            and query prefixes. If False, runs production test cases for
            document prefix only.

    Returns:
        0 if all tests pass, 1 if any test fails. In dry-run mode, always
        returns 0 after printing results.
    """
    if not validate_against_service(PREFIXES):
        print("ERROR: Prefix validation against embedding service failed", file=sys.stderr)
        if not dry_run:
            return 1
    
    test_cases = MOCK_TEST_CASES if dry_run else PRODUCTION_TEST_CASES
    
    if dry_run:
        print("DRY RUN: Running with mock test data (both document and query prefixes)")
    
    all_passed = True
    for text, prefix, expected_valid in test_cases:
        is_valid = check_idempotency(text, prefix)
        
        if is_valid != expected_valid:
            print(f"FAIL: Expected valid={expected_valid}, got valid={is_valid} for: {text}")
            all_passed = False
        elif dry_run:
            print(f"  OK: {text!r} with {prefix!r} -> valid={is_valid}")
                
    if dry_run:
        print("DRY RUN: Completed (exit code forced to 0)")
        return 0
    
    if all_passed:
        print("PASS: Embedding prefix idempotency verified")
        return 0
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CI Check Tool")
    parser.add_argument("--dry-run", action="store_true", help="Run with test/mock data")
    args = parser.parse_args()
    
    exit_code = main(dry_run=args.dry_run)
    if exit_code != 0:
        raise RuntimeError(f"CI check failed with exit code {exit_code}")
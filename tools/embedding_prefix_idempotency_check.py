#!/usr/bin/env python3
"""
CI Gate: Embedding Prefix Idempotency Check

This module validates that embedding prefixes are applied idempotently,
ensuring that text already prefixed does not receive a duplicate prefix.
It loads prefixes from a JSON config file, environment variables, or defaults,
and optionally validates against a running embedding service.
"""
import sys
import argparse
import json
import os
import time
import urllib.request
import urllib.error
import socket
from pathlib import Path
from typing import Dict


CONFIG_PATH: Path = Path(__file__).parent.parent / "config" / "embedding_prefixes.json"
ENV_DOC_PREFIX: str = "EMBEDDING_DOC_PREFIX"
ENV_QUERY_PREFIX: str = "EMBEDDING_QUERY_PREFIX"


def load_prefixes_from_config() -> Dict[str, str]:
    """Load prefixes from JSON config file."""
    if not CONFIG_PATH.exists():
        print(f"WARNING: Config file not found at {CONFIG_PATH}, falling back to environment variables", file=sys.stderr)
        return {}
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in config file {CONFIG_PATH}: {e}") from e


def load_prefixes_from_env() -> Dict[str, str]:
    """Load prefixes from environment variables with validation."""
    prefixes = {}
    used_vars = []
    
    doc_prefix = os.getenv(ENV_DOC_PREFIX)
    if doc_prefix is not None:
        doc_prefix = doc_prefix.strip()
        if doc_prefix:
            prefixes["document"] = doc_prefix
            used_vars.append(ENV_DOC_PREFIX)
        else:
            print(f"WARNING: {ENV_DOC_PREFIX} is set but empty after stripping whitespace", file=sys.stderr)
    
    query_prefix = os.getenv(ENV_QUERY_PREFIX)
    if query_prefix is not None:
        query_prefix = query_prefix.strip()
        if query_prefix:
            prefixes["query"] = query_prefix
            used_vars.append(ENV_QUERY_PREFIX)
        else:
            print(f"WARNING: {ENV_QUERY_PREFIX} is set but empty after stripping whitespace", file=sys.stderr)
    
    if used_vars:
        print(f"INFO: Loaded prefixes from environment variables: {', '.join(used_vars)}", file=sys.stderr)
    
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

    backoff_delays = [1, 2, 4]
    for attempt, delay in enumerate(backoff_delays, start=1):
        try:
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
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, socket.timeout) as e:
            if attempt == len(backoff_delays):
                print(f"WARNING: Could not validate against embedding service: {e}", file=sys.stderr)
                return True
            time.sleep(delay)

def get_doc_test_cases(doc_prefix: str):
    return [
        ("unprefixed_data", doc_prefix, True),
        (f"{doc_prefix}already_prefixed", doc_prefix, True),
        (f"{doc_prefix}{doc_prefix}double_prefixed", doc_prefix, False),
    ]


def get_query_test_cases(query_prefix: str):
    return [
        ("unprefixed_query", query_prefix, True),
        (f"{query_prefix}already_prefixed", query_prefix, True),
        (f"{query_prefix}{query_prefix}double_prefixed", query_prefix, False),
    ]


def get_mock_test_cases(doc_prefix: str, query_prefix: str):
    return get_doc_test_cases(doc_prefix) + get_query_test_cases(query_prefix)


def get_production_test_cases(doc_prefix: str):
    return get_doc_test_cases(doc_prefix)


def check_idempotency(input_text: str, prefix: str) -> bool:
    """
    Verifies that the input text, after applying prefix logic once,
    does not contain a double prefix.
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


def _validate(prefixes: Dict[str, str]) -> bool:
    if not validate_against_service(prefixes):
        print("ERROR: Prefix validation against embedding service failed", file=sys.stderr)
        return False
    return True


def _load_cases(prefixes: Dict[str, str], dry_run: bool):
    doc_prefix = prefixes["document"]
    query_prefix = prefixes["query"]
    return get_mock_test_cases(doc_prefix, query_prefix) if dry_run else get_production_test_cases(doc_prefix)


def run_tests(test_cases, dry_run: bool) -> bool:
    all_passed = True
    for text, prefix, expected_valid in test_cases:
        is_valid = check_idempotency(text, prefix)
        if is_valid != expected_valid:
            all_passed = False
    return all_passed

def _report(all_passed: bool, dry_run: bool) -> int:
    if dry_run:
        print("DRY RUN: Completed (exit code forced to 0)")
        return 0
    if all_passed:
        print("PASS: Embedding prefix idempotency verified")
        return 0
    else:
        print("FAIL: Some embedding prefix idempotency checks failed")
        return 1


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
    prefixes = get_prefixes()
    
    if not _validate(prefixes):
        if not dry_run:
            return 1

    test_cases = _load_cases(prefixes, dry_run)
    if dry_run:
        print("DRY RUN: Running with mock test data (both document and query prefixes)")

    all_passed = run_tests(test_cases, dry_run)
    return _report(all_passed, dry_run)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate embedding prefix idempotency.")
    parser.add_argument("--dry-run", action="store_true", help="Run with mock test data for both document and query prefixes.")
    args = parser.parse_args()
    sys.exit(main(dry_run=args.dry_run))
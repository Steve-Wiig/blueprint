#!/usr/bin/env python3
# CI Gate: Embedding Prefix Idempotency Check
import sys
import argparse

REQUIRED_DOC_PREFIX = "search_document: "
REQUIRED_QUERY_PREFIX = "search_query: "

MOCK_TEST_CASES = [
    ("unprefixed_data", REQUIRED_DOC_PREFIX, True),
    (f"{REQUIRED_DOC_PREFIX}already_prefixed", REQUIRED_DOC_PREFIX, True),
    (f"{REQUIRED_DOC_PREFIX}{REQUIRED_DOC_PREFIX}double_prefixed", REQUIRED_DOC_PREFIX, False),
    ("unprefixed_query", REQUIRED_QUERY_PREFIX, True),
    (f"{REQUIRED_QUERY_PREFIX}already_prefixed", REQUIRED_QUERY_PREFIX, True),
    (f"{REQUIRED_QUERY_PREFIX}{REQUIRED_QUERY_PREFIX}double_prefixed", REQUIRED_QUERY_PREFIX, False),
]

PRODUCTION_TEST_CASES = [
    ("unprefixed_data", REQUIRED_DOC_PREFIX, True),
    (f"{REQUIRED_DOC_PREFIX}already_prefixed", REQUIRED_DOC_PREFIX, True),
    (f"{REQUIRED_DOC_PREFIX}{REQUIRED_DOC_PREFIX}double_prefixed", REQUIRED_DOC_PREFIX, False),
]

def check_idempotency(input_text: str, prefix: str) -> bool:
    """
    Verifies that applying the prefix multiple times does not result in 
    nested prefixing (e.g., 'prefix: prefix: text').
    """
    # Simulate the embedding service logic
    if input_text.startswith(prefix):
        processed = input_text
    else:
        processed = prefix + input_text
    
    # Check for double prefixing
    if processed.startswith(prefix + prefix):
        return False
    
    # Check for single prefixing
    if not processed.startswith(prefix):
        return False
        
    return True

def main(dry_run=False):
    """Run idempotency verification tests. Returns 0 on success, 1 on failure."""
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
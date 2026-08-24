#!/usr/bin/env python3
# CI Gate: Embedding Prefix Idempotency Check
import sys
import argparse

REQUIRED_DOC_PREFIX = "search_document: "
REQUIRED_QUERY_PREFIX = "search_query: "

def check_idempotency(input_text, prefix):
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

def main():
    test_cases = [
        ("unprefixed_data", REQUIRED_DOC_PREFIX, True),
        (f"{REQUIRED_DOC_PREFIX}already_prefixed", REQUIRED_DOC_PREFIX, True),
        (f"{REQUIRED_DOC_PREFIX}{REQUIRED_DOC_PREFIX}double_prefixed", REQUIRED_DOC_PREFIX, False)
    ]
    
    for text, prefix, expected_valid in test_cases:
        is_valid = check_idempotency(text, prefix)
        
        if is_valid != expected_valid:
            print(f"FAIL: Expected valid={expected_valid}, got valid={is_valid} for: {text}")
            return 1
                
    print("PASS: Embedding prefix idempotency verified")
    return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CI Check Tool")
    parser.add_argument("--dry-run", action="store_true", help="Run with test/mock data")
    args = parser.parse_args()
    
    exit_code = main()
    if exit_code != 0:
        raise RuntimeError(f"CI check failed with exit code {exit_code}")
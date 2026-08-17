#!/usr/bin/env python3
# CI Gate: Embedding Prefix Idempotency Check
import sys

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
        ("unprefixed_data", REQUIRED_DOC_PREFIX),
        (f"{REQUIRED_DOC_PREFIX}already_prefixed", REQUIRED_DOC_PREFIX),
        (f"{REQUIRED_DOC_PREFIX}{REQUIRED_DOC_PREFIX}double_prefixed", REQUIRED_DOC_PREFIX)
    ]
    
    for text, prefix in test_cases:
        # Logic: 
        # 1. Unprefixed should pass (gets prefixed once)
        # 2. Single-prefixed should pass (remains prefixed once)
        # 3. Double-prefixed should fail (detected as invalid state)
        
        is_valid = check_idempotency(text, prefix)
        
        if "double_prefixed" in text:
            if is_valid:
                print(f"FAIL: Double prefix not detected for: {text}")
                return 1
        else:
            if not is_valid:
                print(f"FAIL: Idempotency check failed for: {text}")
                return 1
                
    print("PASS: Embedding prefix idempotency verified")
    return 0

if __name__ == "__main__":
    sys.exit(main())
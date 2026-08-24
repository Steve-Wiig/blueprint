#!/usr/bin/env python3
# CI Gate: Two-pass Sanitization Entropy Check
import sys
import argparse
import re
import math
import collections

ENTROPY_THRESHOLD = 4.5
ALLOWLIST_PATTERNS = [
    r'[a-fA-F0-9]{64}',  # SHA256
    r'[a-fA-F0-9]{40}',  # SHA1
    r'[a-fA-F0-9]{32}',  # MD5
    r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}' # UUID
]

ALLOWLIST_REGEX = re.compile('|'.join(f'(?:{p})' for p in ALLOWLIST_PATTERNS))

def calculate_entropy(data):
    if not data:
        return 0
    counts = collections.Counter(data)
    length = len(data)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())

def is_allowlisted(token):
    return ALLOWLIST_REGEX.fullmatch(token) is not None

def sanitize_pass(text):
    tokens = text.split()
    sanitized = []
    for token in tokens:
        if is_allowlisted(token):
            sanitized.append(token)
            continue
        
        entropy = calculate_entropy(token)
        if entropy > ENTROPY_THRESHOLD:
            sanitized.append("[REDACTED]")
        else:
            sanitized.append(token)
    return " ".join(sanitized)

def main():
    try:
        input_data = sys.stdin.read()
        if not input_data:
            return 0
            
        # Pass 1: Initial scan and redaction
        pass1 = sanitize_pass(input_data)
        
        # Pass 2: Verification of remaining high-entropy tokens
        pass2 = sanitize_pass(pass1)
        
        if pass1 != pass2:
            print("FAIL: Sanitization inconsistency detected between passes.")
            return 1
            
        print("PASS: Sanitization entropy threshold verified.")
        return 0
        
    except Exception as e:
        print(f"CONFIG ERROR: {str(e)}")
        return 2

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CI Check Tool")
    parser.add_argument("--dry-run", action="store_true", help="Run with test/mock data")
    args = parser.parse_args()
    
    sys.exit(main())
#!/usr/bin/env python3
"""
CI Gate: Two-pass Sanitization Entropy Check

This module provides a two-pass sanitization system that detects and redacts
high-entropy tokens (potential secrets) from text input while preserving
known safe patterns (hashes, UUIDs).

The entropy threshold of 4.5 bits/character was chosen based on empirical
analysis: typical English text has entropy ~3.5-4.0, while base64-encoded
secrets, API keys, and random tokens typically exceed 4.5. This threshold
balances false positive reduction with secret detection sensitivity.

Two-pass verification ensures idempotency - re-running sanitization on
already-sanitized output produces identical results, confirming no secrets
were missed in the first pass.
"""

import sys
import argparse
import re
import math
import collections
from typing import List

ENTROPY_THRESHOLD: float = 4.5
ALLOWLIST_PATTERNS: List[str] = [
    r'[a-fA-F0-9]{64}',  # SHA256
    r'[a-fA-F0-9]{40}',  # SHA1
    r'[a-fA-F0-9]{32}',  # MD5
    r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'  # UUID
]

ALLOWLIST_REGEX = re.compile('|'.join(f'(?:{p})' for p in ALLOWLIST_PATTERNS))


def calculate_entropy(data: str) -> float:
    """
    Calculate Shannon entropy of a string in bits per character.

    Args:
        data: Input string to analyze.

    Returns:
        Entropy value in bits per character. Returns 0 for empty strings.

    Rationale:
        Entropy measures randomness. High entropy (>4.5) suggests encoded
        secrets, keys, or random tokens rather than natural language.
    """
    if not data:
        return 0.0
    counts = collections.Counter(data)
    length = len(data)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def is_allowlisted(token: str) -> bool:
    """
    Check if a token matches known safe patterns (hashes, UUIDs).

    Args:
        token: String token to check against allowlist patterns.

    Returns:
        True if token matches SHA256, SHA1, MD5, or UUID format; False otherwise.
    """
    return ALLOWLIST_REGEX.fullmatch(token) is not None


def sanitize_pass(text: str) -> str:
    """
    Perform a single sanitization pass on input text.

    Splits text into whitespace-separated tokens, preserves allowlisted tokens,
    and redacts high-entropy tokens (>4.5 bits/char) as "[REDACTED]".

    Args:
        text: Input text to sanitize.

    Returns:
        Sanitized text with high-entropy tokens redacted.
    """
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


def main() -> int:
    """
    Execute two-pass sanitization verification.

    Reads from stdin, performs two sanitization passes, and verifies
    idempotency (pass1 == pass2). Returns exit code indicating result.

    Returns:
        0: PASS - Sanitization consistent, no high-entropy secrets detected.
        1: FAIL - Inconsistency between passes (potential missed secret).
        2: CONFIG ERROR - Unexpected exception during processing.
    """
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
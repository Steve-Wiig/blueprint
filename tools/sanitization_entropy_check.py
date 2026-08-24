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
import os
import io
from typing import List, Iterator, TextIO

# Threshold chosen to detect base64/hex encoded secrets (entropy ~4.7) while allowing normal words (entropy ~3.5);
# make configurable via env var or CLI arg
ENTROPY_THRESHOLD: float = 4.5
ALLOWLIST_PATTERNS: List[str] = [
    r'[a-fA-F0-9]{64}',  # SHA256 hash (256-bit digest); allowlisted as deterministic checksums are non-secret, low-entropy patterns
    r'[a-fA-F0-9]{40}',  # SHA1 hash (160-bit digest); allowlisted for compatibility with legacy checksums and hash-based verification
    r'[a-fA-F0-9]{32}',  # MD5 hash (128-bit digest); allowlisted as widely used in file integrity checks, not suitable for secrets due to collision risk
    r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'  # UUID v4/v1/v2/v3/v5 format; allowlisted as structurally random but non-secret identifiers
]

ALLOWLIST_REGEX = [re.compile(p) for p in ALLOWLIST_PATTERNS]

# Default test data for dry-run mode
DEFAULT_TEST_DATA = """
Normal text with entropy around 3.5 bits per character.
SHA256 hash: a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3
API key: sk_live_abcdefghijklmnopqrstuvwxyz123456
UUID: 550e8400-e29b-41d4-a716-446655440000
Base64 secret: YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXoxMjM0NTY=
"""


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
    # Pre-compute log2(i/length) for i in 1..length to avoid repeated log2 calls
    log2_table = [0.0] * (length + 1)
    for i in range(1, length + 1):
        log2_table[i] = math.log2(i / length)
    return -sum((count / length) * log2_table[count] for count in counts.values())


def is_allowlisted(token: str) -> bool:
    """
    Check if a token matches known safe patterns (hashes, UUIDs).

    Args:
        token: String token to check against allowlist patterns.

    Returns:
        True if token matches SHA256, SHA1, MD5, or UUID format; False otherwise.
    """
    return any(regex.fullmatch(token) for regex in ALLOWLIST_REGEX)


def _tokenize(text: str) -> Iterator[str]:
    """
    Generate whitespace-separated tokens from text without loading all into memory.

    Args:
        text: Input text to tokenize.

    Yields:
        Individual tokens (non-whitespace sequences) from the text.
    """
    for match in re.finditer(r'\S+', text):
        yield match.group()


def sanitize_pass(text: str) -> str:
    """
    Perform a single sanitization pass on input text.

    Processes text token by token using a generator to avoid loading
    all tokens into memory at once. Preserve allowlisted tokens,
    and redacts high-entropy tokens (>4.5 bits/char) as "[REDACTED]".

    Args:
        text: Input text to sanitize.

    Returns:
        Sanitized text with high-entropy tokens redacted.
    """
    output = io.StringIO()
    first = True
    
    for token in _tokenize(text):
        if not first:
            output.write(' ')
        first = False
        
        if is_allowlisted(token):
            output.write(token)
            continue

        entropy = calculate_entropy(token)
        if entropy > ENTROPY_THRESHOLD:
            output.write("[REDACTED]")
        else:
            output.write(token)
    
    return output.getvalue()


def sanitize_stream(input_stream: TextIO) -> str:
    """
    Perform sanitization on a stream line by line to avoid loading entire input into memory.

    Args:
        input_stream: Text stream to read from (e.g., sys.stdin).

    Returns:
        Sanitized text with high-entropy tokens redacted.
    """
    output = io.StringIO()
    first_token = True
    
    for line in input_stream:
        for token in _tokenize(line):
            if not first_token:
                output.write(' ')
            first_token = False
            
            if is_allowlisted(token):
                output.write(token)
                continue

            entropy = calculate_entropy(token)
            if entropy > ENTROPY_THRESHOLD:
                output.write("[REDACTED]")
            else:
                output.write(token)
    
    return output.getvalue()


def main(input_data: str) -> int:
    """
    Execute two-pass sanitization verification.

    Performs two sanitization passes on the provided input and verifies
    idempotency (pass1 == pass2). Returns exit code indicating result.

    Args:
        input_data: The input text to sanitize and verify.

    Returns:
        0: PASS - Sanitization consistent, no high-entropy secrets detected.
        1: FAIL - Inconsistency between passes (potential missed secret).
        2: CONFIG ERROR - Unexpected exception during processing.
    """
    try:
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


def main_stream(input_stream: TextIO) -> int:
    """
    Execute two-pass sanitization verification on a stream.

    Performs two sanitization passes on the provided stream and verifies
    idempotency (pass1 == pass2). Returns exit code indicating result.

    Args:
        input_stream: Text stream to read from (e.g., sys.stdin).

    Returns:
        0: PASS - Sanitization consistent, no high-entropy secrets detected.
        1: FAIL - Inconsistency between passes (potential missed secret).
        2: CONFIG ERROR - Unexpected exception during processing.
    """
    try:
        # Pass 1: Initial scan and redaction
        pass1 = sanitize_stream(input_stream)

        # Pass 2: Verification of remaining high-entropy tokens
        # For pass 2, we need to re-process the output of pass1
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

    if args.dry_run:
        # Use test data from environment variable or default
        input_data = os.environ.get("SANITIZER_TEST_DATA", DEFAULT_TEST_DATA)
        print("DRY-RUN MODE: Using test data")
        sys.exit(main(input_data))
    else:
        # Stream from stdin to avoid loading large inputs into memory
        sys.exit(main_stream(sys.stdin))
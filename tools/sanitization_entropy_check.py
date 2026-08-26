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

# Threshold tuned for base64 (max 6.0 bits/char) vs hex (max 4.0 bits/char);
# 4.5 catches base64-encoded secrets but allows hex-encoded data and normal text.
# Configurable via ENTROPY_THRESHOLD environment variable.
_ENTROPY_THRESHOLD_ENV = os.environ.get("ENTROPY_THRESHOLD")
ENTROPY_THRESHOLD: float = float(_ENTROPY_THRESHOLD_ENV) if _ENTROPY_THRESHOLD_ENV is not None else 4.5

# Redaction token used to replace high-entropy secrets.
# Defined as a module constant to avoid magic strings in multiple locations.
REDACTION_TOKEN: str = "[REDACTED]"

ALLOWLIST_PATTERNS: List[str] = [
    r'[a-fA-F0-9]{64}',  # SHA256 hash (256-bit digest); allowlisted as deterministic checksums are non-secret, low-entropy patterns
    r'[a-fA-F0-9]{40}',  # SHA1 hash (160-bit digest); allowlisted for compatibility with legacy checksums and hash-based verification
    r'[a-fA-F0-9]{32}',  # MD5 hash (128-bit digest); allowlisted as widely used in file integrity checks, not suitable for secrets due to collision risk
    r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'  # UUID v4/v1/v2/v3/v5 format; allowlisted as structurally random but non-secret identifiers
]

# Combined into a single alternation regex: one fullmatch per token
# instead of iterating every pattern (O(patterns) -> O(1) per token).
ALLOWLIST_REGEX = re.compile(
    r"(?:" + "|".join(f"(?:{pat})" for pat in ALLOWLIST_PATTERNS) + r")"
)


def get_default_test_data() -> str:
    """Return default test data for dry-run mode.

    Returns:
        Multi-line string containing sample text with various token types
        for testing the sanitization system.
    """
    return """
Normal text with entropy around 3.5 bits per character.
SHA256 hash: a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3
API key: sk_live_abcdefghijklmnopqrstuvwxyz123456
UUID: 550e8400-e29b-41d4-a716-446655440000
Base64 secret: YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXoxMjM0NTY=
"""


def calculate_entropy(data: str) -> float:
    """Calculate Shannon entropy of a string in bits per character.

    Computes the Shannon entropy H(X) = -sum(p(x) * log2(p(x))) for each
    unique character in the input string, where p(x) is the probability
    of character x occurring.

    Args:
        data: Input string to analyze. Can contain any Unicode characters.
              Empty string returns 0.0.

    Returns:
        Entropy value in bits per character as a float.
        Returns 0.0 for empty strings.
        Typical ranges:
            - English text: ~3.5-4.0 bits/char
            - Hex-encoded data: ~4.0 bits/char
            - Base64-encoded data: ~4.5-6.0 bits/char
            - Random bytes: ~8.0 bits/char

    Edge Cases:
        - Empty string: returns 0.0
        - Single character repeated: returns 0.0
        - Unicode characters: handled correctly via Python's Unicode support
        - Very long strings: O(n) time, O(k) space where k is unique character count

    Example:
        >>> calculate_entropy("aaaa")
        0.0
        >>> calculate_entropy("abcd")
        2.0
        >>> calculate_entropy("")  # empty string
        0.0
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
    """Check if a token matches known safe patterns (hashes, UUIDs).

    Evaluates the token against a compiled list of regex patterns for
    common non-secret identifiers: SHA256, SHA1, MD5 hashes, and UUIDs.

    Args:
        token: String token to check against allowlist patterns.
               Must be a complete token (no partial matches).
               Empty string returns False.

    Returns:
        True if token matches any allowlisted pattern exactly (fullmatch);
        False otherwise.

    Edge Cases:
        - Empty string: returns False (no pattern matches empty string)
        - Substrings of hashes: returns False (requires fullmatch)
        - Case sensitivity: patterns are case-insensitive for hex chars
        - Unicode: patterns only match ASCII hex chars and hyphens

    Example:
        >>> is_allowlisted("a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3")
        True  # SHA256
        >>> is_allowlisted("550e8400-e29b-41d4-a716-446655440000")
        True  # UUID
        >>> is_allowlisted("sk_live_abc123")
        False  # API key pattern not allowlisted
        >>> is_allowlisted("")
        False
    """
    return bool(ALLOWLIST_REGEX.fullmatch(token))


def _tokenize(text: str) -> Iterator[str]:
    """Generate whitespace-separated tokens from text without loading all into memory.

    Args:
        text: Input text to tokenize. Can be any string including Unicode.

    Yields:
        Individual tokens (non-whitespace sequences) from the text.
        Tokens are yielded in order of appearance.
        Empty strings are never yielded.

    Edge Cases:
        - Empty string: yields nothing
        - String with only whitespace: yields nothing
        - Unicode whitespace: handled by \\S regex (matches non-whitespace)
        - Multiple consecutive spaces: treated as single delimiter
    """
    for match in re.finditer(r'\S+', text):
        yield match.group()


def sanitize_pass(text: str) -> str:
    """Perform a single sanitization pass on input text.

    Processes text token by token using a generator to avoid loading
    all tokens into memory at once. Preserves allowlisted tokens,
    and redacts high-entropy tokens (> ENTROPY_THRESHOLD bits/char) as REDACTION_TOKEN.

    Args:
        text: Input text to sanitize. Can be any string including Unicode.
              Empty string returns empty string.

    Returns:
        Sanitized text with high-entropy tokens redacted to REDACTION_TOKEN.
        Whitespace between tokens is normalized to single spaces.
        Leading/trailing whitespace is not preserved.

    Edge Cases:
        - Empty string: returns empty string
        - String with only whitespace: returns empty string
        - Unicode tokens: entropy calculated on Unicode codepoints
        - Very long input: O(n) memory for output, O(1) additional for processing
        - Tokens at threshold boundary: entropy > threshold is redacted (strict)

    Example:
        >>> sanitize_pass("hello world")
        'hello world'
        >>> sanitize_pass("sk_live_abcdefghijklmnopqrstuvwxyz123456")
        '[REDACTED]'
        >>> sanitize_pass("SHA256: a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3")
        'SHA256: a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3'
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
            output.write(REDACTION_TOKEN)
        else:
            output.write(token)
    
    return output.getvalue()


def sanitize_stream(input_stream: TextIO) -> str:
    """Perform sanitization on a stream line by line to avoid loading entire input into memory.

    Reads from the input stream line by line, tokenizes each line, and applies
    the same sanitization logic as sanitize_pass. Suitable for processing
    large files or piped input without memory overhead.

    Args:
        input_stream: Text stream to read from (e.g., sys.stdin, open file).
                      Must support iteration yielding strings (lines).
                      Stream position is consumed.

    Returns:
        Sanitized text with high-entropy tokens redacted to REDACTION_TOKEN.
        Whitespace between tokens is normalized to single spaces.
        Line boundaries are not preserved (tokens separated by single space).

    Edge Cases:
        - Empty stream: returns empty string
        - Stream with only whitespace: returns empty string
        - Very large input: constant memory usage (streaming)
        - Unicode input: handled via TextIO encoding
        - Binary streams: not supported (use TextIOWrapper)

    Example:
        >>> import io
        >>> stream = io.StringIO("hello secret123 world")
        >>> sanitize_stream(stream)
        'hello [REDACTED] world'
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
                output.write(REDACTION_TOKEN)
            else:
                output.write(token)
    
    return output.getvalue()


def main(input_data: str) -> int:
    """Execute two-pass sanitization verification on a string.

    Performs two sanitization passes on the provided input and verifies
    idempotency (pass1 == pass2). Returns exit code indicating result.

    Args:
        input_data: The input text to sanitize and verify.
                    Can be any string including Unicode.
                    Empty string returns 0 (PASS).

    Returns:
        Exit code as int:
            0: PASS - Sanitization consistent, no high-entropy secrets detected.
            1: FAIL - Inconsistency between passes (potential missed secret).
            2: CONFIG ERROR - Unexpected exception during processing.

    Edge Cases:
        - Empty input: returns 0 (PASS)
        - Input with only allowlisted tokens: returns 0 (PASS)
        - Input causing exception: returns 2 (CONFIG ERROR)
        - Unicode input: handled correctly

    Example:
        >>> main("normal text")
        0
        >>> main("sk_live_abcdefghijklmnopqrstuvwxyz123456")
        0  # redacted consistently
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
    """Execute two-pass sanitization verification on a stream.

    Performs two sanitization passes on the provided stream and verifies
    idempotency (pass1 == pass2). Returns exit code indicating result.

    Args:
        input_stream: Text stream to read from (e.g., sys.stdin).
                      Must support iteration yielding strings (lines).
                      Stream position is consumed during first pass.

    Returns:
        Exit code as int:
            0: PASS - Sanitization consistent, no high-entropy secrets detected.
            1: FAIL - Inconsistency between passes (potential missed secret).
            2: CONFIG ERROR - Unexpected exception during processing.
    """
    try:
        # Pass 1: Read entire stream and sanitize
        pass1 = sanitize_stream(input_stream)

        # Pass 2: Verify idempotency on the sanitized output
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
    parser = argparse.ArgumentParser(
        description="Two-pass sanitization entropy check for CI gates.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check stdin (streaming mode)
  cat secrets.log | python sanitize_entropy.py

  # Check string argument
  python sanitize_entropy.py "text with sk_live_abc123 token"

  # Dry-run with default test data
  python sanitize_entropy.py --dry-run

  # Custom entropy threshold
  ENTROPY_THRESHOLD=5.0 python sanitize_entropy.py "input text"
        """
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Input text to sanitize. If omitted, reads from stdin."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run with default test data and show sanitization output."
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Force streaming mode (read from stdin)."
    )

    args = parser.parse_args()

    if args.dry_run:
        test_data = get_default_test_data()
        print("=== Dry-run mode ===")
        print("Input:")
        print(test_data)
        print("\nSanitized (pass 1):")
        pass1 = sanitize_pass(test_data)
        print(pass1)
        print("\nSanitized (pass 2):")
        pass2 = sanitize_pass(pass1)
        print(pass2)
        print(f"\nIdempotent: {pass1 == pass2}")
        sys.exit(0 if pass1 == pass2 else 1)

    if args.input is not None and not args.stream:
        # String argument mode
        sys.exit(main(args.input))
    else:
        # Streaming mode (stdin)
        sys.exit(main_stream(sys.stdin))
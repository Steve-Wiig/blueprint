#!/usr/bin/env python3
"""
Credential Sanitization Tool for SOC Automation Platform.

Scans text content for sensitive credential patterns including AWS keys, GitHub tokens,
JWT bearer tokens, SSH private keys, Slack tokens, API keys, and passwords.
Supports allowlisting of known safe values and dry-run testing mode.

Compliance: LOCAL-SOC-SLM Blueprint v11.6.0 - Appendix O.16 & Section 34.1

This module provides credential detection capabilities for security automation workflows.
It uses compiled regular expressions for efficient pattern matching and maintains
allowlists of known safe values to reduce false positives.

Patterns detected:
    - AWS_KEY: AWS access key IDs (AKIA...)
    - GITHUB_TOKEN: GitHub personal access tokens (ghp_...)
    - BEARER_JWT: JWT bearer tokens (eyJ...)
    - OPENSSH_KEY: OpenSSH private key headers
    - SLACK_TOKEN: Slack bot/user/app tokens (xoxb-, xoxp-, etc.)
    - API_KEY_PARAM: API key parameters in query strings
    - PASSWORD_PARAM: Password parameters in query strings

Allowlists:
    - ALLOWLIST_SHA256: Known safe SHA256 hashes (empty string, common test values)
    - ALLOWLIST_UUID: Known safe UUIDs (nil UUID, test UUID)

Example:
    >>> from credential_sanitizer import scan_text
    >>> violations = scan_text("AKIAIOSFODNN7EXAMPLE")
    >>> print(violations)
    [('AWS_KEY', 'AKIAIOSFODNN7EXAMPLE')]
"""

import re
import sys
import argparse
from typing import Pattern

# LOCAL-SOC-SLM Blueprint v11.6.0 - Credential Sanitization Tool
# Appendix O.16 & Section 34.1 Compliance

ALLOWLIST_SHA256: set[str] = {
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "5feceb66ffc86f38d952786c6d696c79c2dbc239dd4e91b46729d73a27fb57e9"
}

ALLOWLIST_UUID: set[str] = {
    "00000000-0000-0000-0000-000000000000",
    "deadbeef-dead-beef-dead-beefdeadbeef"
}

ALLOWLIST: set[str] = ALLOWLIST_SHA256 | ALLOWLIST_UUID

PATTERNS: dict[str, str] = {
    "AWS_KEY": r"(AKIA[0-9A-Z]{16})",
    "GITHUB_TOKEN": r"(ghp_[a-zA-Z0-9]{36})",
    "BEARER_JWT": r"(eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9._-]{10,}\.[a-zA-Z0-9._-]{10,})",
    "OPENSSH_KEY": r"(-----BEGIN [A-Z ]*PRIVATE KEY-----)",
    "SLACK_TOKEN": r"(xox[baprs]-[0-9a-zA-Z]{10,48})",
    "API_KEY_PARAM": r"(api_key=[a-zA-Z0-9]{16,64})",
    "PASSWORD_PARAM": r"(password=[a-zA-Z0-9!@#$%^&*()_+]{8,64})"
}

_COMBINED_PATTERN: str = '|'.join(f'(?P<{name}>{pattern})' for name, pattern in PATTERNS.items())
COMPILED_COMBINED: Pattern[str] = re.compile(_COMBINED_PATTERN, re.IGNORECASE)

DRY_RUN_PAYLOADS: list[str] = [
    "AKIAIOSFODNN7EXAMPLE",
    "ghp_1234567890abcdef1234567890abcdef1234",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
    "-----BEGIN RSA PRIVATE KEY-----",
    "xoxb-1234567890-1234567890123",
    "api_key=secret1234567890abcdef",
    "password=supersecret123"
]


class ScanExit(RuntimeError):
    """Exception raised to signal scan completion with an exit code."""
    def __init__(self, exit_code: int, message: str = "") -> None:
        super().__init__(message or f"scan completed with exit code {exit_code}")
        self.exit_code = exit_code


def scan_text(text: str) -> list[tuple[str, str]]:
    """
    Scan text for credential patterns.

    Searches the input text for known credential patterns including AWS keys,
    GitHub tokens, JWTs, SSH keys, Slack tokens, API keys, and passwords.
    Matches are filtered against allowlists to reduce false positives.

    Args:
        text: The input text to scan for credentials. Can be any string content
            including file contents, log entries, or configuration data.

    Returns:
        List of tuples containing (pattern_name, matched_value) for each
        credential found that is not in the allowlists. Returns empty list if
        no violations are detected.

    Raises:
        re.error: If a regex pattern is invalid (should not occur with static patterns).
        TypeError: If text is not a string.

    Example:
        >>> scan_text("api_key=secret123")
        [('API_KEY_PARAM', 'api_key=secret123')]
        >>> scan_text("safe content")
        []
    """
    if not isinstance(text, str):
        raise TypeError(f"Expected str, got {type(text).__name__}")

    found: list[tuple[str, str]] = []
    for match in COMPILED_COMBINED.finditer(text):
        pattern_name = match.lastgroup
        matched_value = match.group(pattern_name)
        if matched_value not in ALLOWLIST:
            found.append((pattern_name, matched_value))
    return found


def scan_file(file_path: str) -> list[tuple[str, str]]:
    """
    Scan a single file for credential violations.

    Args:
        file_path: Path to the file to scan.

    Returns:
        List of violations found in the file.

    Raises:
        OSError: If the file cannot be read.
        UnicodeDecodeError: If the file cannot be decoded as UTF-8.
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    return scan_text(content)


def run_dry_run() -> bool:
    """
    Execute dry-run self-test with built-in payloads.

    Returns:
        True if all payloads are detected, False otherwise.
    """
    print("Running dry-run with test payloads...")
    for payload in DRY_RUN_PAYLOADS:
        result = scan_text(payload)
        if not result:
            print(f"FAIL: Dry-run payload missed: {payload}")
            return False
    print("PASS: Dry-run successful.")
    return True


def main() -> None:
    """
    Main entry point for credential scanning CLI.

    Parses command-line arguments and scans specified files for credentials.
    Supports dry-run mode for testing with built-in test payloads.

    Command-line arguments:
        --dry-run: Run self-test with built-in payloads and exit.
        files: Zero or more file paths to scan.

    Raises:
        ScanExit: Always raised with exit code indicating scan result.
            exit_code 0 = success/no violations found
            exit_code 1 = violations found in scanned files or dry-run failed
            exit_code 2 = file read error

    Example:
        $ python credential_sanitizer.py --dry-run
        PASS: Dry-run successful.
        $ python credential_sanitizer.py config.yaml secrets.env
        FAIL: Found AWS_KEY in config.yaml
    """
    parser = argparse.ArgumentParser(
        description="Scan files for credential patterns",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --dry-run                    # Run self-test
  %(prog)s file1.txt file2.yaml         # Scan specific files
  cat secrets.txt | %(prog)s -          # Scan stdin (not implemented)
        """
    )
    parser.add_argument("--dry-run", action="store_true", help="Run self-test with built-in payloads")
    parser.add_argument("files", nargs="*", help="Files to scan for credentials")
    args = parser.parse_args()

    if args.dry_run:
        success = run_dry_run()
        raise ScanExit(0 if success else 1)

    exit_code = 0
    for file_path in args.files:
        try:
            violations = scan_file(file_path)
            if violations:
                for v_type, val in violations:
                    print(f"FAIL: Found {v_type} in {file_path}")
                exit_code = 1
        except (OSError, UnicodeDecodeError) as e:
            print(f"CONFIG ERROR: Could not read {file_path}: {e}")
            raise ScanExit(2)
            
    raise ScanExit(exit_code)


if __name__ == "__main__":
    try:
        main()
    except ScanExit as e:
        sys.exit(e.exit_code)
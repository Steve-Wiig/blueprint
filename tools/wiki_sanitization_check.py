#!/usr/bin/env python3
"""
Credential Sanitization Tool for SOC Automation Platform.

Scans text content for sensitive credential patterns including AWS keys, GitHub tokens,
JWT bearer tokens, SSH private keys, Slack tokens, API keys, and passwords.
Supports allowlisting of known safe values and dry-run testing mode.

Compliance: LOCAL-SOC-SLM Blueprint v11.6.0 - Appendix O.16 & Section 34.1
"""

import re
import sys
import argparse
from typing import List, Tuple

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

PATTERNS: dict[str, str] = {
    "AWS_KEY": r"(AKIA[0-9A-Z]{16})",
    "GITHUB_TOKEN": r"(ghp_[a-zA-Z0-9]{36})",
    "BEARER_JWT": r"(eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9._-]{10,}\.[a-zA-Z0-9._-]{10,})",
    "OPENSSH_KEY": r"(-----BEGIN [A-Z ]*PRIVATE KEY-----)",
    "SLACK_TOKEN": r"(xox[baprs]-[0-9a-zA-Z]{10,48})",
    "API_KEY_PARAM": r"(api_key=[a-zA-Z0-9]{16,64})",
    "PASSWORD_PARAM": r"(password=[a-zA-Z0-9!@#$%^&*()_+]{8,64})"
}

DRY_RUN_PAYLOADS: List[str] = [
    "AKIAIOSFODNN7EXAMPLE",
    "ghp_1234567890abcdef1234567890abcdef1234",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
    "-----BEGIN RSA PRIVATE KEY-----",
    "xoxb-1234567890-1234567890123",
    "api_key=secret1234567890abcdef",
    "password=supersecret123"
]


def scan_text(text: str) -> List[Tuple[str, str]]:
    """
    Scan text for credential patterns.

    Args:
        text: The input text to scan for credentials.

    Returns:
        List of tuples containing (pattern_name, matched_value) for each
        credential found that is not in the allowlists.

    Raises:
        re.error: If a regex pattern is invalid (should not occur with static patterns).
    """
    found: List[Tuple[str, str]] = []
    for name, pattern in PATTERNS.items():
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            if match not in ALLOWLIST_SHA256 and match not in ALLOWLIST_UUID:
                found.append((name, match))
    return found


def main() -> None:
    """
    Main entry point for credential scanning.

    Parses command-line arguments and scans specified files for credentials.
    Supports dry-run mode for testing with built-in test payloads.

    Command-line arguments:
        --dry-run: Run self-test with built-in payloads and exit.
        files: Zero or more file paths to scan.

    Raises:
        RuntimeError: Always raised with exit code encoded in message.
            Exit codes: 0 = success/no violations, 1 = violations found,
            2 = file read error.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("files", nargs="*")
    args = parser.parse_args()

    if args.dry_run:
        print("Running dry-run with test payloads...")
        for p in DRY_RUN_PAYLOADS:
            res = scan_text(p)
            if not res:
                print(f"FAIL: Dry-run payload missed: {p}")
                raise RuntimeError(f"Library code called exit(1)")
        print("PASS: Dry-run successful.")
        raise RuntimeError(f"Library code called exit(0)")

    exit_code = 0
    for file_path in args.files:
        try:
            with open(file_path, 'r') as f:
                content = f.read()
                violations = scan_text(content)
                if violations:
                    for v_type, val in violations:
                        print(f"FAIL: Found {v_type} in {file_path}")
                    exit_code = 1
        except Exception as e:
            print(f"CONFIG ERROR: Could not read {file_path}: {e}")
            raise RuntimeError(f"Library code called exit(2)")
            
    raise RuntimeError(f"Library code called sys.exit({exit_code})")


if __name__ == "__main__":
    main()
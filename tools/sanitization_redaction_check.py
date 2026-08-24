import re
import argparse
import sys
from typing import TypedDict
from enum import IntEnum

class CheckResult(IntEnum):
    PASS = 0
    PATTERN_MISSING = 1
    PAYLOAD_MISSING = 2
    INTERNAL_ERROR = 3

class PatternConfig(TypedDict):
    pattern: str
    redaction_type: str

PATTERNS: dict[str, PatternConfig] = {
    "aws_key": {"pattern": r"\b(AKIA[0-9A-Z]{16})\b", "redaction_type": "full"},
    "github_token": {"pattern": r"\b(ghp_[a-zA-Z0-9]{36})\b", "redaction_type": "full"},
    "jwt_token": {"pattern": r"\b(eyJ[a-zA-Z0-9_-]{16,}\.[a-zA-Z0-9_-]{16,}\.[a-zA-Z0-9_-]{16,})\b", "redaction_type": "full"},
    "ssh_key": {"pattern": r"(-----BEGIN[ A-Z0-9]+PRIVATE KEY-----)", "redaction_type": "full"},
    "slack_token": {"pattern": r"\b(xox[baprs]-[0-9a-zA-Z]{10,48})\b", "redaction_type": "full"},
    "auth_header": {"pattern": r"(?i)(Authorization:\s+(?:Bearer|Basic|Token)\s+)([a-zA-Z0-9\._\-\+/=]+)", "redaction_type": "group"},
    "api_key_query": {"pattern": r"(?i)(api_key=)([a-zA-Z0-9]{20,})", "redaction_type": "group"},
    "password_query": {"pattern": r"(?i)(password=)([^&\s]{8,})", "redaction_type": "group"}
}

COMPILED_PATTERNS: dict[str, re.Pattern[str]] = {k: re.compile(v["pattern"]) for k, v in PATTERNS.items()}

TEST_PAYLOADS: dict[str, str] = {
    "aws_key": "Access key is AKIAIOSFODNN7EXAMPLE",
    "github_token": "Token: ghp_1234567890abcdef1234567890abcdef1234",
    "jwt_token": "Header: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
    "ssh_key": "Key: -----BEGIN RSA PRIVATE KEY-----",
    "slack_token": "Slack: xoxb-1234567890-1234567890123",
    "auth_header": "Authorization: Bearer mysecrettoken123",
    "api_key_query": "url?api_key=abcdef1234567890abcdef12",
    "password_query": "login?user=admin&password=supersecretpassword"
}

def redact(pattern_key: str, text: str) -> str:
    """Redact sensitive pattern in text, preserving prefix for query/header patterns.

    Args:
        pattern_key: Key identifying the pattern to redact (must exist in PATTERNS).
        text: Input text containing potential sensitive data.

    Returns:
        Text with sensitive portions replaced by "[REDACTED]". For "group" redaction
        types (auth_header, api_key_query, password_query), the prefix (e.g.,
        "Authorization: Bearer ", "api_key=", "password=") is preserved.

    Raises:
        KeyError: If pattern_key is not found in PATTERNS.

    Example:
        >>> redact("aws_key", "Key: AKIAIOSFODNN7EXAMPLE")
        'Key: [REDACTED]'
        >>> redact("auth_header", "Authorization: Bearer token123")
        'Authorization: Bearer [REDACTED]'
    """
    pattern = COMPILED_PATTERNS[pattern_key]
    redaction_type = PATTERNS[pattern_key]["redaction_type"]
    if redaction_type == "group":
        return pattern.sub(r"\1[REDACTED]", text)
    return pattern.sub("[REDACTED]", text)

def run_sanitization_check() -> CheckResult:
    """Run sanitization verification against known test payloads.

    Validates that all defined patterns:
    1. Have corresponding test payloads in TEST_PAYLOADS.
    2. Match their respective test payloads.
    3. Successfully redact the matched portion (producing "[REDACTED]").

    Returns:
        CheckResult enum indicating verification status:
        - PASS (0): All patterns validated successfully.
        - PATTERN_MISSING (1): A pattern failed to match its payload or redact.
        - PAYLOAD_MISSING (2): A pattern lacks a corresponding test payload.
        - INTERNAL_ERROR (3): Unexpected error or empty configuration.

    Side Effects:
        None. Reads global PATTERNS, COMPILED_PATTERNS, and TEST_PAYLOADS.

    Example:
        >>> result = run_sanitization_check()
        >>> result == CheckResult.PASS
        True
    """
    try:
        if not PATTERNS or not TEST_PAYLOADS:
            return CheckResult.INTERNAL_ERROR

        for key in PATTERNS:
            payload = TEST_PAYLOADS.get(key)
            if not payload:
                return CheckResult.PAYLOAD_MISSING

            if not COMPILED_PATTERNS[key].search(payload):
                return CheckResult.PATTERN_MISSING

            redacted = redact(key, payload)
            if "[REDACTED]" not in redacted:
                return CheckResult.PATTERN_MISSING

        return CheckResult.PASS
    except MemoryError:
        return CheckResult.INTERNAL_ERROR
    except Exception:
        return CheckResult.PAYLOAD_MISSING

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CI Check Tool")
    parser.add_argument("--dry-run", action="store_true", help="Run with test/mock data")
    parser.parse_args()
    sys.exit(run_sanitization_check())
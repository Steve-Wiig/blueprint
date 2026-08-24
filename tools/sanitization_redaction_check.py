import re
import argparse
import sys
from typing import Dict, Pattern, TypedDict
from enum import IntEnum

class CheckResult(IntEnum):
    PASS = 0
    PATTERN_MISSING = 1
    PAYLOAD_MISSING = 2
    INTERNAL_ERROR = 3

class PatternConfig(TypedDict):
    pattern: str
    redaction_type: str

PATTERNS: Dict[str, PatternConfig] = {
    "aws_key": {"pattern": r"\b(AKIA[0-9A-Z]{16})\b", "redaction_type": "full"},
    "github_token": {"pattern": r"\b(ghp_[a-zA-Z0-9]{36})\b", "redaction_type": "full"},
    "jwt_token": {"pattern": r"\b(eyJ[a-zA-Z0-9_-]{16,}\.[a-zA-Z0-9_-]{16,}\.[a-zA-Z0-9_-]{16,})\b", "redaction_type": "full"},
    "ssh_key": {"pattern": r"(-----BEGIN[ A-Z0-9]+PRIVATE KEY-----)", "redaction_type": "full"},
    "slack_token": {"pattern": r"\b(xox[baprs]-[0-9a-zA-Z]{10,48})\b", "redaction_type": "full"},
    "auth_header": {"pattern": r"(?i)(Authorization:\s+(?:Bearer|Basic|Token)\s+)([a-zA-Z0-9\._\-\+/=]+)", "redaction_type": "group"},
    "api_key_query": {"pattern": r"(?i)(api_key=)([a-zA-Z0-9]{20,})", "redaction_type": "group"},
    "password_query": {"pattern": r"(?i)(password=)([^&\s]{8,})", "redaction_type": "group"}
}

COMPILED_PATTERNS: Dict[str, Pattern[str]] = {k: re.compile(v["pattern"]) for k, v in PATTERNS.items()}

TEST_PAYLOADS: Dict[str, str] = {
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
    """Redact sensitive pattern in text, preserving prefix for query/header patterns."""
    pattern = COMPILED_PATTERNS[pattern_key]
    redaction_type = PATTERNS[pattern_key]["redaction_type"]
    if redaction_type == "group":
        return pattern.sub(r"\1[REDACTED]", text)
    return pattern.sub("[REDACTED]", text)

def run_sanitization_check() -> CheckResult:
    """Run sanitization verification. Returns CheckResult enum."""
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
    args = parser.parse_args()
    sys.exit(run_sanitization_check())
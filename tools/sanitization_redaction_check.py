"""Sanitization pattern verification for SOC automation. Validates secret detection regexes against known payloads."""
import re
import sys
from typing import TypedDict, Dict, Pattern, Optional
from enum import IntEnum


class CheckResult(IntEnum):
    """Enumeration of possible sanitization check outcomes."""
    PASS = 0
    PATTERN_MISSING = 1
    PAYLOAD_MISSING = 2
    INTERNAL_ERROR = 3


class PatternConfig(TypedDict):
    """Configuration for a secret detection pattern."""
    pattern: str
    redaction_type: str


# Pattern definitions for secret detection.
# Each entry maps a pattern key to its regex pattern and redaction strategy.
# redaction_type "full": replace entire match with [REDACTED]
# redaction_type "group": preserve first capture group (prefix), redact remainder
PATTERNS: Dict[str, PatternConfig] = {
    "aws_key": {
        "pattern": r"\b(AKIA[0-9A-Z]{16})\b",
        "redaction_type": "full"
    },  # AWS Access Key ID (20 chars starting with AKIA)
    "github_token": {
        "pattern": r"\b(ghp_[a-zA-Z0-9]{36})\b",
        "redaction_type": "full"
    },  # GitHub Personal Access Token (classic)
    "jwt_token": {
        "pattern": r"\b(eyJ[a-zA-Z0-9_-]{16,}\.[a-zA-Z0-9_-]{16,}\.[a-zA-Z0-9_-]{16,})\b",
        "redaction_type": "full"
    },  # JSON Web Token (three base64url-encoded segments)
    "ssh_key": {
        "pattern": r"(-----BEGIN[ A-Z0-9]+PRIVATE KEY-----)",
        "redaction_type": "full"
    },  # SSH Private Key header (RSA, EC, OPENSSH, etc.)
    "slack_token": {
        "pattern": r"\b(xox[baprs]-[0-9a-zA-Z]{10,48})\b",
        "redaction_type": "full"
    },  # Slack API Token (bot, user, app, workspace, etc.)
    "auth_header": {
        "pattern": r"(?i)(Authorization:\s+(?:Bearer|Basic|Token)\s+)([a-zA-Z0-9\._\-\+/=]+)",
        "redaction_type": "group"
    },  # HTTP Authorization header with Bearer/Basic/Token scheme
    "api_key_query": {
        "pattern": r"(?i)(api_key=)([a-zA-Z0-9]{20,})",
        "redaction_type": "group"
    },  # API key in query string parameter
    "password_query": {
        "pattern": r"(?i)(password=)([^&\s]{8,})",
        "redaction_type": "group"
    },  # Password in query string parameter
}

# Test payloads for validating each pattern.
# Each key corresponds to a pattern in PATTERNS and contains a sample string
# that should match the pattern and be redacted correctly.
TEST_PAYLOADS: Dict[str, str] = {
    "aws_key": "Access key is AKIAIOSFODNN7EXAMPLE",  # AWS Access Key ID
    "github_token": "Token: ghp_1234567890abcdef1234567890abcdef1234",  # GitHub PAT
    "jwt_token": "Header: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",  # JWT
    "ssh_key": "Key: -----BEGIN RSA PRIVATE KEY-----",  # SSH private key header
    "slack_token": "Slack: xoxb-1234567890-1234567890123",  # Slack bot token
    "auth_header": "Authorization: Bearer mysecrettoken123",  # Auth header with Bearer token
    "api_key_query": "url?api_key=abcdef1234567890abcdef12",  # API key in query param
    "password_query": "login?user=admin&password=supersecretpassword"  # Password in query param
}


class Sanitizer:
    """Encapsulates secret detection patterns and redaction logic for isolated testing."""

    def __init__(self, patterns: Optional[Dict[str, PatternConfig]] = None):
        """Initialize sanitizer with custom or default patterns.

        Args:
            patterns: Optional dict of pattern configurations. If None, uses global PATTERNS.
        """
        self._patterns = patterns if patterns is not None else PATTERNS
        self._compiled_patterns: Dict[str, Pattern[str]] = {
            k: re.compile(v["pattern"]) for k, v in self._patterns.items()
        }

    def redact(self, pattern_key: str, text: str) -> str:
        """Redact sensitive pattern in text, preserving prefix for query/header patterns.

        Args:
            pattern_key: Key identifying the pattern to redact (must exist in patterns).
            text: Input text containing potential sensitive data.

        Returns:
            Text with sensitive portions replaced by "[REDACTED]". For "group" redaction
            types (auth_header, api_key_query, password_query), the prefix (e.g.,
            "Authorization: Bearer ", "api_key=", "password=") is preserved.

        Raises:
            KeyError: If pattern_key is not found in patterns.
        """
        pattern = self._compiled_patterns.get(pattern_key)
        if not pattern:
            raise KeyError(pattern_key)
        redaction_type = self._patterns[pattern_key]["redaction_type"]
        if redaction_type == "group":
            return pattern.sub(r"\1[REDACTED]", text)
        return pattern.sub("[REDACTED]", text)

    def run_sanitization_check(self, test_payloads: Optional[Dict[str, str]] = None) -> CheckResult:
        """Run sanitization verification against known test payloads.

        Validates that all defined patterns:
        1. Have corresponding test payloads.
        2. Match their respective test payloads.
        3. Successfully redact the matched portion (producing "[REDACTED]").

        Args:
            test_payloads: Optional dict of test payloads. If None, uses global TEST_PAYLOADS.

        Returns:
            CheckResult enum indicating verification status.
        """
        payloads = test_payloads if test_payloads is not None else TEST_PAYLOADS
        try:
            if not self._patterns or not payloads:
                return CheckResult.INTERNAL_ERROR

            for key in self._patterns:
                payload = payloads.get(key)
                if not payload:
                    return CheckResult.PAYLOAD_MISSING

                if not self._compiled_patterns[key].search(payload):
                    return CheckResult.PATTERN_MISSING

                redacted = self.redact(key, payload)
                if "[REDACTED]" not in redacted:
                    return CheckResult.PATTERN_MISSING

            return CheckResult.PASS
        except MemoryError:
            return CheckResult.INTERNAL_ERROR
        except Exception:
            return CheckResult.PAYLOAD_MISSING


_default_sanitizer: Optional[Sanitizer] = None


def _get_default_sanitizer() -> Sanitizer:
    """Get or create the default sanitizer instance (lazy initialization)."""
    global _default_sanitizer
    if _default_sanitizer is None:
        _default_sanitizer = Sanitizer()
    return _default_sanitizer


def redact(pattern_key: str, text: str) -> str:
    """Redact sensitive pattern in text using default patterns.

    Args:
        pattern_key: Key identifying the pattern to redact (must exist in PATTERNS).
        text: Input text containing potential sensitive data.

    Returns:
        Text with sensitive portions replaced by "[REDACTED]". For "group" redaction
        types (auth_header, api_key_query, password_query), the prefix (e.g.,
        "Authorization: Bearer ", "api_key=", "password=") is preserved.

    Raises:
        KeyError: If pattern_key is not found in PATTERNS.
    """
    return _get_default_sanitizer().redact(pattern_key, text)


def run_sanitization_check() -> CheckResult:
    """Run sanitization verification against known test payloads using default patterns.

    Returns:
        CheckResult enum indicating verification status.
    """
    return _get_default_sanitizer().run_sanitization_check()


if __name__ == "__main__":
    sys.exit(run_sanitization_check())
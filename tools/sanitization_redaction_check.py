import json
import os
import re
import sys
import threading
from pathlib import Path
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


# Embedded default patterns (fallback when config file not found)
_DEFAULT_PATTERNS: Dict[str, PatternConfig] = {
    "aws_key": {
        "pattern": r"\b(AKIA[0-9A-Z]{16})\b",
        "redaction_type": "full"
    },
    "github_token": {
        "pattern": r"\b(ghp_[a-zA-Z0-9]{36})\b",
        "redaction_type": "full"
    },
    "jwt_token": {
        "pattern": r"\b(eyJ[a-zA-Z0-9_-]{16,}\.[a-zA-Z0-9_-]{16,}\.[a-zA-Z0-9_-]{16,})\b",
        "redaction_type": "full"
    },
    "ssh_key": {
        "pattern": r"(-----BEGIN[ A-Z0-9]+PRIVATE KEY-----)",
        "redaction_type": "full"
    },
    "slack_token": {
        "pattern": r"\b(xox[baprs]-[0-9a-zA-Z]{10,48})\b",
        "redaction_type": "full"
    },
    "auth_header": {
        "pattern": r"(?i)(Authorization:\s+(?:Bearer|Basic|Token)\s+)([a-zA-Z0-9\._\-\+/=]+)",
        "redaction_type": "group"
    },
    "api_key_query": {
        "pattern": r"(?i)(api_key=)([a-zA-Z0-9]{20,})",
        "redaction_type": "group"
    },
    "password_query": {
        "pattern": r"(?i)(password=)([^&\s]{8,})",
        "redaction_type": "group"
    },
}

# Embedded default test payloads (fallback when config file not found)
_DEFAULT_TEST_PAYLOADS: Dict[str, str] = {
    "aws_key": "Access key is AKIAIOSFODNN7EXAMPLE",
    "github_token": "Token: ghp_1234567890abcdef1234567890abcdef1234",
    "jwt_token": "Header: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
    "ssh_key": "Key: -----BEGIN RSA PRIVATE KEY-----",
    "slack_token": "Slack: xoxb-1234567890-1234567890123",
    "auth_header": "Authorization: Bearer mysecrettoken123",
    "api_key_query": "url?api_key=abcdef1234567890abcdef12",
    "password_query": "login?user=admin&password=supersecretpassword"
}

# Module-level globals (patched by tests, loaded from config at runtime)
PATTERNS: Dict[str, PatternConfig] = dict(_DEFAULT_PATTERNS)
TEST_PAYLOADS: Dict[str, str] = dict(_DEFAULT_TEST_PAYLOADS)

_CONFIG_LOADED = False


def _load_config(config_path: Optional[str] = None) -> None:
    """Load PATTERNS and TEST_PAYLOADS from external JSON config file.

    Args:
        config_path: Path to JSON config file. If None, checks SANITIZER_CONFIG
                     environment variable, then default locations.
    """
    global PATTERNS, TEST_PAYLOADS, _CONFIG_LOADED

    if _CONFIG_LOADED:
        return

    search_paths = []
    if config_path:
        search_paths.append(Path(config_path))
    else:
        env_path = os.environ.get("SANITIZER_CONFIG")
        if env_path:
            search_paths.append(Path(env_path))
        search_paths.extend([
            Path("/etc/sanitizer/config.json"),
            Path.home() / ".config" / "sanitizer" / "config.json",
            Path.cwd() / "sanitizer_config.json",
        ])

    for path in search_paths:
        if path.is_file():
            try:
                with path.open("r", encoding="utf-8") as f:
                    config = json.load(f)
                if "patterns" in config:
                    PATTERNS = dict(config["patterns"])
                if "test_payloads" in config:
                    TEST_PAYLOADS = dict(config["test_payloads"])
                _CONFIG_LOADED = True
                return
            except (json.JSONDecodeError, OSError, KeyError):
                continue

    _CONFIG_LOADED = True


class Sanitizer:
    """Encapsulates secret detection patterns and redaction logic for isolated testing.

    This is the primary API for sanitization. Instantiate with custom patterns
    or use defaults. All methods are instance methods to enable parallel use
    with different configurations and facilitate unit testing.

    Thread-safety: Pattern updates via recompile() are thread-safe. Concurrent
    reads (redact, run_sanitization_check) are safe against concurrent updates.
    """

    def __init__(self, patterns: Optional[Dict[str, PatternConfig]] = None, redaction_token: str = '[REDACTED]'):
        """Initialize sanitizer with custom or default patterns.

        Args:
            patterns: Optional dict of pattern configurations. If None, uses global PATTERNS.
                      A copy is made to avoid external mutations affecting compiled patterns.
            redaction_token: Token used to replace sensitive data.
        """
        self._patterns = dict(patterns) if patterns is not None else dict(PATTERNS)
        self._compiled_patterns: Dict[str, Pattern[str]] = {}
        self._pattern_hashes: Dict[str, int] = {}
        self._redaction_token = redaction_token
        self._lock = threading.RLock()
        self.recompile()

    def recompile(self) -> None:
        """Recompile only patterns that have changed since last compilation.

        Call this if _patterns is modified after initialization to ensure
        compiled patterns are up to date. Thread-safe.
        """
        with self._lock:
            new_hashes = {}
            for k, v in self._patterns.items():
                pattern_str = v["pattern"]
                new_hashes[k] = hash(pattern_str)

            for k, new_hash in new_hashes.items():
                old_hash = self._pattern_hashes.get(k)
                if old_hash != new_hash:
                    self._compiled_patterns[k] = re.compile(self._patterns[k]["pattern"])

            for k in list(self._compiled_patterns.keys()):
                if k not in new_hashes:
                    del self._compiled_patterns[k]

            self._pattern_hashes = new_hashes

    def redact(self, pattern_key: str, text: str, redaction_token: Optional[str] = None) -> str:
        """Redact sensitive pattern in text, preserving prefix for query/header patterns.

        Args:
            pattern_key: Key identifying the pattern to redact (must exist in patterns).
            text: Input text containing potential sensitive data.
            redaction_token: Optional override for the instance's redaction token.

        Returns:
            Text with sensitive portions replaced by the configured redaction token. For "group" redaction
            types (auth_header, api_key_query, password_query), the prefix (e.g.,
            "Authorization: Bearer ", "api_key=", "password=") is preserved.

        Raises:
            KeyError: If pattern_key is not found in patterns.
        """
        with self._lock:
            pattern = self._compiled_patterns.get(pattern_key)
            if not pattern:
                raise KeyError(pattern_key)
            redaction_type = self._patterns[pattern_key]["redaction_type"]
            token = redaction_token if redaction_token is not None else self._redaction_token
            if redaction_type == "group":
                return pattern.sub(r"\1" + token, text)
            return pattern.sub(token, text)

    def run_sanitization_check(self, test_payloads: Optional[Dict[str, str]] = None) -> CheckResult:
        """Run sanitization verification against known test payloads.

        Validates that all defined patterns:
        1. Have corresponding test payloads.
        2. Match their respective test payloads.
        3. Successfully redact the matched portion (producing the configured redaction token).

        Args:
            test_payloads: Optional dict of test payloads. If None, uses global TEST_PAYLOADS.

        Returns:
            CheckResult enum indicating verification status.
        """
        payloads = test_payloads if test_payloads is not None else TEST_PAYLOADS
        try:
            with self._lock:
                assert self._patterns and payloads

                for key in self._patterns:
                    payload = payloads.get(key)
                    if not payload:
                        return CheckResult.PAYLOAD_MISSING

                    if not self._compiled_patterns[key].search(payload):
                        return CheckResult.PATTERN_MISSING

                    redacted = self.redact(key, payload)
                    if self._redaction_token not in redacted:
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


def redact(pattern_key: str, text: str, redaction_token: Optional[str] = None) -> str:
    """Redact sensitive pattern in text using default patterns.

    Args:
        pattern_key: Key identifying the pattern to redact (must exist in PATTERNS).
        text: Input text containing potential sensitive data.
        redaction_token: Optional custom redaction token. If not provided, uses the default "[REDACTED]".

    Returns:
        Text with sensitive portions replaced by the redaction token. For "group" redaction
        types (auth_header, api_key_query, password_query), the prefix (e.g.,
        "Authorization: Bearer ", "api_key=", "password=") is preserved.

    Raises:
        KeyError: If pattern_key is not found in PATTERNS.
    """
    return _get_default_sanitizer().redact(pattern_key, text, redaction_token)


def run_sanitization_check() -> CheckResult:
    """Run sanitization verification against known test payloads using default patterns.

    Returns:
        CheckResult enum indicating verification status.
    """
    return _get_default_sanitizer().run_sanitization_check()


def main() -> int:
    """CLI entry point: load config and run sanitization check."""
    _load_config()
    return int(run_sanitization_check())


if __name__ == "__main__":
    sys.exit(main())
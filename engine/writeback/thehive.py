import argparse
import os
import requests
import json
import sys
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union
from engine.sanitization_pipeline import sanitize_payload

"""
TheHive Case Writeback Adapter

This module provides functionality to create cases in TheHive platform
from structured case data. It handles payload sanitization, API communication,
and audit logging for SOC automation workflows.

Usage:
    python -m thehive_writeback.handoff --case-data '{"title": "...", "description": "..."}' \
        --api-key <key> --url <url> [--mode draft|live] [--log-path <path>]

Environment Variables:
    HANDOFF_LOG_PATH: Default path for handoff log file (default: handoff_log.txt)
"""

REQUIRED_CASE_FIELDS = {'title', 'description'}

SECRET_PATTERNS = [
    re.compile(r'(?i)(api[_-]?key|apikey)\s*[:=]\s*[\w\-]{20,}'),
    re.compile(r'(?i)(password|passwd|pwd)\s*[:=]\s*\S+'),
    re.compile(r'(?i)(token|access[_-]?token|bearer)\s*[:=]\s*[\w\-]{20,}'),
    re.compile(r'(?i)(secret|client[_-]?secret)\s*[:=]\s*[\w\-]{20,}'),
    re.compile(r'(?i)(authorization|auth)\s*[:=]\s*Bearer\s+\S+'),
    re.compile(r'[\w\-]{32,}'),
    re.compile(r'sk-[\w\-]{20,}'),
    re.compile(r'gh[pousr]_[A-Za-z0-9]{36,}'),
    re.compile(r'xox[baprs]-[\w\-]{10,}'),
]

_LOGGER_CACHE: dict[Path, logging.Logger] = {}
_SESSION: Optional[requests.Session] = None


class TheHiveWritebackAdapter:
    """Class-based adapter for TheHive case writeback with isolated session and logger state."""

    def __init__(self, session: Optional[requests.Session] = None, logger_cache: Optional[dict[Path, logging.Logger]] = None):
        self._session = session
        self._logger_cache = logger_cache if logger_cache is not None else {}

    def _get_session(self) -> requests.Session:
        """Get or create a requests Session for connection pooling."""
        if self._session is None:
            self._session = requests.Session()
        return self._session

    def _setup_logger(self, log_path: Path) -> logging.Logger:
        """Configure a file logger for handoff audit trail.

        Args:
            log_path: Path to the log file.

        Returns:
            Configured logger instance with file handler.
        """
        if log_path in self._logger_cache:
            return self._logger_cache[log_path]

        logger_name = f"thehive_writeback.handoff.{log_path}"
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        logger.handlers.clear()
        handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        self._logger_cache[log_path] = logger
        return logger

    def verify_sanitization(self, payload: Any, context: str = "payload") -> None:
        """Verify that payload contains no secrets or high-entropy tokens.

        Args:
            payload: The sanitized payload to verify.
            context: Description of the payload for error messages.

        Raises:
            ValueError: If any secret pattern is detected in the payload.
        """
        payload_str = json.dumps(payload, ensure_ascii=False)
        for pattern in SECRET_PATTERNS:
            match = pattern.search(payload_str)
            if match:
                raise ValueError(
                    f"Sanitization verification failed: potential secret detected in {context} "
                    f"(pattern: {pattern.pattern}, match: {match.group()[:50]})"
                )

    def build_payload(self, raw_data: Any, mode: str) -> Any:
        """Build and sanitize the case payload for TheHive API.

        This function creates a copy of the input data to avoid mutating
        the caller's original dictionary.

        Args:
            raw_data: Raw case data dictionary.
            mode: Operation mode ('draft' or 'live').

        Returns:
            Sanitized payload ready for TheHive API submission.

        Raises:
            ValueError: If sanitization fails due to invalid data or secrets remain.
        """
        data = dict(raw_data)
        if mode == 'draft':
            data['status'] = 'Open'
            data['tags'] = data.get('tags', []) + ['draft-mode']
        sanitized = sanitize_payload(data)
        self.verify_sanitization(sanitized, "sanitized payload")
        return sanitized

    def call_thehive_api(self, url: str, api_key: str, payload: Any) -> str:
        """Create a case in TheHive via REST API.

        Args:
            url: TheHive base URL (e.g., 'https://thehive.example.com').
            api_key: TheHive API key for authentication.
            payload: Sanitized case payload dictionary.

        Returns:
            TheHive case ID string.

        Raises:
            RuntimeError: If API returns error status or missing case ID in response.
            requests.exceptions.RequestException: If network request fails.
        """
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        session = self._get_session()
        response = session.post(
            f"{url}/api/case",
            json=payload,
            headers=headers,
            timeout=30
        )
        if response.status_code not in [200, 201]:
            raise RuntimeError(f"TheHive API error: {response.status_code} - {response.text}")
        case_id = response.json().get('id')
        if not case_id:
            raise RuntimeError("TheHive API response missing case ID")
        return case_id

    def log_handoff(self, log_path: Path, case_id: str, mode: str) -> None:
        """Log successful case creation to handoff audit file.

        Args:
            log_path: Path to the handoff log file.
            case_id: TheHive case ID that was created.
            mode: Operation mode ('draft' or 'live').

        Returns:
            None
        """
        logger = self._setup_logger(log_path)
        now = datetime.now(timezone.utc)
        logger.info(f"{now.isoformat()}|REF:{case_id}|STATUS:SUCCESS|MODE:{mode}")

    def main(self, args: argparse.Namespace) -> Union[str, int]:
        """Main entry point for TheHive case writeback adapter.

        Parses arguments, validates input, creates case in TheHive,
        and logs the handoff result.

        Args:
            args: Parsed command-line arguments.

        Returns:
            Case ID string on success, or integer exit code on failure:
            - 1: Missing required fields or TheHive API error
            - 2: Invalid JSON in case-data
            - 3: Network/request exception
            - 4: Sanitization verification failed
        """
        log_path = Path(args.log_path) if args.log_path else Path(os.environ.get("HANDOFF_LOG_PATH", "handoff_log.txt"))
        try:
            raw_data: Any = json.loads(args.case_data)
        except json.JSONDecodeError:
            return 2
        missing = REQUIRED_CASE_FIELDS - set(raw_data.keys())
        if missing:
            print(f"Missing required fields: {missing}", file=sys.stderr)
            return 1
        try:
            sanitized_data = self.build_payload(raw_data, args.mode)
        except ValueError as e:
            print(f"Sanitization error: {e}", file=sys.stderr)
            return 4
        try:
            case_id = self.call_thehive_api(args.url, args.api_key, sanitized_data)
            self.log_handoff(log_path, case_id, args.mode)
            return case_id
        except requests.exceptions.RequestException as e:
            error_logger = logging.getLogger("thehive_writeback.handoff.error")
            error_logger.setLevel(logging.ERROR)
            if not error_logger.handlers:
                handler = logging.StreamHandler(sys.stderr)
                handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
                error_logger.addHandler(handler)
            error_logger.exception("TheHive API request failed for URL %s with payload %s", args.url, sanitized_data)
            return 3
        except RuntimeError:
            return 1


_default_adapter = TheHiveWritebackAdapter(session=_SESSION, logger_cache=_LOGGER_CACHE)


def create_adapter() -> TheHiveWritebackAdapter:
    """Factory function to create a new isolated TheHiveWritebackAdapter instance.

    Returns:
        A new TheHiveWritebackAdapter with fresh session and logger cache.
    """
    return TheHiveWritebackAdapter()


def _get_session() -> requests.Session:
    """Get or create a requests Session for connection pooling (module-level backward compatibility)."""
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
    return _SESSION


def _setup_logger(log_path: Path) -> logging.Logger:
    """Configure a file logger for handoff audit trail (module-level backward compatibility).

    Args:
        log_path: Path to the log file.

    Returns:
        Configured logger instance with file handler.
    """
    if log_path in _LOGGER_CACHE:
        return _LOGGER_CACHE[log_path]

    logger_name = f"thehive_writeback.handoff.{log_path}"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()
    handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    _LOGGER_CACHE[log_path] = logger
    return logger


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the TheHive writeback adapter.

    Returns:
        Parsed arguments namespace with attributes:
        - case_data: JSON string of case data
        - api_key: TheHive API key
        - url: TheHive base URL
        - mode: Operation mode ('draft' or 'live')
        - log_path: Optional path to handoff log file
    """
    parser = argparse.ArgumentParser(description="TheHive Case Writeback Adapter v11.6.0")
    parser.add_argument("--case-data", required=True, help="JSON string of case data")
    parser.add_argument("--api-key", required=True, help="TheHive API Key")
    parser.add_argument("--url", required=True, help="TheHive Base URL")
    parser.add_argument("--mode", choices=['draft', 'live'], default='draft', help="Adapter mode")
    parser.add_argument("--log-path", help="Path to the handoff log file (overrides HANDOFF_LOG_PATH env var and default)")
    return parser.parse_args()


def verify_sanitization(payload: Any, context: str = "payload") -> None:
    """Verify that payload contains no secrets or high-entropy tokens (module-level backward compatibility).

    Args:
        payload: The sanitized payload to verify.
        context: Description of the payload for error messages.

    Raises:
        ValueError: If any secret pattern is detected in the payload.
    """
    _default_adapter.verify_sanitization(payload, context)


def build_payload(raw_data: Any, mode: str) -> Any:
    """Build and sanitize the case payload for TheHive API (module-level backward compatibility).

    This function creates a copy of the input data to avoid mutating
    the caller's original dictionary.

    Args:
        raw_data: Raw case data dictionary.
        mode: Operation mode ('draft' or 'live').

    Returns:
        Sanitized payload ready for TheHive API submission.

    Raises:
        ValueError: If sanitization fails due to invalid data or secrets remain.
    """
    return _default_adapter.build_payload(raw_data, mode)


def call_thehive_api(url: str, api_key: str, payload: Any) -> str:
    """Create a case in TheHive via REST API (module-level backward compatibility).

    Args:
        url: TheHive base URL (e.g., 'https://thehive.example.com').
        api_key: TheHive API key for authentication.
        payload: Sanitized case payload dictionary.

    Returns:
        TheHive case ID string.

    Raises:
        RuntimeError: If API returns error status or missing case ID in response.
        requests.exceptions.RequestException: If network request fails.
    """
    return _default_adapter.call_thehive_api(url, api_key, payload)


def log_handoff(log_path: Path, case_id: str, mode: str) -> None:
    """Log successful case creation to handoff audit file (module-level backward compatibility).

    Args:
        log_path: Path to the handoff log file.
        case_id: TheHive case ID that was created.
        mode: Operation mode ('draft' or 'live').

    Returns:
        None
    """
    _default_adapter.log_handoff(log_path, case_id, mode)


def main() -> str:
    """Main entry point for TheHive case writeback adapter (module-level backward compatibility).

    Parses arguments, validates input, creates case in TheHive,
    and logs the handoff result.

    Returns:
        Case ID string on success.

    Raises:
        ValidationError: Missing required fields, invalid JSON, or sanitization failed.
        TheHiveAPIError: TheHive API returned an error.
        NetworkError: Network/request exception occurred.
    """
    args = parse_args()

    # Handle --test-sanitization CLI entry point for external test suite
    if getattr(args, 'test_sanitization', False):
        try:
            from tests.test_thehive_writeback import run_sanitization_tests
            success = run_sanitization_tests()
            if not success:
                raise ValidationError("Sanitization tests failed")
            return "test-success"
        except ImportError as e:
            raise RuntimeError("Test module not found. Run tests via pytest.") from e
        except Exception as e:
            raise RuntimeError(f"Test execution failed: {e}") from e

    # Import custom exceptions (defined elsewhere in the codebase)
    try:
        from engine.exceptions import ValidationError, TheHiveAPIError, NetworkError
    except ImportError:
        # Fallback definitions if not available
        class ValidationError(Exception):
            pass
        class TheHiveAPIError(Exception):
            pass
        class NetworkError(Exception):
            pass

    result = _default_adapter.main(args)
    if isinstance(result, str):
        return result

    # Map legacy integer error codes to specific exceptions
    if result == 1:
        raise TheHiveAPIError("Missing required fields or TheHive API error")
    elif result == 2:
        raise ValidationError("Invalid JSON in case-data")
    elif result == 3:
        raise NetworkError("Network/request exception")
    elif result == 4:
        raise ValidationError("Sanitization verification failed")
    else:
        raise RuntimeError(f"Unknown error code: {result}")
def run_sanitization_tests() -> bool:
    """Run unit tests for sanitization verification.

    Returns:
        True if all tests pass, False otherwise.
    """
    test_cases = [
        ({"title": "Test", "description": "Normal case"}, True, "clean payload"),
        ({"title": "Test", "description": "Case with api_key=abcdefghijklmnopqrstuvwxyz"}, False, "api key in description"),
        ({"title": "Test", "description": "Password: secret123"}, False, "password in description"),
        ({"title": "Test", "description": "Token: ghp_abcdefghijklmnopqrstuvwxyz123456"}, False, "github token"),
        ({"title": "Test", "description": "Key: sk-abcdefghijklmnopqrstuvwxyz123456"}, False, "openai key"),
        ({"title": "Test", "description": "Auth: Bearer abcdefghijklmnopqrstuvwxyz"}, False, "bearer token"),
        ({"title": "Test", "description": "Secret: abcdefghijklmnopqrstuvwxyz123456"}, False, "high entropy string"),
        ({"title": "Test", "tags": ["normal", "tag"]}, True, "clean tags"),
        ({"title": "Test", "tags": ["api_key=abcdefghijklmnopqrstuvwxyz"]}, False, "secret in tag"),
        ({"title": "Test", "customFields": [{"name": "api_key", "value": "abcdefghijklmnopqrstuvwxyz"}]}, False, "secret in custom field"),
    ]

    all_passed = True
    for payload, should_pass, description in test_cases:
        try:
            verify_sanitization(payload, f"test: {description}")
            if not should_pass:
                print(f"FAIL: {description} - expected detection but passed")
                all_passed = False
            else:
                print(f"PASS: {description}")
        except ValueError as e:
            if should_pass:
                print(f"FAIL: {description} - unexpected detection: {e}")
                all_passed = False
            else:
                print(f"PASS: {description} - correctly detected secret")

    return all_passed


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test-sanitization":
        success = run_sanitization_tests()
        sys.exit(0 if success else 1)
    result = main()
    if isinstance(result, str):
        sys.exit(0)
    else:
        sys.exit(result)
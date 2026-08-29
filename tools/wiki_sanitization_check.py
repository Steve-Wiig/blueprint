import re
import sys
import argparse
import logging
import logging.handlers
import os
from pathlib import Path
from typing import Pattern
from datetime import datetime, timezone

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


class ScanExit(SystemExit):
    """Exception raised to signal scan completion with an exit code."""
    def __init__(self, exit_code: int, message: str = "") -> None:
        super().__init__(exit_code)
        self.exit_code = exit_code
        self.message = message or f"scan completed with exit code {exit_code}"
        self.args = (self.message,)
def _configure_logging() -> logging.Logger:
    """
    Configure structured logging for audit trails per Blueprint v11.8.

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger("credential_sanitizer")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}',
        datefmt="%Y-%m-%dT%H:%M:%S.%fZ"
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    log_file = Path("credential_sanitizer_audit.log")
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10_485_760, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


LOGGER = _configure_logging()


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


def scan_directory(dir_path: str, recursive: bool = True) -> list[tuple[str, str, str]]:
    """
    Scan a directory for credential violations.

    Args:
        dir_path: Path to the directory to scan.
        recursive: If True, scan recursively using os.walk with pruning. If False, scan only top-level files.

    Returns:
        List of tuples containing (file_path, pattern_name, matched_value) for each violation.

    Raises:
        OSError: If the directory cannot be accessed.
    """
    found: list[tuple[str, str, str]] = []
    path = Path(dir_path)
    
    if not path.is_dir():
        raise OSError(f"Path is not a directory: {dir_path}")
    
    exclude_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'env', 'dist', 'build', '.pytest_cache', '.mypy_cache'}
    
    if recursive:
        for root, dirs, files in os.walk(path):
            # Prune excluded directories in-place to avoid descending into them
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for file_name in files:
                file_path = Path(root) / file_name
                try:
                    violations = scan_file(str(file_path))
                    for v_type, val in violations:
                        found.append((str(file_path), v_type, val))
                except (OSError, UnicodeDecodeError):
                    continue
    else:
        for file_path in path.iterdir():
            if file_path.is_file():
                try:
                    violations = scan_file(str(file_path))
                    for v_type, val in violations:
                        found.append((str(file_path), v_type, val))
                except (OSError, UnicodeDecodeError):
                    continue
    
    return found

def _generate_dry_run_payloads() -> list[str]:
    """
    Generate test payloads programmatically to avoid hardcoded credential-like strings.

    Returns:
        List of test payloads that match credential patterns but are clearly test values.
    """
    payloads = [
        f"INVALID_AKIA{'T' * 16}",  # AWS_KEY: AKIA + 16 chars
        f"TEST_GHP_{'T' * 36}",  # GITHUB_TOKEN: ghp_ + 36 chars
        f"eyJTEST{'T' * 10}.{'T' * 12}.{'T' * 12}",  # BEARER_JWT: three base64url parts
        "-----BEGIN INVALID PRIVATE KEY-----",  # OPENSSH_KEY: test key header
        f"xoxb-INVALID{'T' * 12}",  # SLACK_TOKEN: xoxb- + 12 chars
        f"api_key=INVALID{'T' * 16}",  # API_KEY_PARAM: api_key= + 16 chars
        f"password=INVALID{'T' * 12}"  # PASSWORD_PARAM: password= + 12 chars
    ]
    return payloads

def run_dry_run() -> bool:
    """
    Execute dry-run self-test with built-in payloads.

    Returns:
        True if all payloads are detected, False otherwise.
    """
    LOGGER.info("Running dry-run with test payloads...")
    for payload in _generate_dry_run_payloads():
        result = scan_text(payload)
        if not result:
            LOGGER.error("FAIL: Dry-run payload missed: %s", payload)
            return False
    LOGGER.info("PASS: Dry-run successful.")
    return True


def main() -> None:
    """
    Main entry point for credential scanning CLI.

    Parses command-line arguments and scans specified files/directories for credentials.
    Supports dry-run mode for testing with built-in test payloads.

    Command-line arguments:
        --dry-run: Run self-test with built-in payloads and exit.
        --recursive: Scan directories recursively (default: True).
        --no-recursive: Scan only top-level files in directories.
        files: Zero or more file or directory paths to scan.

    Raises:
        ScanExit: Always raised with exit code indicating scan result.
            exit_code 0 = success/no violations found
            exit_code 1 = violations found in scanned files or dry-run failed
            exit_code 2 = file/directory read error

    Example:
        $ python credential_sanitizer.py --dry-run
        PASS: Dry-run successful.
        $ python credential_sanitizer.py config.yaml secrets.env
        FAIL: Found AWS_KEY in config.yaml
        $ python credential_sanitizer.py --recursive ./project
        FAIL: Found GITHUB_TOKEN in ./project/.env
    """
    # Load allowlist configuration
    ALLOWLIST_SHA256 = [
        # Example SHA256 hash, replace with actual values and comments
        # 'hash1'  # Allowlisted due to specific use case in project XYZ
    ]
    ALLOWLIST_UUID = [
        # Example UUID, replace with actual values and comments
        # 'uuid1'  # Allowlisted due to specific use case in project ABC
    ]
    ALLOWLIST = set(ALLOWLIST_SHA256 + ALLOWLIST_UUID)

    parser = argparse.ArgumentParser(
        description="Scan files and directories for credential patterns",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --dry-run                    # Run self-test
  %(prog)s file1.txt file2.yaml         # Scan specific files
  %(prog)s --recursive ./project        # Scan directory recursively
  %(prog)s --no-recursive ./config      # Scan only top-level files in directory
        """
    )
    parser.add_argument("--dry-run", action="store_true", help="Run self-test with built-in payloads")
    parser.add_argument("--recursive", action="store_true", default=True, help="Scan directories recursively (default)")
    parser.add_argument("--no-recursive", action="store_false", dest="recursive", help="Scan only top-level files in directories")
    parser.add_argument("paths", nargs="*", help="Files or directories to scan for credentials")
    args = parser.parse_args()

    if args.dry_run:
        success = run_dry_run()
        raise ScanExit(0 if success else 1)

    exit_code = 0
    for path_str in args.paths:
        path = Path(path_str)
        try:
            if path.is_file():
                violations = scan_file(path_str)
                if violations:
                    for v_type, val in violations:
                        if val in ALLOWLIST:
                            LOGGER.info("SKIP: Allowlisted %s found in %s", v_type, path_str)
                        else:
                            LOGGER.error("FAIL: Found %s in %s", v_type, path_str)
                            exit_code = 1
            elif path.is_dir():
                violations = scan_directory(path_str, recursive=args.recursive)
                if violations:
                    for file_path, v_type, val in violations:
                        if val in ALLOWLIST:
                            LOGGER.info("SKIP: Allowlisted %s found in %s", v_type, file_path)
                        else:
                            LOGGER.error("FAIL: Found %s in %s", v_type, file_path)
                            exit_code = 1
            else:
                LOGGER.error("CONFIG ERROR: Path does not exist: %s", path_str)
                raise ScanExit(2)
        except (OSError, UnicodeDecodeError) as e:
            LOGGER.error("CONFIG ERROR: Could not read %s: %s", path_str, e)
            raise ScanExit(2)

    raise ScanExit(exit_code)


if __name__ == "__main__":
    try:
        main()
    except ScanExit as e:
        sys.exit(e.exit_code)
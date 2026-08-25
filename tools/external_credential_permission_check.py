"""
CI Gate: External Credential Permission Proof

This module verifies that external service credentials have the correct
permissions - read access allowed, write/restart access denied.

It loads service configuration from a JSON file and tests each service's
credentials against a lab environment URL.
"""

import os
import sys
import argparse
import json
from dataclasses import dataclass
from typing import Any

try:
    import requests
except ImportError:
    print("FAIL: requests library is not installed")
    raise RuntimeError("Library code called exit(2)")

DEFAULT_CONFIG_PATH: str = os.path.join(os.path.dirname(__file__), "config.json")

REQUIRED_KEYS = {"user_env", "token_env", "read", "forbidden", "forbidden_method"}
VALID_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
SUCCESS_CODES = {200, 201}
DENIED_CODES = {401, 403}

MOCK_USER = "mock_user"
MOCK_TOKEN = "mock_token"


def validate_config(config: dict) -> None:
    """
    Validate the configuration schema.

    Args:
        config: Configuration dictionary to validate.

    Raises:
        ValueError: If configuration is invalid.
    """
    if not isinstance(config, dict):
        raise ValueError("Config must be a dictionary mapping service names to config objects")

    for service, cfg in config.items():
        if not isinstance(cfg, dict):
            raise ValueError(f"Service '{service}' config must be a dictionary")

        missing = REQUIRED_KEYS - set(cfg.keys())
        if missing:
            raise ValueError(f"Service '{service}' missing required keys: {missing}")

        if cfg["forbidden_method"].upper() not in VALID_METHODS:
            raise ValueError(
                f"Service '{service}' has invalid forbidden_method: {cfg['forbidden_method']}. "
                f"Must be one of {VALID_METHODS}"
            )

        for key in ("read", "forbidden"):
            if not isinstance(cfg[key], str) or not cfg[key].startswith("/"):
                raise ValueError(f"Service '{service}' {key} must be a path starting with '/'")


def load_config(config_path: str | None = None) -> dict:
    """
    Load service configuration from a JSON file.

    Args:
        config_path: Optional path to config file. Defaults to CONFIG_FILE
            environment variable or DEFAULT_CONFIG_PATH.

    Returns:
        Dictionary mapping service names to their configuration objects.

    Raises:
        RuntimeError: If config file is not found, contains invalid JSON, or fails validation.
    """
    path = config_path or os.getenv("CONFIG_FILE", DEFAULT_CONFIG_PATH)
    try:
        with open(path, "r") as f:
            config = json.load(f)
    except FileNotFoundError:
        raise RuntimeError(f"CONFIG ERROR: config file not found at {path}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"CONFIG ERROR: invalid JSON in {path}: {exc}")

    try:
        validate_config(config)
    except ValueError as exc:
        raise RuntimeError(f"CONFIG ERROR: validation failed: {exc}")

    return config


@dataclass
class MockResponse:
    """Mock HTTP response for dry-run testing."""
    status_code: int


def get_mock_response(status_code: int) -> MockResponse:
    """Return a mock HTTP response with the given status code.

    Args:
        status_code: HTTP status code for the mock response.

    Returns:
        A MockResponse instance with the specified status code.
    """
    return MockResponse(status_code)


def check_service(service: str, cfg: dict, lab_url: str, dry_run: bool = False) -> bool:
    """
    Verify credential permissions for a single service.

    Tests that credentials allow read access but deny forbidden actions.

    Args:
        service: Service name (for logging).
        cfg: Service configuration dict with keys:
            - user_env: Environment variable name for username
            - token_env: Environment variable name for token
            - read: Read endpoint path
            - forbidden: Forbidden action endpoint path
            - forbidden_method: HTTP method for forbidden action
        lab_url: Base URL of the lab environment.
        dry_run: If True, use mock responses instead of real requests.

    Returns:
        True if read access succeeds (200/201) and forbidden action is denied (401/403),
        False otherwise.
    """
    user = os.getenv(cfg["user_env"], MOCK_USER) if dry_run else os.getenv(cfg["user_env"])
    token = os.getenv(cfg["token_env"], MOCK_TOKEN) if dry_run else os.getenv(cfg["token_env"])

    if not user or not token:
        print(f"CONFIG ERROR: missing credentials for {service}")
        return False

    auth = (user, token)
    read_url = lab_url.rstrip("/") + cfg["read"]
    forbidden_url = lab_url.rstrip("/") + cfg["forbidden"]

    try:
        if dry_run:
            read_resp = get_mock_response(200)
            forbidden_resp = get_mock_response(403)
        else:
            read_resp = requests.get(read_url, auth=auth, timeout=10, verify=False)
            forbidden_resp = requests.request(cfg["forbidden_method"], forbidden_url, auth=auth, timeout=10, verify=False)

        if read_resp.status_code not in SUCCESS_CODES:
            print(f"FAIL: {service} read access denied: {read_resp.status_code}")
            return False

        if forbidden_resp.status_code not in DENIED_CODES:
            print(f"FAIL: {service} forbidden action was not denied: {forbidden_resp.status_code}")
            return False

    except Exception as exc:
        print(f"FAIL: {service} request failed: {exc}")
        return False

    print(f"PASS: {service} credential permissions verified")
    return True


def main() -> int:
    """
    Main entry point for the credential permission verification script.

    Parses command-line arguments, loads configuration, and checks all
    configured services.

    Returns:
        0 if all services pass permission checks, 1 if any fail,
        2 if configuration error (missing LAB_URL or config error).
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--config", help="Path to config JSON file")
    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except RuntimeError as exc:
        print(exc)
        return 2

    lab_url = os.getenv("LAB_URL", "http://localhost:8080" if args.dry_run else "")
    if not lab_url:
        print("CONFIG ERROR: LAB_URL is not set")
        return 2

    all_pass = True
    for service, cfg in config.items():
        if not check_service(service, cfg, lab_url, args.dry_run):
            all_pass = False

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
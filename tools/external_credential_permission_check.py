#!/usr/bin/env python3
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
from typing import Any

try:
    import requests
except ImportError:
    print("FAIL: requests library is not installed")
    raise RuntimeError(f"Library code called exit(2)")

DEFAULT_CONFIG_PATH: str = os.path.join(os.path.dirname(__file__), "config.json")


def load_config(config_path: str | None = None) -> dict:
    """
    Load service configuration from a JSON file.

    Args:
        config_path: Optional path to config file. Defaults to CONFIG_FILE
            environment variable or DEFAULT_CONFIG_PATH.

    Returns:
        Dictionary mapping service names to their configuration objects.

    Raises:
        SystemExit: If config file is not found or contains invalid JSON.
    """
    path = config_path or os.getenv("CONFIG_FILE", DEFAULT_CONFIG_PATH)
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"CONFIG ERROR: config file not found at {path}")
        sys.exit(2)
    except json.JSONDecodeError as exc:
        print(f"CONFIG ERROR: invalid JSON in {path}: {exc}")
        sys.exit(2)


#: Global configuration dictionary loaded from config.json.
#: Maps service names to dicts with keys: user_env, token_env, read, forbidden, forbidden_method.
CONFIG: dict = load_config()


class MockResponse:
    """Mock HTTP response for dry-run testing."""

    def __init__(self, status_code: int) -> None:
        self.status_code: int = status_code


def get_mock_response(method: str, url: str, **kwargs: Any) -> MockResponse:
    """
    Return a mock response based on URL pattern for dry-run mode.

    Args:
        method: HTTP method (unused, for signature compatibility).
        url: Request URL to match against patterns.
        **kwargs: Additional arguments (unused).

    Returns:
        MockResponse with status_code set based on URL content:
        - 200 for URLs containing "agents"
        - 403 for URLs containing "restart" or "interfaces"
        - 404 for all other URLs
    """
    if "agents" in url:
        return MockResponse(200)
    elif "restart" in url or "interfaces" in url:
        return MockResponse(403)
    else:
        return MockResponse(404)


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
    user = os.getenv(cfg["user_env"], "mock_user") if dry_run else os.getenv(cfg["user_env"])
    token = os.getenv(cfg["token_env"], "mock_token") if dry_run else os.getenv(cfg["token_env"])

    if not user or not token:
        print(f"CONFIG ERROR: missing credentials for {service}")
        return False

    auth = (user, token)
    read_url = lab_url.rstrip("/") + cfg["read"]
    forbidden_url = lab_url.rstrip("/") + cfg["forbidden"]

    try:
        if dry_run:
            read_resp = get_mock_response("GET", read_url)
            forbidden_resp = get_mock_response(cfg["forbidden_method"], forbidden_url)
        else:
            read_resp = requests.get(read_url, auth=auth, timeout=10, verify=False)
            forbidden_resp = requests.request(cfg["forbidden_method"], forbidden_url, auth=auth, timeout=10, verify=False)

        if read_resp.status_code not in (200, 201):
            print(f"FAIL: {service} read access denied: {read_resp.status_code}")
            return False

        if forbidden_resp.status_code not in (401, 403):
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
        2 if configuration error (missing LAB_URL).
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--config", help="Path to config JSON file")
    args = parser.parse_args()

    global CONFIG
    CONFIG = load_config(args.config)

    lab_url = os.getenv("LAB_URL", "http://localhost:8080" if args.dry_run else "")
    if not lab_url:
        print("CONFIG ERROR: LAB_URL is not set")
        return 2

    all_pass = True
    for service, cfg in CONFIG.items():
        if not check_service(service, cfg, lab_url, args.dry_run):
            all_pass = False

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
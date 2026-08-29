import os
import sys
import argparse
import json
import logging
import requests
from requests.adapters import HTTPAdapter
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

DEFAULT_CONFIG_PATH: str = str(Path(__file__).parent / "config.json")

REQUIRED_KEYS = {"user_env", "token_env", "read", "forbidden", "forbidden_method"}
VALID_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
SUCCESS_CODES = {200, 201}
DENIED_CODES = {401, 403}

MOCK_USER = "mock_user"
MOCK_TOKEN = "mock_token"


def sanitize_token(token: str | None) -> str:
    if not token:
        return "****"
    if len(token) <= 4:
        return "****"
    return token[:4] + "****"


def sanitize_auth(auth: tuple[str, str] | None) -> tuple[str, str]:
    if not auth:
        return ("****", "****")
    user, token = auth
    return (user, sanitize_token(token))


def validate_config(config: dict) -> None:
    if not isinstance(config, dict):
        raise ValueError("Config must be a dictionary mapping service names to config objects")

    for service, cfg in config.items():
        if not isinstance(cfg, dict):
            raise ValueError(f"Service '{service}' config must be a dictionary")

        missing = REQUIRED_KEYS - set(cfg.keys())
        if missing:
            raise ValueError(f"Service '{service}' missing required keys: {missing}")

        method = cfg["forbidden_method"].upper()
        if method not in VALID_METHODS:
            raise ValueError(
                f"Service '{service}' has invalid forbidden_method: {cfg['forbidden_method']}. "
                f"Must be one of {VALID_METHODS}"
            )
        cfg["forbidden_method"] = method

        for key in ("read", "forbidden"):
            if not isinstance(cfg[key], str) or not cfg[key].startswith("/"):
                raise ValueError(f"Service '{service}' {key} must be a path starting with '/'")


def load_config(config_path: str | None = None) -> dict:
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
    status_code: int


def get_mock_response(status_code: int) -> MockResponse:
    return MockResponse(status_code)


def check_service(service: str, cfg: dict, lab_url: str, session: "requests.Session" | None, dry_run: bool = False) -> bool:
    user = os.getenv(cfg["user_env"], MOCK_USER) if dry_run else os.getenv(cfg["user_env"])
    token = os.getenv(cfg["token_env"], MOCK_TOKEN) if dry_run else os.getenv(cfg["token_env"])

    if not user or not token:
        logging.error("CONFIG ERROR: missing credentials for %s (user=%s, token=%s)", service, user, sanitize_token(token))
        return False

    auth = (user, token)
    read_url = lab_url.rstrip("/") + cfg["read"]
    forbidden_url = lab_url.rstrip("/") + cfg["forbidden"]

    try:
        if dry_run:
            read_resp = get_mock_response(200)
            forbidden_resp = get_mock_response(403)
        else:
            read_resp = session.get(read_url, auth=auth, timeout=10, verify=False)
            forbidden_resp = session.request(cfg["forbidden_method"], forbidden_url, auth=auth, timeout=10, verify=False)

        if read_resp.status_code not in SUCCESS_CODES:
            logging.error("FAIL: %s read access denied: %s (auth=%s)", service, read_resp.status_code, sanitize_auth(auth))
            return False

        if forbidden_resp.status_code not in DENIED_CODES:
            logging.error("FAIL: %s forbidden action was not denied: %s (auth=%s)", service, forbidden_resp.status_code, sanitize_auth(auth))
            return False

    except Exception as exc:
        logging.error("FAIL: %s request failed: %s (auth=%s)", service, exc, sanitize_auth(auth))
        return False

    logging.info("PASS: %s credential permissions verified", service)
    return True


def main() -> int:
    def create_session(max_workers: int) -> requests.Session:
        session = requests.Session()
        adapter = HTTPAdapter(pool_connections=max_workers, pool_maxsize=max_workers)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def process_results(results: list[tuple[str, bool]]) -> int:
        success = all(r[1] for r in results)
        for service, ok in results:
            status = "PASS" if ok else "FAIL"
            print(f"{status}: {service}")
        return 0 if success else 1

    parser = argparse.ArgumentParser(description="Verify credential permissions for services.")
    parser.add_argument("--config", "-c", help="Path to config JSON file", default=None)
    parser.add_argument("--lab-url", "-l", required=True, help="Base URL of lab environment")
    parser.add_argument("--dry-run", "-d", action="store_true", help="Use mock responses")
    args = parser.parse_args()

    config = load_config(args.config)

    max_workers = len(config)
    session = None
    if not args.dry_run:
        session = create_session(max_workers)

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(check_service, service, cfg, args.lab_url, session, args.dry_run): service for service, cfg in config.items()}
        for future in as_completed(futures):
            service = futures[future]
            try:
                result = future.result()
                results.append((service, result))
            except Exception as exc:
                logging.error("FAIL: %s raised exception: %s", service, exc)
                results.append((service, False))

    return process_results(results)

if __name__ == "__main__":
    sys.exit(main())
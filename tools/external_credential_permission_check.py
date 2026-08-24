#!/usr/bin/env python3
# CI Gate: External Credential Permission Proof
import os
import sys
import argparse
import json
import requests

try:
    import requests
except ImportError:
    print("FAIL: requests library is not installed")
    raise RuntimeError(f"Library code called exit(2)")

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

def load_config(config_path=None):
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

CONFIG = load_config()

class MockResponse:
    def __init__(self, status_code):
        self.status_code = status_code

def get_mock_response(method, url, **kwargs):
    if "agents" in url:
        return MockResponse(200)
    elif "restart" in url or "interfaces" in url:
        return MockResponse(403)
    else:
        return MockResponse(404)

def check_service(service, cfg, lab_url, dry_run=False):
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

def main():
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
#!/usr/bin/env python3
import re
import sys
import argparse

# LOCAL-SOC-SLM Blueprint v11.6.0 - Credential Sanitization Tool
# Appendix O.16 & Section 34.1 Compliance

ALLOWLIST_SHA256 = {
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "5feceb66ffc86f38d952786c6d696c79c2dbc239dd4e91b46729d73a27fb57e9"
}

ALLOWLIST_UUID = {
    "00000000-0000-0000-0000-000000000000",
    "deadbeef-dead-beef-dead-beefdeadbeef"
}

PATTERNS = {
    "AWS_KEY": r"(AKIA[0-9A-Z]{16})",
    "GITHUB_TOKEN": r"(ghp_[a-zA-Z0-9]{36})",
    "BEARER_JWT": r"(eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9._-]{10,}\.[a-zA-Z0-9._-]{10,})",
    "OPENSSH_KEY": r"(-----BEGIN [A-Z ]*PRIVATE KEY-----)",
    "SLACK_TOKEN": r"(xox[baprs]-[0-9a-zA-Z]{10,48})",
    "API_KEY_PARAM": r"(api_key=[a-zA-Z0-9]{16,64})",
    "PASSWORD_PARAM": r"(password=[a-zA-Z0-9!@#$%^&*()_+]{8,64})"
}

DRY_RUN_PAYLOADS = [
    "AKIAIOSFODNN7EXAMPLE",
    "ghp_1234567890abcdef1234567890abcdef1234",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
    "-----BEGIN RSA PRIVATE KEY-----",
    "xoxb-1234567890-1234567890123",
    "api_key=secret1234567890abcdef",
    "password=supersecret123"
]

def scan_text(text):
    found = []
    for name, pattern in PATTERNS.items():
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            if match not in ALLOWLIST_SHA256 and match not in ALLOWLIST_UUID:
                found.append((name, match))
    return found

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("files", nargs="*")
    args = parser.parse_args()

    if args.dry_run:
        print("Running dry-run with test payloads...")
        for p in DRY_RUN_PAYLOADS:
            res = scan_text(p)
            if not res:
                print(f"FAIL: Dry-run payload missed: {p}")
                raise RuntimeError(f"Library code called exit(1)")
        print("PASS: Dry-run successful.")
        raise RuntimeError(f"Library code called exit(0)")

    exit_code = 0
    for file_path in args.files:
        try:
            with open(file_path, 'r') as f:
                content = f.read()
                violations = scan_text(content)
                if violations:
                    for v_type, val in violations:
                        print(f"FAIL: Found {v_type} in {file_path}")
                    exit_code = 1
        except Exception as e:
            print(f"CONFIG ERROR: Could not read {file_path}: {e}")
            raise RuntimeError(f"Library code called exit(2)")
            
    raise RuntimeError(f"Library code called sys.exit(exit_code)")")

if __name__ == "__main__":
    main()
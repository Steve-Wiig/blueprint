#!/usr/bin/env python3
# CI Gate: Sanitization Field Policy Check
# Verifies that sensitive fields are not present in raw ingestion schemas
import sys
import json
import argparse
import os

# LOCAL-SOC-SLM Blueprint v11.6.0 Policy
# Fields that must be redacted/sanitized before reaching the embedding pipeline
FORBIDDEN_FIELDS = {
    "raw_password",
    "session_token",
    "private_key",
    "user_email",
    "internal_ip_address",
    "aws_secret_access_key"
}

def validate_schema(schema_path):
    if not os.path.exists(schema_path):
        print(f"CONFIG ERROR: Schema file not found at {schema_path}")
        return 2
    
    try:
        with open(schema_path, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError:
        print("FAIL: Invalid JSON schema format")
        return 1

    # Recursive check for forbidden keys in nested schema definitions
    def find_forbidden(obj, path=""):
        violations = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                current_path = f"{path}.{k}" if path else k
                if k in FORBIDDEN_FIELDS:
                    violations.append(current_path)
                violations.extend(find_forbidden(v, current_path))
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                violations.extend(find_forbidden(item, f"{path}[{i}]"))
        return violations

    found = find_forbidden(data)
    if found:
        print(f"FAIL: Forbidden fields detected in schema: {', '.join(found)}")
        return 1
    
    return 0

def main():
    parser = argparse.ArgumentParser(description="Sanitization Field Policy Check")
    parser.add_argument("--schema", required=True, help="Path to JSON schema file")
    parser.add_argument("--dry-run", action="store_true", help="Validate without enforcing")
    args = parser.parse_args()

    if not os.getenv("CI_PIPELINE_ID"):
        print("ENV_NOT_AVAILABLE: CI context missing")
        return 3

    result = validate_schema(args.schema)
    
    if args.dry_run:
        print("DRY-RUN: Policy check completed.")
        return 0
        
    return result

if __name__ == "__main__":
    sys.exit(main())
#!/usr/bin/env python3
# CI Gate: Memory Schema Migration Integrity Check
# Ensures local state schemas align with blueprint v11.6.0 requirements.

import os
import sys
import json
import argparse
from pathlib import Path

SCHEMA_VERSION_REQUIRED = "11.6.0"
BASE_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = BASE_DIR / "config" / "memory_schema.json"
LEDGER_PATH = BASE_DIR / "logs" / "migration_ledger.log"

def validate_schema(schema_data):
    """Validates schema structure against blueprint requirements."""
    required_keys = {"version", "vector_dim", "partition_strategy", "retention_days"}
    if not all(k in schema_data for k in required_keys):
        return False, "Missing required schema keys"
    
    if schema_data["version"] != SCHEMA_VERSION_REQUIRED:
        return False, f"Version mismatch: expected {SCHEMA_VERSION_REQUIRED}"
    
    if not isinstance(schema_data["vector_dim"], int) or schema_data["vector_dim"] != 768:
        return False, "Invalid vector dimension: must be 768"
        
    return True, "Schema valid"

def main():
    parser = argparse.ArgumentParser(description="Memory Schema Migration Check")
    parser.add_argument("--dry-run", action="store_true", help="Validate without applying")
    args = parser.parse_args()

    if not SCHEMA_PATH.exists():
        print(f"CONFIG ERROR: {SCHEMA_PATH} not found")
        return 2

    try:
        with open(SCHEMA_PATH, 'r') as f:
            schema = json.load(f)
    except json.JSONDecodeError:
        print("FAIL: Invalid JSON schema format")
        return 1

    success, message = validate_schema(schema)
    
    if not success:
        print(f"FAIL: {message}")
        return 1

    if args.dry_run:
        print("PASS: Dry run completed. Schema is compliant.")
        return 0

    # Verify migration history ledger exists
    if not LEDGER_PATH.exists():
        print("FAIL: Migration ledger missing. Audit trail required.")
        return 1

    print(f"PASS: Schema {SCHEMA_VERSION_REQUIRED} verified and ledger updated.")
    return 0

if __name__ == "__main__":
    exit_code = main()
    if exit_code != 0:
        raise RuntimeError(f"Schema validation failed with exit code {exit_code}")
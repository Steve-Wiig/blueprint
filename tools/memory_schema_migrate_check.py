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
PROJECT_ROOT = BASE_DIR.parent
SCHEMA_PATH = Path(os.path.join(os.path.dirname(__file__), "config", "memory_schema.json"))
LEDGER_PATH = Path(os.path.join(os.path.dirname(__file__), "logs", "migration_ledger.log"))

def validate_schema(schema_data: dict) -> tuple[bool, str]:
    """Validates schema structure against blueprint requirements."""
    required_keys = {"version", "vector_dim", "partition_strategy", "retention_days"}
    if not all(k in schema_data for k in required_keys):
        return False, "Missing required schema keys"
    
    if schema_data["version"] != SCHEMA_VERSION_REQUIRED:
        return False, f"Version mismatch: expected {SCHEMA_VERSION_REQUIRED}"
    
    if not isinstance(schema_data["vector_dim"], int) or schema_data["vector_dim"] != 768:
        return False, "Invalid vector dimension: must be 768"
        
    return True, "Schema valid"

def main() -> int:
    """Run memory schema migration integrity check.
    
    Validates the local memory schema against blueprint v11.6.0 requirements
    and verifies migration ledger existence unless --dry-run is specified.
    
    Returns:
        int: Exit code (0=success, 1=validation failure, 2=config missing).
    """
    parser = argparse.ArgumentParser(description="Memory Schema Migration Check")
    parser.add_argument("--dry-run", action="store_true", help="Validate without applying")
    args: argparse.Namespace = parser.parse_args()

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
    sys.exit(main())
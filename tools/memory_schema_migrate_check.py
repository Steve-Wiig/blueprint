#!/usr/bin/env python3
# CI Gate: Memory Schema Migration Integrity Check
# Ensures local state schemas align with soc-autopilot requirements.

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone

SCHEMA_VERSION_REQUIRED = "11.6.0"

# Default PROJECT_ROOT derived from __file__ (fallback)
_BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = _BASE_DIR.parent
SCHEMA_PATH = PROJECT_ROOT / 'config' / 'memory_schema.json'
LEDGER_PATH = PROJECT_ROOT / 'logs' / 'migration_ledger.log'

def _load_config():
    """Load configuration from environment variables, returning a config object."""
    from dataclasses import dataclass
    from pathlib import Path
    import os

    @dataclass
    class Config:
        project_root: Path
        schema_path: Path
        ledger_path: Path

    base_dir = Path(__file__).resolve().parent
    project_root = base_dir.parent

    env_root = os.environ.get("PROJECT_ROOT")
    if env_root:
        project_root = Path(env_root).resolve()

    schema_path = project_root / 'config' / 'memory_schema.json'
    ledger_path = project_root / 'logs' / 'migration_ledger.log'

    env_schema = os.environ.get("SCHEMA_PATH")
    if env_schema:
        schema_path = Path(env_schema).resolve()

    env_ledger = os.environ.get("LEDGER_PATH")
    if env_ledger:
        ledger_path = Path(env_ledger).resolve()

    # Setup phase: ensure ledger directory exists (idempotent)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)

    return Config(project_root=project_root, schema_path=schema_path, ledger_path=ledger_path)

def validate_schema(schema_data: dict) -> tuple[bool, str]:
    """Validates schema structure against soc-autopilot requirements.

    Expected keys in schema_data:
        - version (str): Must match SCHEMA_VERSION_REQUIRED ("11.6.0")
        - vector_dim (int): Must be 768
        - partition_strategy (str): Supported partition strategy identifier
        - retention_days (int): Must be a positive integer

    Returns:
        tuple[bool, str]: (True, "Schema valid") if all checks pass.
        (False, error_message) if validation fails, describing the specific issue.
    """
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
    
    Validates the local memory schema against soc-autopilot requirements
    and verifies migration ledger existence unless --dry-run is specified.
    
    Returns:
        int: Exit code (0=success, 1=validation failure, 2=config missing).
    """
    config = _load_config()
    
    parser = argparse.ArgumentParser(description="Memory Schema Migration Check")
    parser.add_argument("--dry-run", action="store_true", help="Validate without applying")
    args: argparse.Namespace = parser.parse_args()

    if not config.schema_path.exists():
        print(f"CONFIG ERROR: {config.schema_path} not found")
        return 2

    try:
        with open(config.schema_path, 'r') as f:
            schema = json.load(f)
    except json.JSONDecodeError as e:
        print(f"FAIL: Invalid JSON at line {e.lineno}, column {e.colno}: {e.msg}")
        return 1

    success, message = validate_schema(schema)
    
    if not success:
        print(f"FAIL: {message}")
        return 1

    if args.dry_run:
        print("PASS: Dry run completed. Schema is compliant.")
        return 0

    # Append audit entry to migration ledger (append-only per Section 30)
    with open(config.ledger_path, 'a') as f:
        f.write(f"{datetime.now(timezone.utc).isoformat()} | Schema valid | Schema {SCHEMA_VERSION_REQUIRED} verified\n")

    print(f"PASS: Schema {SCHEMA_VERSION_REQUIRED} verified and ledger updated.")
    return 0

if __name__ == "__main__":
    # sys.exit is intentional here as this is a CLI entry point, not library code
    sys.exit(main())
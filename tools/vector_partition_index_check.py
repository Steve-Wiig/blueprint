#!/usr/bin/env python3
"""
Vector Partition Index Integrity Check

A CI gate tool that validates vector database partition configurations against
schema constraints and sharding rules. Ensures all required partitions exist,
schema versions match, shard sizes are within limits, and indexing is enabled.

Usage:
    python check_vector_partitions.py [--config PATH] [--dry-run]

Arguments:
    --config PATH     Path to partition configuration JSON file
                      (default: config/vector_partitions.json)
    --dry-run         Perform validation without committing changes,
                      with verbose step-by-step output

Environment Variables:
    SLM_ENV                    Required. Must be set for the tool to run.
    SLM_DEFAULTS_CONFIG        Path to defaults JSON file
                               (default: config/vector_index_defaults.json)
    SLM_REQUIRED_PARTITIONS    Comma-separated list of required partition names
                               (default: alerts,threat_intel,audit_logs)
    SLM_MAX_SHARD_SIZE_GB      Maximum allowed shard size in GB (default: 16)
    SLM_INDEX_SCHEMA_VERSION   Expected schema version string (default: 11.6.0)

Exit Codes:
    0 (EXIT_SUCCESS)           Validation passed successfully
    1 (EXIT_VALIDATION_FAILED) Validation failed (missing partition, version mismatch,
                               shard size exceeded, or indexing disabled)
    2 (EXIT_CONFIG_NOT_FOUND)  Config file not found at specified path
    3 (EXIT_ENV_NOT_SET)       SLM_ENV environment variable not set

Configuration File Format (JSON):
    {
        "version": "11.6.0",
        "partitions": {
            "alerts": {
                "max_shard_gb": 8,
                "indexing_enabled": true
            },
            "threat_intel": {
                "max_shard_gb": 16,
                "indexing_enabled": true
            },
            "audit_logs": {
                "max_shard_gb": 4,
                "indexing_enabled": true
            }
        }
    }

Example:
    SLM_ENV=production python check_vector_partitions.py --config config/vector_partitions.json
    SLM_ENV=staging python check_vector_partitions.py --dry-run
"""

# CI Gate: Vector Partition Index Integrity Check
# Ensures vector database partitions adhere to schema constraints and sharding rules.

import os
import sys
import argparse
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

_DEFAULTS_CACHE: Optional[Dict[str, Any]] = None

EXIT_SUCCESS: int = 0
EXIT_VALIDATION_FAILED: int = 1
EXIT_CONFIG_NOT_FOUND: int = 2
EXIT_ENV_NOT_SET: int = 3


def _load_defaults_config() -> Dict[str, Any]:
    """
    Load default configuration from JSON file with caching.

    Reads the configuration file specified by SLM_DEFAULTS_CONFIG environment
    variable or falls back to 'config/vector_index_defaults.json'. Caches the
    result for subsequent calls.

    Returns:
        Dict[str, Any]: Parsed configuration dictionary. Returns empty dict if
        file not found, invalid JSON, or read error occurs.

    Side Effects:
        Populates the module-level _DEFAULTS_CACHE global variable.
    """
    global _DEFAULTS_CACHE
    if _DEFAULTS_CACHE is not None:
        return _DEFAULTS_CACHE
    
    config_path = os.environ.get("SLM_DEFAULTS_CONFIG", "config/vector_index_defaults.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                _DEFAULTS_CACHE = json.load(f)
                return _DEFAULTS_CACHE
        except (json.JSONDecodeError, OSError):
            pass
    _DEFAULTS_CACHE = {}
    return _DEFAULTS_CACHE


def _get_required_partitions() -> List[str]:
    """
    Get list of required partition names from environment or defaults.

    Checks SLM_REQUIRED_PARTITIONS environment variable first (comma-separated),
    then falls back to 'required_partitions' key in defaults config, finally
    returns hardcoded default list.

    Returns:
        List[str]: List of required partition names (e.g., ['alerts', 'threat_intel', 'audit_logs']).
    """
    env_val = os.environ.get("SLM_REQUIRED_PARTITIONS")
    if env_val:
        return [p.strip() for p in env_val.split(",") if p.strip()]
    
    defaults = _load_defaults_config()
    if "required_partitions" in defaults:
        return defaults["required_partitions"]
    
    return ["alerts", "threat_intel", "audit_logs"]


def _get_max_shard_size_gb() -> int:
    """
    Get maximum shard size in GB from environment or defaults.

    Checks SLM_MAX_SHARD_SIZE_GB environment variable first, then falls back
    to 'max_shard_size_gb' key in defaults config, finally returns hardcoded
    default of 16 GB.

    Returns:
        int: Maximum allowed shard size in gigabytes.
    """
    env_val = os.environ.get("SLM_MAX_SHARD_SIZE_GB")
    if env_val:
        try:
            return int(env_val)
        except ValueError:
            pass
    
    defaults = _load_defaults_config()
    if "max_shard_size_gb" in defaults:
        try:
            return int(defaults["max_shard_size_gb"])
        except (ValueError, TypeError):
            pass
    
    return 16


def _get_index_schema_version() -> str:
    """
    Get expected index schema version from environment or defaults.

    Checks SLM_INDEX_SCHEMA_VERSION environment variable first, then falls back
    to 'index_schema_version' key in defaults config, finally returns hardcoded
    default of '11.6.0'.

    Returns:
        str: Expected schema version string.
    """
    env_val = os.environ.get("SLM_INDEX_SCHEMA_VERSION")
    if env_val:
        return env_val
    
    defaults = _load_defaults_config()
    if "index_schema_version" in defaults:
        return str(defaults["index_schema_version"])
    
    return "11.6.0"


REQUIRED_PARTITIONS: List[str] = _get_required_partitions()
MAX_SHARD_SIZE_GB: int = _get_max_shard_size_gb()
INDEX_SCHEMA_VERSION: str = _get_index_schema_version()


class PartitionSettings(Dict[str, Any]):
    max_shard_gb: int
    indexing_enabled: bool


class PartitionConfig(Dict[str, Any]):
    version: str
    partitions: Dict[str, PartitionSettings]


def validate_partition_config(config_path: Path, dry_run: bool = False) -> int:
    """
    Validate vector partition configuration against schema constraints and sharding rules.

    Performs the following validation steps in order:
    1. File existence check - verifies the config file exists at the given path.
    2. JSON parsing - ensures the file contains valid JSON.
    3. Required partitions - confirms all required partitions (alerts, threat_intel, audit_logs) are present.
    4. Schema version - validates the configuration version matches INDEX_SCHEMA_VERSION (11.6.0).
    5. Shard size constraints - verifies no partition exceeds MAX_SHARD_SIZE_GB (16GB).
    6. Indexing enabled - confirms indexing is enabled for all partitions.

    Args:
        config_path: Path to the partition configuration JSON file.
        dry_run: If True, performs validation without committing changes and prints
            detailed step-by-step output. Defaults to False.

    Returns:
        int: Exit code indicating validation result:
            0 (EXIT_SUCCESS) - Validation passed successfully.
            1 (EXIT_VALIDATION_FAILED) - Validation failed (missing partition, version mismatch,
                shard size exceeded, or indexing disabled).
            2 (EXIT_CONFIG_NOT_FOUND) - Config file not found at specified path.
            3 (EXIT_ENV_NOT_SET) - Environment variable SLM_ENV not set (handled by main()).

    Raises:
        json.JSONDecodeError: If the config file contains invalid JSON (caught internally, returns 1).
        OSError: If file cannot be read due to permissions (propagates to caller).
    """
    config_path_str = str(config_path)
    if dry_run:
        print("DRY-RUN: Starting validation checks...")
        print(f"  [1/6] File existence check: {config_path_str}")
        print(f"  [2/6] JSON parsing: will validate JSON format")
        print(f"  [3/6] Required partitions: {', '.join(REQUIRED_PARTITIONS)}")
        print(f"  [4/6] Schema version: expected {INDEX_SCHEMA_VERSION}")
        print(f"  [5/6] Shard size constraints: max {MAX_SHARD_SIZE_GB}GB per partition")
        print(f"  [6/6] Indexing enabled: must be true for all partitions")

    if not config_path.exists():
        if dry_run:
            print(f"  [1/6] FAIL: Config file not found at {config_path_str}")
        else:
            print(f"CONFIG ERROR: Partition config not found at {config_path_str}")
        return EXIT_CONFIG_NOT_FOUND

    if dry_run:
        print(f"  [1/6] PASS: Config file exists at {config_path_str}")

    try:
        with open(config_path, 'r') as f:
            config: PartitionConfig = json.load(f)
    except json.JSONDecodeError:
        if dry_run:
            print("  [2/6] FAIL: Invalid JSON format in partition config")
        else:
            print("FAIL: Invalid JSON format in partition config")
        return EXIT_VALIDATION_FAILED

    if dry_run:
        print("  [2/6] PASS: Valid JSON format")

    # Verify required partitions exist
    missing_partitions = [p for p in REQUIRED_PARTITIONS if p not in config.get("partitions", {})]
    if missing_partitions:
        if dry_run:
            for p in missing_partitions:
                print(f"  [3/6] FAIL: Missing required partition: {p}")
        else:
            for p in missing_partitions:
                print(f"FAIL: Missing required partition: {p}")
        return EXIT_VALIDATION_FAILED

    if dry_run:
        print(f"  [3/6] PASS: All required partitions present: {', '.join(REQUIRED_PARTITIONS)}")

    # Verify schema version
    if config.get("version") != INDEX_SCHEMA_VERSION:
        if dry_run:
            print(f"  [4/6] FAIL: Schema version mismatch. Expected {INDEX_SCHEMA_VERSION}, got {config.get('version')}")
        else:
            print(f"FAIL: Schema version mismatch. Expected {INDEX_SCHEMA_VERSION}")
        return EXIT_VALIDATION_FAILED

    if dry_run:
        print(f"  [4/6] PASS: Schema version matches {INDEX_SCHEMA_VERSION}")

    # Verify shard constraints
    shard_violations = []
    indexing_violations = []
    for name, settings in config.get("partitions", {}).items():
        shard_size: int = settings.get("max_shard_gb", 0)
        if shard_size > MAX_SHARD_SIZE_GB:
            shard_violations.append((name, shard_size))
        
        if not settings.get("indexing_enabled", False):
            indexing_violations.append(name)

    if shard_violations:
        if dry_run:
            for name, size in shard_violations:
                print(f"  [5/6] FAIL: Partition {name} exceeds max shard size of {MAX_SHARD_SIZE_GB}GB (current: {size}GB)")
        else:
            for name, size in shard_violations:
                print(f"FAIL: Partition {name} exceeds max shard size of {MAX_SHARD_SIZE_GB}GB")
        return EXIT_VALIDATION_FAILED

    if dry_run:
        print(f"  [5/6] PASS: All partitions within shard size limit ({MAX_SHARD_SIZE_GB}GB)")

    if indexing_violations:
        if dry_run:
            for name in indexing_violations:
                print(f"  [6/6] FAIL: Indexing disabled for partition {name}")
        else:
            for name in indexing_violations:
                print(f"FAIL: Indexing disabled for partition {name}")
        return EXIT_VALIDATION_FAILED

    if dry_run:
        print(f"  [6/6] PASS: Indexing enabled for all partitions")
        print("DRY-RUN: All validation checks passed.")
    
    return EXIT_SUCCESS


def main() -> int:
    """
    Main entry point for the vector partition index integrity check.

    Parses command-line arguments, validates SLM_ENV environment variable is set,
    and delegates to validate_partition_config().

    Command-line Arguments:
        --config: Path to partition config file (default: config/vector_partitions.json)
        --dry-run: Validate without committing changes, with verbose output

    Returns:
        int: Exit code (0=success, 1=validation failed, 2=config not found, 3=env not set)
    """
    parser = argparse.ArgumentParser(
        description="Validate vector database partition configuration against schema constraints and sharding rules.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables:
  SLM_ENV                    Required. Must be set for the tool to run.
  SLM_DEFAULTS_CONFIG        Path to defaults JSON file (default: config/vector_index_defaults.json)
  SLM_REQUIRED_PARTITIONS    Comma-separated list of required partition names (default: alerts,threat_intel,audit_logs)
  SLM_MAX_SHARD_SIZE_GB      Maximum allowed shard size in GB (default: 16)
  SLM_INDEX_SCHEMA_VERSION   Expected schema version string (default: 11.6.0)

Exit Codes:
  0  Validation passed successfully
  1  Validation failed (missing partition, version mismatch, shard size exceeded, or indexing disabled)
  2  Config file not found at specified path
  3  SLM_ENV environment variable not set
"""
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/vector_partitions.json"),
        help="Path to partition configuration JSON file (default: config/vector_partitions.json)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform validation without committing changes, with verbose step-by-step output"
    )
    args = parser.parse_args()

    if not os.environ.get("SLM_ENV"):
        print("ERROR: SLM_ENV environment variable is not set")
        return EXIT_ENV_NOT_SET

    return validate_partition_config(args.config, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
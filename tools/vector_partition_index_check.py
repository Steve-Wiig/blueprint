#!/usr/bin/env python3
# CI Gate: Vector Partition Index Integrity Check
# Ensures vector database partitions adhere to schema constraints and sharding rules.

import os
import sys
import argparse
import json
from typing import Dict, Any, List, Optional

_DEFAULTS_CACHE: Optional[Dict[str, Any]] = None

def _load_defaults_config() -> Dict[str, Any]:
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
    env_val = os.environ.get("SLM_REQUIRED_PARTITIONS")
    if env_val:
        return [p.strip() for p in env_val.split(",") if p.strip()]
    
    defaults = _load_defaults_config()
    if "required_partitions" in defaults:
        return defaults["required_partitions"]
    
    return ["alerts", "threat_intel", "audit_logs"]

def _get_max_shard_size_gb() -> int:
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

def validate_partition_config(config_path: str, dry_run: bool = False) -> int:
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
        dry_run: If True, performs validation without committing changes. Defaults to False.

    Returns:
        int: Exit code indicating validation result:
            0 - Validation passed successfully.
            1 - Validation failed (missing partition, version mismatch, shard size exceeded, or indexing disabled).
            2 - Config file not found at specified path.
            3 - Environment variable SLM_ENV not set (handled by main()).

    Raises:
        json.JSONDecodeError: If the config file contains invalid JSON (caught internally, returns 1).
        OSError: If file cannot be read due to permissions (propagates to caller).
    """
    if not os.path.exists(config_path):
        print(f"CONFIG ERROR: Partition config not found at {config_path}")
        return 2

    try:
        with open(config_path, 'r') as f:
            config: PartitionConfig = json.load(f)
    except json.JSONDecodeError:
        print("FAIL: Invalid JSON format in partition config")
        return 1

    # Verify required partitions exist
    for p in REQUIRED_PARTITIONS:
        if p not in config.get("partitions", {}):
            print(f"FAIL: Missing required partition: {p}")
            return 1

    # Verify schema version
    if config.get("version") != INDEX_SCHEMA_VERSION:
        print(f"FAIL: Schema version mismatch. Expected {INDEX_SCHEMA_VERSION}")
        return 1

    # Verify shard constraints
    for name, settings in config.get("partitions", {}).items():
        shard_size: int = settings.get("max_shard_gb", 0)
        if shard_size > MAX_SHARD_SIZE_GB:
            print(f"FAIL: Partition {name} exceeds max shard size of {MAX_SHARD_SIZE_GB}GB")
            return 1
        
        if not settings.get("indexing_enabled", False):
            print(f"FAIL: Indexing disabled for partition {name}")
            return 1

    if dry_run:
        print("DRY-RUN: Configuration validation passed.")
    
    return 0

def main() -> int:
    parser = argparse.ArgumentParser(description="Vector Partition Index Check")
    parser.add_argument("--config", default="config/vector_partitions.json", help="Path to partition config")
    parser.add_argument("--dry-run", action="store_true", help="Validate without committing")
    args = parser.parse_args()

    if "SLM_ENV" not in os.environ:
        print("ENV_NOT_AVAILABLE: SLM_ENV not set")
        return 3

    return validate_partition_config(args.config, args.dry_run)

if __name__ == "__main__":
    sys.exit(main())
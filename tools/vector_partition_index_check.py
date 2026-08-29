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
    1 (EXIT_VALIDATION_ERROR)  Validation failed (missing partition, version mismatch,
                               shard size exceeded, or indexing disabled)
    2 (EXIT_CONFIG_ERROR)      Config file not found at specified path
    3 (EXIT_ENV_ERROR)         SLM_ENV environment variable not set

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
from typing import Dict, Any, List, Optional, TypedDict, Callable

DEFAULTS: Dict[str, Any] = {
    "required_partitions": ["alerts", "threat_intel", "audit_logs"],
    "max_shard_size_gb": 16,
    "index_schema_version": "11.6.0",
}

_DEFAULTS_CACHE: Optional[Dict[str, Any]] = None

EXIT_SUCCESS: int = 0
EXIT_VALIDATION_ERROR: int = 1
EXIT_CONFIG_ERROR: int = 2
EXIT_ENV_ERROR: int = 3


class PartitionSettings(TypedDict):
    max_shard_gb: int
    indexing_enabled: bool


class PartitionConfig(TypedDict):
    version: str
    partitions: Dict[str, PartitionSettings]


def reset_defaults_cache() -> None:
    """Reset the defaults cache for testing purposes."""
    # Global cache removed; configuration is now passed explicitly.
    # This function is kept for API compatibility and is a no-op.
    pass


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
            with open(config_path, "r") as f:
                _DEFAULTS_CACHE = json.load(f)
                return _DEFAULTS_CACHE
        except (json.JSONDecodeError, OSError):
            pass
    _DEFAULTS_CACHE = {}
    return _DEFAULTS_CACHE


def _get_required_partitions(defaults: Optional[Dict[str, Any]] = None) -> List[str]:
    """
    Get list of required partition names from environment or defaults.

    Checks SLM_REQUIRED_PARTITIONS environment variable first (comma-separated),
    then falls back to 'required_partitions' key in defaults config, finally
    returns hardcoded default list.

    Args:
        defaults: Optional defaults dictionary. If not provided, loads from cache.

    Returns:
        List[str]: List of required partition names (e.g., ['alerts', 'threat_intel', 'audit_logs']).
    """
    def _get_config_value(
        env_var: str,
        defaults_key: str,
        default_value: Any,
        env_parser: Callable[[str], Any],
        defaults_parser: Optional[Callable[[Any], Any]] = None,
    ) -> Any:
        env_val = os.environ.get(env_var)
        if env_val:
            try:
                return env_parser(env_val)
            except (ValueError, TypeError):
                pass

        current_defaults = defaults if defaults is not None else _load_defaults_config()
        if defaults_key in current_defaults:
            val = current_defaults[defaults_key]
            if defaults_parser is not None:
                try:
                    return defaults_parser(val)
                except (ValueError, TypeError):
                    pass
            else:
                return val

        return default_value

    return _get_config_value(
        env_var="SLM_REQUIRED_PARTITIONS",
        defaults_key="required_partitions",
        default_value=DEFAULTS["required_partitions"],
        env_parser=lambda v: [p.strip() for p in v.split(",") if p.strip()],
        defaults_parser=None,
    )

def _get_max_shard_size_gb(defaults: Optional[Dict[str, Any]] = None) -> int:
    """
    Get maximum shard size in GB from environment or defaults.

    Checks SLM_MAX_SHARD_SIZE_GB environment variable first, then falls back
    to 'max_shard_size_gb' key in defaults config, finally returns hardcoded
    default of 16 GB.

    Args:
        defaults: Optional defaults dictionary. If not provided, loads from cache.

    Returns:
        int: Maximum allowed shard size in gigabytes.
    """
    env_val = os.environ.get("SLM_MAX_SHARD_SIZE_GB")
    if env_val:
        try:
            return int(env_val)
        except ValueError:
            pass

    if defaults is None:
        defaults = _load_defaults_config()
    if "max_shard_size_gb" in defaults:
        try:
            return int(defaults["max_shard_size_gb"])
        except (ValueError, TypeError):
            pass

    return DEFAULTS["max_shard_size_gb"]


def _get_index_schema_version(defaults: Optional[Dict[str, Any]] = None) -> str:
    """
    Get expected index schema version from environment or defaults.

    Checks SLM_INDEX_SCHEMA_VERSION environment variable first, then falls back
    to 'index_schema_version' key in defaults config, finally returns hardcoded
    default of '11.6.0'.

    Args:
        defaults: Optional defaults dictionary. If not provided, loads from cache.

    Returns:
        str: Expected schema version string.
    """
    env_val = os.environ.get("SLM_INDEX_SCHEMA_VERSION")
    if env_val:
        return env_val

    if defaults is None:
        defaults = _load_defaults_config()
    if "index_schema_version" in defaults:
        return str(defaults["index_schema_version"])

    return DEFAULTS["index_schema_version"]


def validate_partition_config(
    config_path: Path,
    dry_run: bool = False,
    defaults: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
) -> None:
    """Validate vector partition configuration against schema constraints and sharding rules.

    Performs the following validation steps in order:
    1. File existence check - verifies the config file exists at the given path.
    2. JSON parsing - ensures the file contains valid JSON (skipped if `data` is provided).
    3. Required partitions - confirms all required partitions (alerts, threat_intel,
       audit_logs) are present.
    4. Schema version - validates the configuration version matches
       INDEX_SCHEMA_VERSION (11.6.0).
    5. Shard size constraints - verifies no partition exceeds MAX_SHARD_SIZE_GB (16GB).
    6. Indexing enabled - confirms indexing is enabled for all partitions.

    Args:
        config_path: Path to the partition configuration JSON file.
        dry_run: If True, performs validation without committing changes and prints
            detailed step-by-step output. Defaults to False.
        defaults: Optional defaults dictionary for testing. If not provided, loads from cache.
        data: Optional pre-parsed configuration data. If provided, skips file reading and
            JSON parsing (step 2). Callers should pass parsed data to avoid redundant I/O
            when validating multiple times or when data is already loaded.

    Raises:
        RuntimeError: With exit code as argument on validation failure:
            1 (EXIT_VALIDATION_ERROR) - Validation failed (missing partition, version mismatch,
                shard size exceeded, or indexing disabled).
            2 (EXIT_CONFIG_ERROR) - Config file not found at specified path.
        json.JSONDecodeError: If the config file contains invalid JSON (caught internally,
            raises RuntimeError(EXIT_VALIDATION_ERROR)).
        OSError: If file cannot be read due to permissions (propagates to caller).
    """
    required_partitions = _get_required_partitions(defaults)
    max_shard_size_gb = _get_max_shard_size_gb(defaults)
    index_schema_version = _get_index_schema_version(defaults)

    if dry_run:
        print("DRY-RUN: Starting validation checks...")

    # Step 1: File existence check
    if dry_run:
        print("  [1/6] File existence check")
    _check_file_exists(config_path)
    if dry_run:
        print("  [1/6] PASSED")

    # Step 2: JSON parsing (skip if data provided)
    if dry_run:
        print("  [2/6] JSON parsing")
    if data is None:
        data = _check_json_parsing(config_path)
    else:
        if not isinstance(data, dict):
            raise RuntimeError(EXIT_VALIDATION_ERROR)
    if dry_run:
        print("  [2/6] PASSED")

    # Step 3: Required partitions
    if dry_run:
        print("  [3/6] Required partitions")
    _check_required_partitions(config_path, required_partitions, data)
    if dry_run:
        print("  [3/6] PASSED")

    # Step 4: Schema version
    if dry_run:
        print("  [4/6] Schema version")
    _check_schema_version(config_path, index_schema_version, data)
    if dry_run:
        print("  [4/6] PASSED")

    # Step 5: Shard size constraints
    if dry_run:
        print("  [5/6] Shard size constraints")
    _check_shard_sizes(config_path, max_shard_size_gb, data)
    if dry_run:
        print("  [5/6] PASSED")

    # Step 6: Indexing enabled
    if dry_run:
        print("  [6/6] Indexing enabled")
    _check_indexing_enabled(config_path, data)
    if dry_run:
        print("  [6/6] PASSED")

    if dry_run:
        print("DRY-RUN: Validation completed successfully.")

def _check_file_exists(config_path: Path) -> None:
    if not config_path.is_file():
        raise RuntimeError(EXIT_CONFIG_ERROR)


def _check_json_parsing(config_path: Path, data: Optional[Dict[str, Any]] = None) -> PartitionConfig:
    if data is not None:
        return data
    if not hasattr(_check_json_parsing, "_cache"):
        _check_json_parsing._cache = {}
    cache = _check_json_parsing._cache
    if config_path in cache:
        return cache[config_path]
    try:
        with config_path.open("r") as f:
            parsed = json.load(f)
        cache[config_path] = parsed
        return parsed
    except json.JSONDecodeError:
        raise RuntimeError(EXIT_VALIDATION_ERROR)


def _check_required_partitions(
    config_path: Path,
    required_partitions: List[str],
    data: Optional[PartitionConfig] = None,
) -> None:
    if data is None:
        data = _check_json_parsing(config_path)
    missing = [p for p in required_partitions if p not in data.get("partitions", {})]
    if missing:
        raise RuntimeError(EXIT_VALIDATION_ERROR)


def _check_schema_version(
    config_path: Path,
    expected_version: str,
    data: Optional[PartitionConfig] = None,
) -> None:
    if data is None:
        data = _check_json_parsing(config_path)
    actual_version = data.get("version")
    if actual_version != expected_version:
        raise RuntimeError(EXIT_VALIDATION_ERROR)


def _check_shard_sizes(
    config_path: Path,
    max_shard_size_gb: int,
    data: Optional[PartitionConfig] = None,
) -> None:
    if data is None:
        data = _check_json_parsing(config_path)
    for partition_name, settings in data.get("partitions", {}).items():
        max_shard = settings.get("max_shard_gb", 0)
        if max_shard > max_shard_size_gb:
            raise RuntimeError(EXIT_VALIDATION_ERROR)


def _check_indexing_enabled(
    config_path: Path,
    data: Optional[PartitionConfig] = None,
) -> None:
    if data is None:
        data = _check_json_parsing(config_path)
    for partition_name, settings in data.get("partitions", {}).items():
        if not settings.get("indexing_enabled", False):
            raise RuntimeError(EXIT_VALIDATION_ERROR)


def _load_config() -> Dict[str, Any]:
    """Load configuration from environment variables and defaults file."""
    defaults = _load_defaults_config()
    return {
        "required_partitions": _get_required_partitions(defaults),
        "max_shard_size_gb": _get_max_shard_size_gb(defaults),
        "index_schema_version": _get_index_schema_version(defaults),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate vector partition configuration against schema constraints and sharding rules."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/vector_partitions.json"),
        help="Path to partition configuration JSON file (default: config/vector_partitions.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform validation without committing changes, with verbose step-by-step output",
    )
    args = parser.parse_args()

    if not os.environ.get("SLM_ENV"):
        print("ERROR: SLM_ENV environment variable not set", file=sys.stderr)
        return EXIT_ENV_ERROR

    try:
        validate_partition_config(args.config, args.dry_run)
    except RuntimeError as e:
        return int(e.args[0]) if e.args else EXIT_VALIDATION_ERROR
    except OSError:
        return EXIT_CONFIG_ERROR

    return EXIT_SUCCESS

if __name__ == "__main__":
    sys.exit(main())
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


class ValidationError(RuntimeError):
    """Raised when partition configuration validation fails."""
    def __init__(self, message: str, partition: Optional[str] = None, value: Any = None, limit: Any = None):
        self.partition = partition
        self.value = value
        self.limit = limit
        super().__init__(message)


class ConfigError(RuntimeError):
    """Raised when configuration file is missing or invalid."""
    def __init__(self, message: str, path: Optional[Path] = None):
        self.path = path
        super().__init__(message)


class EnvError(RuntimeError):
    """Raised when required environment variable is not set."""
    def __init__(self, message: str, var_name: Optional[str] = None):
        self.var_name = var_name
        super().__init__(message)


class PartitionSettings(TypedDict):
    max_shard_gb: int
    indexing_enabled: bool


class PartitionConfig(TypedDict):
    version: str
    partitions: Dict[str, PartitionSettings]


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
        ValidationError: On validation failure with descriptive message including
            partition name and offending value.
        ConfigError: If config file not found at specified path.
        json.JSONDecodeError: If the config file contains invalid JSON (caught internally,
            raises ValidationError).
        OSError: If file cannot be read due to permissions (propagates to caller).
    """
    required_partitions = _get_required_partitions(defaults)
    max_shard_size_gb = _get_max_shard_size_gb(defaults)
    index_schema_version = _get_index_schema_version(defaults)

    if dry_run:
        print("DRY-RUN: Starting validation checks...")

    # Use a mutable holder so step2 can update the parsed data for subsequent steps
    data_holder = [data]

    def step1() -> None:
        _check_file_exists(config_path)

    def step2() -> None:
        if data_holder[0] is None:
            data_holder[0] = _check_json_parsing(config_path)
        else:
            if not isinstance(data_holder[0], dict):
                raise ValidationError("Configuration data must be a dictionary")

    def step3() -> None:
        _check_required_partitions(config_path, required_partitions, data_holder[0])

    def step4() -> None:
        _check_schema_version(config_path, index_schema_version, data_holder[0])

    def step5() -> None:
        _check_shard_sizes(config_path, max_shard_size_gb, data_holder[0])

    def step6() -> None:
        _check_indexing_enabled(config_path, data_holder[0])

    validation_steps = [
        ("File existence check", step1),
        ("JSON parsing", step2),
        ("Required partitions", step3),
        ("Schema version", step4),
        ("Shard size constraints", step5),
        ("Indexing enabled", step6),
    ]

    for i, (name, step_func) in enumerate(validation_steps, 1):
        if dry_run:
            print(f"  [{i}/{len(validation_steps)}] {name}")
        step_func()
        if dry_run:
            print(f"  [{i}/{len(validation_steps)}] PASSED")

    if dry_run:
        print("DRY-RUN: Validation completed successfully.")

def _check_file_exists(config_path: Path) -> None:
    if not config_path.is_file():
        raise ConfigError(f"Configuration file not found: {config_path}", path=config_path)


def _check_json_parsing(config_path: Path, data: Optional[Dict[str, Any]] = None) -> PartitionConfig:
    if data is not None:
        return data
    try:
        with config_path.open("r") as f:
            parsed = json.load(f)
        return parsed
    except json.JSONDecodeError as e:
        raise ValidationError(f"Invalid JSON in configuration file: {e}") from e

def _check_required_partitions(
    config_path: Path,
    required_partitions: List[str],
    data: PartitionConfig,
) -> None:
    partitions = data.get("partitions", {})
    missing = [p for p in required_partitions if p not in partitions]
    if missing:
        raise ValidationError(
            f"Missing required partitions: {', '.join(missing)}",
            partition=", ".join(missing),
            value="missing",
            limit=f"required: {', '.join(required_partitions)}"
        )


def _check_schema_version(
    config_path: Path,
    expected_version: str,
    data: PartitionConfig,
) -> None:
    actual_version = data.get("version")
    if actual_version != expected_version:
        raise ValidationError(
            f"Schema version mismatch: expected '{expected_version}', got '{actual_version}'",
            partition="version",
            value=actual_version,
            limit=expected_version
        )


def _check_shard_sizes(
    config_path: Path,
    max_shard_size_gb: int,
    data: PartitionConfig,
) -> None:
    partitions = data.get("partitions", {})
    for partition_name, settings in partitions.items():
        max_shard = settings.get("max_shard_gb")
        if max_shard is not None and max_shard > max_shard_size_gb:
            raise ValidationError(
                f"Partition '{partition_name}' exceeds maximum shard size: {max_shard} GB > {max_shard_size_gb} GB",
                partition=partition_name,
                value=max_shard,
                limit=max_shard_size_gb
            )


def _check_indexing_enabled(
    config_path: Path,
    data: PartitionConfig,
) -> None:
    partitions = data.get("partitions", {})
    for partition_name, settings in partitions.items():
        indexing_enabled = settings.get("indexing_enabled")
        if indexing_enabled is not True:
            raise ValidationError(
                f"Partition '{partition_name}' has indexing disabled or not set",
                partition=partition_name,
                value=indexing_enabled,
                limit=True
            )


def main() -> int:
    EXIT_SUCCESS = 0
    EXIT_VALIDATION_ERROR = 1
    EXIT_CONFIG_ERROR = 2
    EXIT_ENV_ERROR = 3

    parser = argparse.ArgumentParser(
        description="Validate vector database partition configuration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables:
  SLM_ENV                    Required. Must be set for the tool to run.
  SLM_DEFAULTS_CONFIG        Path to defaults JSON file
                             (default: config/vector_index_defaults.json)
  SLM_REQUIRED_PARTITIONS    Comma-separated list of required partition names
                             (default: alerts,threat_intel,audit_logs)
  SLM_MAX_SHARD_SIZE_GB      Maximum allowed shard size in GB (default: 16)
  SLM_INDEX_SCHEMA_VERSION   Expected schema version string (default: 11.6.0)

Exit Codes:
  0  Validation passed successfully
  1  Validation failed
  2  Config file not found
  3  SLM_ENV not set
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
        help="Perform validation without committing changes, with verbose output"
    )
    args = parser.parse_args()

    if not os.environ.get("SLM_ENV"):
        print("Error: SLM_ENV environment variable is required", file=sys.stderr)
        return EXIT_ENV_ERROR

    try:
        validate_partition_config(args.config, dry_run=args.dry_run)
        return EXIT_SUCCESS
    except ConfigError as e:
        print(f"Config Error: {e}", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    except ValidationError as e:
        print(f"Validation Error: {e}", file=sys.stderr)
        return EXIT_VALIDATION_ERROR
    except json.JSONDecodeError as e:
        print(f"JSON Parse Error: {e}", file=sys.stderr)
        return EXIT_VALIDATION_ERROR
    except OSError as e:
        print(f"File Error: {e}", file=sys.stderr)
        return EXIT_CONFIG_ERROR

if __name__ == "__main__":
    sys.exit(main())
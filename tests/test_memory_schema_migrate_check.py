import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import json
import os
from unittest.mock import patch, mock_open
from tools.memory_schema_migrate_check import validate_schema, main

def test_validate_schema_success():
    data = {
        "version": "11.6.0",
        "vector_dim": 768,
        "partition_strategy": "round-robin",
        "retention_days": 30
    }
    success, msg = validate_schema(data)
    assert success is True
    assert msg == "Schema valid"

def test_validate_schema_missing_keys():
    data = {"version": "11.6.0"}
    success, msg = validate_schema(data)
    assert success is False
    assert "Missing required schema keys" in msg

def test_validate_schema_version_mismatch():
    data = {
        "version": "1.0.0",
        "vector_dim": 768,
        "partition_strategy": "none",
        "retention_days": 1
    }
    success, msg = validate_schema(data)
    assert success is False
    assert "Version mismatch" in msg

def test_validate_schema_invalid_dim():
    data = {
        "version": "11.6.0",
        "vector_dim": 128,
        "partition_strategy": "none",
        "retention_days": 1
    }
    success, msg = validate_schema(data)
    assert success is False
    assert "Invalid vector dimension" in msg

@patch("os.path.exists")
def test_main_missing_config(mock_exists):
    mock_exists.return_value = False
    assert main() == 2

@patch("os.path.exists")
@patch("builtins.open", new_callable=mock_open, read_data="invalid json")
def test_main_invalid_json(mock_file, mock_exists):
    mock_exists.return_value = True
    assert main() == 1

@patch("os.path.exists")
@patch("builtins.open", new_callable=mock_open, read_data='{"version": "11.6.0", "vector_dim": 768, "partition_strategy": "x", "retention_days": 1}')
@patch("argparse.ArgumentParser.parse_args")
def test_main_dry_run_success(mock_args, mock_file, mock_exists):
    mock_exists.return_value = True
    mock_args.return_value = type('obj', (object,), {'dry_run': True})
    assert main() == 0

@patch("os.path.exists")
@patch("builtins.open", new_callable=mock_open, read_data='{"version": "11.6.0", "vector_dim": 768, "partition_strategy": "x", "retention_days": 1}')
@patch("argparse.ArgumentParser.parse_args")
def test_main_missing_ledger(mock_args, mock_file, mock_exists):
    # First call for config, second for ledger
    mock_exists.side_effect = [True, False]
    mock_args.return_value = type('obj', (object,), {'dry_run': False})
    assert main() == 1

@patch("os.path.exists")
@patch("builtins.open", new_callable=mock_open, read_data='{"version": "11.6.0", "vector_dim": 768, "partition_strategy": "x", "retention_days": 1}')
@patch("argparse.ArgumentParser.parse_args")
def test_main_full_success(mock_args, mock_file, mock_exists):
    mock_exists.return_value = True
    mock_args.return_value = type('obj', (object,), {'dry_run': False})
    assert main() == 0
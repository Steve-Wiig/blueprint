"""Tests for tools/memory_schema_migrate_check.py"""
import sys
import json
from pathlib import Path
from unittest.mock import patch
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.memory_schema_migrate_check import main


def test_main_dry_run_success(tmp_path):
    """Dry run should succeed when config file exists."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({
        "version": "11.6.0",
        "vector_dim": 768,
        "partition_strategy": "x",
        "retention_days": 90
    }))
    
    with patch("tools.memory_schema_migrate_check.CONFIG_PATH", config_file):
        with patch("tools.memory_schema_migrate_check.LEDGER_PATH", tmp_path / "ledger.json"):
            with patch("sys.argv", ["memory_schema_migrate_check.py", "--dry-run"]):
                result = main()
                assert result == 0


def test_main_full_success(tmp_path):
    """Full run should succeed when config and ledger exist."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({
        "version": "11.6.0",
        "vector_dim": 768,
        "partition_strategy": "x",
        "retention_days": 90
    }))
    
    ledger_file = tmp_path / "ledger.json"
    ledger_file.write_text(json.dumps({"migrations": []}))
    
    with patch("tools.memory_schema_migrate_check.CONFIG_PATH", config_file):
        with patch("tools.memory_schema_migrate_check.LEDGER_PATH", ledger_file):
            with patch("sys.argv", ["memory_schema_migrate_check.py"]):
                result = main()
                assert result == 0


def test_main_missing_config(tmp_path):
    """Should fail when config file doesn't exist."""
    with patch("tools.memory_schema_migrate_check.CONFIG_PATH", tmp_path / "nonexistent.json"):
        with patch("sys.argv", ["memory_schema_migrate_check.py"]):
            with pytest.raises(RuntimeError, match="exit\\(2\\)"):
                main()


def test_main_invalid_json(tmp_path):
    """Should fail when config file contains invalid JSON."""
    config_file = tmp_path / "config.json"
    config_file.write_text("not valid json {")
    
    with patch("tools.memory_schema_migrate_check.CONFIG_PATH", config_file):
        with patch("sys.argv", ["memory_schema_migrate_check.py"]):
            with pytest.raises(RuntimeError, match="exit\\(1\\)"):
                main()

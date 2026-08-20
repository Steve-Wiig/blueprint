import sys
import json
import os
import pytest
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

@pytest.fixture
def config_file(tmp_path):
    d = tmp_path / "config"
    d.mkdir()
    f = d / "vector_partitions.json"
    return f

def write_config(path, data):
    with open(path, 'w') as f:
        json.dump(data, f)

def test_validate_partition_config_success(config_file):
    valid_data = {
        "version": "11.6.0",
        "partitions": {
            "alerts": {"max_shard_gb": 10, "indexing_enabled": True},
            "threat_intel": {"max_shard_gb": 5, "indexing_enabled": True},
            "audit_logs": {"max_shard_gb": 1, "indexing_enabled": True}
        }
    }
    write_config(config_file, valid_data)
    
    # Test via subprocess as per CLI tool requirements
    tool_path = Path(__file__).parent.parent / "tools" / "vector_partition_index_check.py"
    env = os.environ.copy()
    env["SLM_ENV"] = "test"
    
    result = subprocess.run(
        [sys.executable, str(tool_path), "--config", str(config_file), "--dry-run"],
        env=env, capture_output=True, text=True
    )
    assert result.returncode == 0

def test_validate_partition_config_missing_file():
    tool_path = Path(__file__).parent.parent / "tools" / "vector_partition_index_check.py"
    env = os.environ.copy()
    env["SLM_ENV"] = "test"
    
    result = subprocess.run(
        [sys.executable, str(tool_path), "--config", "non_existent.json"],
        env=env, capture_output=True, text=True
    )
    assert result.returncode == 2

def test_validate_partition_config_invalid_json(config_file):
    with open(config_file, 'w') as f:
        f.write("{ invalid json")
    
    tool_path = Path(__file__).parent.parent / "tools" / "vector_partition_index_check.py"
    env = os.environ.copy()
    env["SLM_ENV"] = "test"
    
    result = subprocess.run(
        [sys.executable, str(tool_path), "--config", str(config_file)],
        env=env, capture_output=True, text=True
    )
    assert result.returncode == 1

def test_validate_partition_config_missing_env():
    tool_path = Path(__file__).parent.parent / "tools" / "vector_partition_index_check.py"
    env = os.environ.copy()
    if "SLM_ENV" in env:
        del env["SLM_ENV"]
        
    result = subprocess.run(
        [sys.executable, str(tool_path)],
        env=env, capture_output=True, text=True
    )
    assert result.returncode == 3

def test_validate_partition_config_schema_mismatch(config_file):
    invalid_data = {
        "version": "0.0.1",
        "partitions": {
            "alerts": {"max_shard_gb": 1, "indexing_enabled": True},
            "threat_intel": {"max_shard_gb": 1, "indexing_enabled": True},
            "audit_logs": {"max_shard_gb": 1, "indexing_enabled": True}
        }
    }
    write_config(config_file, invalid_data)
    
    tool_path = Path(__file__).parent.parent / "tools" / "vector_partition_index_check.py"
    env = os.environ.copy()
    env["SLM_ENV"] = "test"
    
    result = subprocess.run(
        [sys.executable, str(tool_path), "--config", str(config_file)],
        env=env, capture_output=True, text=True
    )
    assert result.returncode == 1

def test_validate_partition_config_shard_too_large(config_file):
    invalid_data = {
        "version": "11.6.0",
        "partitions": {
            "alerts": {"max_shard_gb": 99, "indexing_enabled": True},
            "threat_intel": {"max_shard_gb": 5, "indexing_enabled": True},
            "audit_logs": {"max_shard_gb": 1, "indexing_enabled": True}
        }
    }
    write_config(config_file, invalid_data)
    
    tool_path = Path(__file__).parent.parent / "tools" / "vector_partition_index_check.py"
    env = os.environ.copy()
    env["SLM_ENV"] = "test"
    
    result = subprocess.run(
        [sys.executable, str(tool_path), "--config", str(config_file)],
        env=env, capture_output=True, text=True
    )
    assert result.returncode == 1
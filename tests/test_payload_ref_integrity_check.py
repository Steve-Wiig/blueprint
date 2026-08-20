import sys
import json
import os
import pytest
import subprocess
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.payload_ref_integrity_check import verify_payload

@pytest.fixture
def valid_ledger(tmp_path):
    ledger = {
        "ledger_id": "test-123",
        "timestamp": "2023-10-27T10:00:00Z",
        "payload_hash": {"data": "sample"},
        "origin_node": "soc-internal://node-1",
        "schema_version": "1.0",
        "security_level": "high",
        "integrity_checksum": "a" * 64,
        "signature_blob": "sig-data"
    }
    path = tmp_path / "ledger.json"
    with open(path, "w") as f:
        json.dump(ledger, f)
    return path

def test_verify_payload_success(valid_ledger):
    assert verify_payload(str(valid_ledger)) == 0

def test_verify_payload_missing_file():
    assert verify_payload("non_existent.json") == 1

def test_verify_payload_invalid_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{ invalid json")
    assert verify_payload(str(path)) == 2

def test_verify_payload_missing_keys(tmp_path):
    path = tmp_path / "incomplete.json"
    with open(path, "w") as f:
        json.dump({"ledger_id": "1"}, f)
    assert verify_payload(str(path)) == 1

def test_verify_payload_invalid_scheme(tmp_path):
    path = tmp_path / "bad_scheme.json"
    data = {
        "ledger_id": "1", "timestamp": "2", "payload_hash": {}, "origin_node": "ftp://bad",
        "schema_version": "1", "security_level": "1", "integrity_checksum": "a"*64, "signature_blob": "1"
    }
    with open(path, "w") as f:
        json.dump(data, f)
    assert verify_payload(str(path)) == 1

def test_cli_execution(valid_ledger):
    tool_path = Path(__file__).parent.parent / "tools" / "payload_ref_integrity_check.py"
    env = os.environ.copy()
    env["LEDGER_PATH"] = str(valid_ledger)
    
    result = subprocess.run(
        [sys.executable, str(tool_path)],
        env=env,
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "PASS" in result.stdout

def test_cli_failure_exit_code():
    tool_path = Path(__file__).parent.parent / "tools" / "payload_ref_integrity_check.py"
    env = os.environ.copy()
    env["LEDGER_PATH"] = "non_existent_file.json"
    
    result = subprocess.run(
        [sys.executable, str(tool_path)],
        env=env,
        capture_output=True,
        text=True
    )
    assert result.returncode == 1
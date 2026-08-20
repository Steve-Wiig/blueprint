import sys
import json
import pytest
import subprocess
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

@pytest.fixture
def temp_schema(tmp_path):
    def _create_schema(data):
        p = tmp_path / "schema.json"
        p.write_text(json.dumps(data))
        return str(p)
    return _create_schema

def test_validate_schema_success(temp_schema):
    from tools.sanitization_field_policy_check import validate_schema
    path = temp_schema({"user": "name", "age": 30})
    assert validate_schema(path) == 0

def test_validate_schema_forbidden_found(temp_schema):
    from tools.sanitization_field_policy_check import validate_schema
    path = temp_schema({"user": "name", "raw_password": "123"})
    assert validate_schema(path) == 1

def test_validate_schema_nested_forbidden(temp_schema):
    from tools.sanitization_field_policy_check import validate_schema
    path = temp_schema({"data": {"items": [{"private_key": "abc"}]}})
    assert validate_schema(path) == 1

def test_validate_schema_invalid_file():
    from tools.sanitization_field_policy_check import validate_schema
    assert validate_schema("non_existent.json") == 2

def test_validate_schema_invalid_json(temp_schema):
    from tools.sanitization_field_policy_check import validate_schema
    p = Path(temp_schema({}))
    p.write_text("{ invalid json")
    assert validate_schema(str(p)) == 1

def test_cli_missing_env():
    tool_path = Path(__file__).parent.parent / "tools" / "sanitization_field_policy_check.py"
    result = subprocess.run(
        [sys.executable, str(tool_path), "--schema", "dummy.json"],
        capture_output=True, text=True
    )
    assert result.returncode == 3

def test_cli_dry_run_success(temp_schema):
    tool_path = Path(__file__).parent.parent / "tools" / "sanitization_field_policy_check.py"
    path = temp_schema({"safe": "data"})
    with patch.dict("os.environ", {"CI_PIPELINE_ID": "123"}):
        result = subprocess.run(
            [sys.executable, str(tool_path), "--schema", path, "--dry-run"],
            capture_output=True, text=True
        )
        assert result.returncode == 0

def test_cli_failure_exit_code(temp_schema):
    tool_path = Path(__file__).parent.parent / "tools" / "sanitization_field_policy_check.py"
    path = temp_schema({"raw_password": "bad"})
    with patch.dict("os.environ", {"CI_PIPELINE_ID": "123"}):
        result = subprocess.run(
            [sys.executable, str(tool_path), "--schema", path],
            capture_output=True, text=True
        )
        assert result.returncode == 1
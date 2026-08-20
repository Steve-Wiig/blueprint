import sys
import os
import pytest
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.dynamic_vram_budget_check import get_gpu_info, parse_mem_value, main

def test_parse_mem_value():
    assert parse_mem_value("16384 MiB") == 16384
    assert parse_mem_value("0 MiB") == 0
    assert parse_mem_value("invalid") == 0

@patch("tools.dynamic_vram_budget_check.subprocess.run")
def test_get_gpu_info_success(mock_run):
    mock_run.return_value.stdout = "<nvidia_smi_log><gpu></gpu></nvidia_smi_log>"
    result = get_gpu_info()
    assert result is not None
    assert result.tag == "nvidia_smi_log"

@patch("tools.dynamic_vram_budget_check.subprocess.run")
def test_get_gpu_info_failure(mock_run):
    mock_run.side_effect = subprocess.CalledProcessError(1, 'cmd')
    assert get_gpu_info() is None

@patch("tools.dynamic_vram_budget_check.get_gpu_info")
def test_main_no_gpu(mock_get_gpu):
    mock_get_gpu.return_value = None
    assert main() == 1

@patch("tools.dynamic_vram_budget_check.get_gpu_info")
def test_main_config_error_invalid_env(mock_get_gpu):
    with patch.dict(os.environ, {"VRAM_BUDGET_MB": "abc"}):
        # Mocking a valid structure to pass initial parsing but fail env validation
        mock_gpu = MagicMock()
        mock_get_gpu.return_value = mock_gpu
        assert main() == 2

@patch("tools.dynamic_vram_budget_check.get_gpu_info")
def test_main_pass_within_budget(mock_get_gpu):
    # Construct XML structure that main() expects
    root = MagicMock()
    gpu = MagicMock()
    fb = MagicMock()
    total = MagicMock()
    used = MagicMock()
    
    total.text = "1000 MiB"
    used.text = "500 MiB"
    
    root.find.return_value = gpu
    gpu.find.return_value = fb
    fb.find.side_effect = [total, used]
    
    mock_get_gpu.return_value = root
    
    with patch.dict(os.environ, {"VRAM_BUDGET_MB": "900"}):
        assert main() == 0

@patch("tools.dynamic_vram_budget_check.get_gpu_info")
def test_main_fail_exceeds_budget(mock_get_gpu):
    root = MagicMock()
    gpu = MagicMock()
    fb = MagicMock()
    total = MagicMock()
    used = MagicMock()
    
    total.text = "1000 MiB"
    used.text = "950 MiB"
    
    root.find.return_value = gpu
    gpu.find.return_value = fb
    fb.find.side_effect = [total, used]
    
    mock_get_gpu.return_value = root
    
    with patch.dict(os.environ, {"VRAM_BUDGET_MB": "900"}):
        assert main() == 1

def test_cli_dry_run():
    tool_path = Path(__file__).parent.parent / "tools" / "dynamic_vram_budget_check.py"
    result = subprocess.run([sys.executable, str(tool_path), "--dry-run"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "PASS" in result.stdout
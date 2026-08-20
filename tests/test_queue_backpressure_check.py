import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import patch, MagicMock
from tools.queue_backpressure_check import check_backpressure

@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("QUEUE_SERVICE_TOKEN", "fake-token")

def test_check_backpressure_missing_url():
    assert check_backpressure(None) == 2

def test_check_backpressure_dry_run():
    assert check_backpressure("http://test.lab", dry_run=True) == 0

def test_check_backpressure_missing_token(monkeypatch):
    monkeypatch.delenv("QUEUE_SERVICE_TOKEN", raising=False)
    assert check_backpressure("http://test.lab") == 3

@patch("requests.get")
def test_check_backpressure_api_failure(mock_get, mock_env):
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_get.return_value = mock_response
    
    assert check_backpressure("http://test.lab") == 1

@patch("requests.get")
def test_check_backpressure_fail_threshold(mock_get, mock_env):
    mock_response = MagicMock()
    mock_response.status_code = 200
    # 900 is > 850 (1000 * 0.85), backpressure_active is False
    mock_response.json.return_value = {"depth": 900, "backpressure_active": False}
    mock_get.return_value = mock_response
    
    assert check_backpressure("http://test.lab") == 1

@patch("requests.get")
def test_check_backpressure_pass_high_load(mock_get, mock_env):
    mock_response = MagicMock()
    mock_response.status_code = 200
    # 900 is > 850, backpressure_active is True
    mock_response.json.return_value = {"depth": 900, "backpressure_active": True}
    mock_get.return_value = mock_response
    
    assert check_backpressure("http://test.lab") == 0

@patch("requests.get")
def test_check_backpressure_pass_low_load(mock_get, mock_env):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"depth": 100, "backpressure_active": False}
    mock_get.return_value = mock_response
    
    assert check_backpressure("http://test.lab") == 0

@patch("requests.get")
def test_check_backpressure_request_exception(mock_get, mock_env):
    import requests
    mock_get.side_effect = requests.RequestException("Connection refused")
    
    assert check_backpressure("http://test.lab") == 1
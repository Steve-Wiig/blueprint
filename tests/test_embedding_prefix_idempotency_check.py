import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from tools.embedding_prefix_idempotency_check import check_idempotency, main

def test_check_idempotency_unprefixed():
    prefix = "test: "
    text = "hello"
    assert check_idempotency(text, prefix) is True

def test_check_idempotency_already_prefixed():
    prefix = "test: "
    text = "test: hello"
    assert check_idempotency(text, prefix) is True

def test_check_idempotency_double_prefixed():
    prefix = "test: "
    text = "test: test: hello"
    assert check_idempotency(text, prefix) is False

def test_check_idempotency_empty_string():
    prefix = "test: "
    assert check_idempotency("", prefix) is True

def test_check_idempotency_prefix_only():
    prefix = "test: "
    assert check_idempotency("test: ", prefix) is True

def test_main_success(capsys):
    # The main function is designed to pass with its hardcoded test cases
    # because the double_prefixed case in main() is specifically handled
    # to return 1 if it is valid, but the logic in check_idempotency
    # correctly identifies it as invalid (returning False).
    result = main()
    captured = capsys.readouterr()
    assert result == 0
    assert "PASS" in captured.out

def test_main_logic_flow():
    # Verify that the logic inside main correctly identifies the failure case
    # by mocking the behavior if necessary, but here we test the integration.
    # The current main() implementation returns 0 on success.
    assert main() == 0
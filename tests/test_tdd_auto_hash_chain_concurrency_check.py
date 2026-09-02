import pytest
from unittest.mock import patch, MagicMock
from hash_chain_concurrency_check import check_hash_chain_concurrency


def test_check_hash_chain_concurrency_pre_allocates_results_list():
    input_data = [b"block1", b"block2", b"block3", b"block4"]
    expected_size = len(input_data)

    with patch("builtins.list", wraps=list) as mock_list:
        result = check_hash_chain_concurrency(input_data)

        assert len(result) == expected_size
        assert all(isinstance(r, bool) for r in result)

        list_constructor_calls = [call for call in mock_list.call_args_list if call.args == ()]
        assert len(list_constructor_calls) == 1, (
            f"Expected list() to be called once (pre-allocated), "
            f"but was called {len(list_constructor_calls)} times"
        )
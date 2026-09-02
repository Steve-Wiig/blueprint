import pytest
from embeddings import get_embeddings


def test_misleading_exit_error_message():
    with pytest.raises(RuntimeError) as exc_info:
        get_embeddings(["test input"])
    assert "Library code called exit(1)" in str(exc_info.value)
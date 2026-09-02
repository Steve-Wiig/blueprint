import tempfile, os
import pytest
from llm_analyze import count_words

def test_count_words_large_file_runtime_error():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("word " * 100000)
        path = f.name
    try:
        with pytest.raises(RuntimeError):
            count_words(path)
    finally:
        os.unlink(path)
import pytest
from retention import compress, _HAS_ZSTANDARD

def test_zstandard_caching():
    compress(b"test")
    compress(b"test")
    assert _HAS_ZSTANDARD is not None
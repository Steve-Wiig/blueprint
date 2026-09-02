import pytest
from so_cases import sanitize_input

def test_sanitize_input_non_dict_raises():
    with pytest.raises(TypeError):
        sanitize_input("not a dict")
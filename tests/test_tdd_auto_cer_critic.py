import pytest
from cer_critic import sanitize_input
def test_sanitization_fails_on_secrets():
    with pytest.raises(RuntimeError):
        sanitize_input("high_entropy_token_1234567890")
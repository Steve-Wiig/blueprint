import hash_chain_verify

def test_hash_chain_verify_raises_runtime_error_instead_of_system_exit():
    import pytest
    with pytest.raises(RuntimeError):
        hash_chain_verify.main()
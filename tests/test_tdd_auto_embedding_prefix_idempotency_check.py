import pytest
import embedding_prefix_idempotency_check as ep


def test_module_separates_library_from_cli():
    assert hasattr(ep, "main"), "Module should have a main() function for CLI entry point"
    assert hasattr(ep, "check_idempotency"), "Module should expose library function check_idempotency"
    assert hasattr(ep, "compute_prefix"), "Module should expose library function compute_prefix"
    assert ep.__doc__ and "CI verification tool" not in ep.__doc__, "Module docstring should not mention 'CI verification tool'"
import pytest
import defeat_ledger


def test_module_has_docstring():
    """Test that defeat_ledger module has a module-level docstring."""
    assert defeat_ledger.__doc__ is not None, "Module lacks module-level docstring"
    assert defeat_ledger.__doc__.strip() != "", "Module docstring is empty"
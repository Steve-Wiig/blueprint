import pytest
from unittest.mock import Mock, patch
import sys
import types

# Create a minimal module to test the redact function behavior
# Since we can't read the source, we'll test the expected behavior

def test_redact_reuses_audit_repl_closure():
    """Test that redact() reuses the _audit_repl closure instead of creating new ones."""
    # Import the actual module
    import sanitization_redaction_check as src
    
    # Create a mock audit logger
    audit_logger = Mock()
    
    # Track the replacement functions used
    repl_functions = []
    
    # Patch re.sub to capture the replacement function used
    original_sub = src.re.sub if hasattr(src, 're') else None
    
    if original_sub is None:
        # Try to find re module in the src
        import re
        original_sub = re.sub
    
    def capture_sub(pattern, repl, string, *args, **kwargs):
        if callable(repl):
            repl_functions.append(repl)
        return original_sub(pattern, repl, string, *args, **kwargs)
    
    with patch('sanitization_redaction_check.re.sub', side_effect=capture_sub):
        # Call redact multiple times with the same audit_logger
        src.redact("test secret 123", audit_logger=audit_logger)
        src.redact("another secret 456", audit_logger=audit_logger)
        src.redact("third secret 789", audit_logger=audit_logger)
    
    # Verify that the same replacement function was reused
    # This will FAIL in the current broken state where new closures are created each call
    assert len(repl_functions) >= 3, "Expected at least 3 calls to re.sub with callable repl"
    
    # All replacement functions should be the SAME object (same closure)
    first_repl = repl_functions[0]
    for i, repl in enumerate(repl_functions[1:], 1):
        assert repl is first_repl, f"Call {i+1} created a new closure function instead of reusing the first one"
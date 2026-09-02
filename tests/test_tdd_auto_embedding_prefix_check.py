import pytest
import sys
import logging
from unittest.mock import patch, MagicMock


def test_module_level_logger_creation_side_effect():
    """Test that module-level logger creation executes on import."""
    # Remove module if already imported to test fresh import
    module_name = "embedding_prefix_check"
    if module_name in sys.modules:
        del sys.modules[module_name]
    
    # Mock getLogger to track calls
    with patch("logging.getLogger") as mock_get_logger:
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        
        # Import the module - this should trigger module-level logger creation
        import embedding_prefix_check
        
        # Verify getLogger was called at module level (on import)
        mock_get_logger.assert_called_once_with(module_name)
        
        # The bug: logger creation happens on import (module-level side effect)
        # This test fails because the current code creates logger at module level
        assert mock_get_logger.call_count == 1
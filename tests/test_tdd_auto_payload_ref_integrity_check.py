import pytest
from unittest.mock import patch, mock_open, MagicMock
import os

from payload_ref_integrity_check import check_payload_integrity


def test_check_payload_integrity_no_redundant_exists_check():
    """Test that check_payload_integrity doesn't call os.path.exists before open."""
    test_path = "/fake/path/payload.bin"
    test_content = b"test payload content"
    
    with patch("builtins.open", mock_open(read_data=test_content)) as mock_file:
        with patch("os.path.exists", return_value=True) as mock_exists:
            result = check_payload_integrity(test_path)
            
            mock_exists.assert_not_called()
            mock_file.assert_called_once_with(test_path, "rb")
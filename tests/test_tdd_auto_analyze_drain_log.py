import pytest
import tempfile
import os
from analyze_drain_log import analyze_drain_log


def test_analyze_drain_log_streaming_not_loading_entire_file():
    """Test that analyze_drain_log processes large files in streaming fashion, not loading entirely into memory."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
        for i in range(100000):
            f.write(f"2024-01-15 10:00:{i%60:02d} INFO Drain cycle {i} completed\n")
        large_log_path = f.name
    
    try:
        result = analyze_drain_log(large_log_path)
        assert result['total_cycles'] == 100000
        assert 'memory_peak_mb' in result
        assert result['memory_peak_mb'] < 50
    finally:
        os.unlink(large_log_path)
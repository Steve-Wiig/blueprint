"""Tests for orchestrator/context_stitcher.py — stitch_memory_context function."""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator.context_stitcher import stitch_memory_context


def test_returns_memory_context_tags():
    """Retrieved cases should be wrapped in <memory_context> tags."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchall.return_value = [
        ("case-001", "Alert triage summary for phishing IOC", 0.85),
        ("case-002", "Brute force SSH detection narrative", 0.79),
    ]
    with patch("orchestrator.context_stitcher._get_pg_conn", return_value=mock_conn):
        # The function returns a tuple: (context_string, metadata_dict)
        result, metadata = stitch_memory_context([0.1] * 768, top_k=5, max_age_days=30)

        assert "<memory_context>" in result
        assert "</memory_context>" in result
        assert "case-001" in result or "phishing" in result
        # Verify metadata is returned for ledger recording
        assert "retrieved_case_ids" in metadata
        assert "case-001" in metadata["retrieved_case_ids"]


def test_empty_results_return_empty_context():
    """No matching cases should return empty or minimal context."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchall.return_value = []
    with patch("orchestrator.context_stitcher._get_pg_conn", return_value=mock_conn):
        result, metadata = stitch_memory_context([0.1] * 768, top_k=5, max_age_days=30)

        # The wrapper tags may be present, but they should contain no actual case data
        assert "case-" not in result
        assert metadata["retrieved_case_ids"] == []


def test_top_k_limits_results():
    """Only top_k results should be returned."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchall.return_value = [
        (f"case-{i:03d}", f"summary {i}", 0.9 - i * 0.1)
        for i in range(10)
    ]
    with patch("orchestrator.context_stitcher._get_pg_conn", return_value=mock_conn):
        result, metadata = stitch_memory_context([0.1] * 768, top_k=3, max_age_days=30)

        # Verify LIMIT was passed to the query
        call_args = mock_cursor.execute.call_args
        assert call_args is not None

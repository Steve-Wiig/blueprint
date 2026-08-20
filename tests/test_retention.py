import pytest
import os
import datetime
from unittest.mock import patch, MagicMock
from pathlib import Path
from memory.retention import archive_partition, run_retention, check_cmr_mount, ARCHIVE_BASE, CMR_MOUNT

@pytest.fixture
def mock_db_conn():
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    return conn

def test_check_cmr_mount_failure(monkeypatch):
    monkeypatch.setattr(os.path, "ismount", lambda x: False)
    with pytest.raises(RuntimeError) as e:
        check_cmr_mount()
    # Auto-fixer replaced sys.exit(3) with RuntimeError — verify type only
    assert isinstance(e.value, RuntimeError)

def test_archive_partition_logic(tmp_path, monkeypatch, mock_db_conn):
    monkeypatch.setattr("memory.retention.ARCHIVE_BASE", str(tmp_path))
    
    mock_popen = MagicMock()
    mock_popen.returncode = 0
    monkeypatch.setattr("subprocess.Popen", lambda *args, **kwargs: mock_popen)
    
    partition_name = "iocs_2023_01_01"
    archive_partition(mock_db_conn, partition_name)
    
    expected_dir = tmp_path / "2023_01"
    assert expected_dir.exists()
    assert (expected_dir / f"{partition_name}.jsonl.zst").exists()
    mock_db_conn.cursor.return_value.__enter__.return_value.execute.assert_called_with(f"DROP TABLE {partition_name};")

def test_retention_window_calculation(monkeypatch, mock_db_conn):
    # Mock dependencies
    monkeypatch.setattr("memory.retention.check_cmr_mount", lambda: None)
    monkeypatch.setattr("psycopg2.connect", lambda x: mock_db_conn)
    
    # Mock partitions: one old (100 days), one new (10 days)
    old_date = (datetime.datetime.now() - datetime.timedelta(days=100)).strftime("%Y_%m_%d")
    new_date = (datetime.datetime.now() - datetime.timedelta(days=10)).strftime("%Y_%m_%d")
    
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchall.return_value = [(f"iocs_{old_date}",), (f"iocs_{new_date}",)]
    
    with patch("memory.retention.archive_partition") as mock_archive:
        run_retention("postgresql://test")
        
        # Should only archive the old one
        assert mock_archive.call_count == 1
        assert mock_archive.call_args[0][1] == f"iocs_{old_date}"

def test_retention_invalid_partition_name(monkeypatch, mock_db_conn):
    monkeypatch.setattr("memory.retention.check_cmr_mount", lambda: None)
    monkeypatch.setattr("psycopg2.connect", lambda x: mock_db_conn)
    
    mock_cursor = mock_db_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchall.return_value = [("invalid_name",)]
    
    with patch("memory.retention.archive_partition") as mock_archive:
        run_retention("postgresql://test")
        mock_archive.assert_not_called()
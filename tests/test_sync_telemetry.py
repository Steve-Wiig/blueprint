import os
import sys
import tempfile
import pytest
import fcntl
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))
import tools.sync_telemetry as syncer

@pytest.fixture
def sync_env(tmp_path):
    """Setup temporary directories and patch module constants."""
    outbox = tmp_path / "outbox"
    outbox.mkdir()
    nas = tmp_path / "nas"
    nas.mkdir()
    lock = tmp_path / "sync.lock"

    # Create a dummy file in outbox
    (outbox / "pending_123.jsonl").write_text('{"test": 1}\n')

    # Patch the module constants
    syncer.LOCAL_OUTBOX = outbox
    syncer.NAS_DEST = nas
    syncer.LOCK_FILE = lock

    yield syncer, outbox, nas, lock

def test_empty_outbox(sync_env, capsys):
    syncer_mod, outbox, nas, lock = sync_env
    for f in outbox.iterdir(): f.unlink()

    syncer_mod.sync()
    assert "Outbox empty" in capsys.readouterr().out

def test_nas_unmounted_st_dev_trap(sync_env, capsys):
    syncer_mod, outbox, nas, lock = sync_env

    mock_stat = MagicMock()
    mock_stat.st_dev = 2050 # Root st_dev for BOTH

    # We DO want to test the internal logic of verify_nas_mount here.
    # Because verify_nas_mount returns False immediately, NAS_DEST.mkdir() 
    # is never reached, so the global os.stat mock doesn't break pathlib.
    with patch('tools.sync_telemetry.os.stat', return_value=mock_stat), \
         patch('tools.sync_telemetry.subprocess.run') as mock_run:
        syncer_mod.sync()

    out = capsys.readouterr().out
    assert "CRITICAL: NAS mount lost" in out
    mock_run.assert_not_called()

def test_normal_sync(sync_env, capsys):
    syncer_mod, outbox, nas, lock = sync_env

    # FIX: Instead of globally mocking os.stat and breaking pathlib, 
    # we just mock the verify_nas_mount function to return True.
    with patch('tools.sync_telemetry.verify_nas_mount', return_value=True), \
         patch('tools.sync_telemetry.subprocess.run') as mock_run:

        mock_run.return_value = MagicMock(returncode=0)
        syncer_mod.sync()

    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert "rsync" in args
    assert "--remove-source-files" in args

def test_rsync_vanished_files(sync_env, capsys):
    syncer_mod, outbox, nas, lock = sync_env

    # FIX: Mock verify_nas_mount directly to bypass the st_dev check
    with patch('tools.sync_telemetry.verify_nas_mount', return_value=True), \
         patch('tools.sync_telemetry.subprocess.run') as mock_run:

        mock_run.return_value = MagicMock(returncode=24, stderr="vanished")
        syncer_mod.sync()

    assert "vanished source files" in capsys.readouterr().out

def test_concurrent_syncers(sync_env, capsys):
    syncer_mod, outbox, nas, lock = sync_env

    fd = os.open(str(lock), os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    try:
        # FIX: sync() now returns instead of sys.exit(0), so this won't raise SystemExit
        syncer_mod.sync()
        assert "Another syncer is already running" in capsys.readouterr().out
    finally:
        os.close(fd)

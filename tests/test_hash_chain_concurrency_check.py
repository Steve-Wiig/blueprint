import sys
import threading
import subprocess
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.hash_chain_concurrency_check import HashChainLedger, worker

def test_hash_chain_ledger_logic():
    ledger = HashChainLedger()
    idx1 = ledger.append_hash("hash1")
    idx2 = ledger.append_hash("hash2")
    
    assert idx1 == 1
    assert idx2 == 2
    assert len(ledger.chain) == 2
    assert ledger.chain == ["hash1", "hash2"]

def test_worker_concurrency_safety():
    ledger = HashChainLedger()
    results = []
    threads = []
    
    # Test that multiple workers can append without crashing
    for _ in range(5):
        t = threading.Thread(target=worker, args=(ledger, results))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    assert len(results) == 5
    assert None not in results
    assert len(set(results)) == 5

def test_main_dry_run():
    tool_path = Path(__file__).parent.parent / "tools" / "hash_chain_concurrency_check.py"
    result = subprocess.run([sys.executable, str(tool_path), "--dry-run"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "PASS" in result.stdout

def test_main_execution():
    tool_path = Path(__file__).parent.parent / "tools" / "hash_chain_concurrency_check.py"
    # Run the actual CLI tool logic
    result = subprocess.run([sys.executable, str(tool_path)], capture_output=True, text=True)
    assert result.returncode == 0
    assert "PASS" in result.stdout

def test_invalid_path_config(monkeypatch):
    # Force an invalid path to trigger config error (exit code 2)
    monkeypatch.setenv("HASH_CHAIN_LEDGER", "/root/forbidden/path.ledger")
    tool_path = Path(__file__).parent.parent / "tools" / "hash_chain_concurrency_check.py"
    result = subprocess.run([sys.executable, str(tool_path)], capture_output=True, text=True)
    assert result.returncode == 2
    assert "CONFIG ERROR" in result.stdout
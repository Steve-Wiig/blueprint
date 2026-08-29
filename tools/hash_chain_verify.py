#!/usr/bin/env python3
# CI Gate: Hash Chain Integrity Verification
import hashlib
import argparse
import json
import sys
import os
from typing import Any, Iterable

try:
    import ijson
    IJSON_AVAILABLE = True
except ImportError:
    IJSON_AVAILABLE = False

LARGE_FILE_THRESHOLD = 100 * 1024 * 1024  # 100 MB

def compute_row_hash(row: dict[str, Any]) -> str:
    """Recomputes hash for a single row excluding the hash field itself."""
    data = {k: v for k, v in row.items() if k != "hash"}
    serialized = json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    return hashlib.sha256(serialized.encode()).hexdigest()

def _verify_chain_iterable(entries: Iterable[dict[str, Any]]) -> bool:
    """Internal helper that verifies a chain given an iterable of entries."""
    expected_seq = 0
    expected_prev_hash = "0" * 64
    for entry in entries:
        if entry.get("chain_seq") != expected_seq:
            print(f"FAIL: Sequence mismatch. Expected {expected_seq}, got {entry.get('chain_seq')}")
            return False
        if entry.get("previous_hash") != expected_prev_hash:
            print(f"FAIL: Linkage break at seq {expected_seq}. Expected {expected_prev_hash}")
            return False
        actual_hash = entry.get("hash")
        computed_hash = compute_row_hash(entry)
        if actual_hash != computed_hash:
            print(f"FAIL: Hash mismatch at seq {expected_seq}.")
            return False
        expected_prev_hash = actual_hash
        expected_seq += 1
    return True
def verify_chain_streaming(file_path: str) -> bool:
    """
    Verifies hash chain using streaming JSON parser (ijson).
    Verifies:
    1. chain_seq ordering (0..N)
    2. previous_hash linkage
    3. row_hash recomputation
    """
    with open(file_path, 'rb') as f:
        parser = ijson.items(f, 'item')
        return _verify_chain_iterable(parser)

def verify_chain(chain_data: list[dict[str, Any]]) -> bool:
    """
    Verifies:
    1. chain_seq ordering (0..N)
    2. previous_hash linkage
    3. row_hash recomputation
    """
    return _verify_chain_iterable(chain_data)

def load_mock_chain() -> list[dict[str, Any]]:
    """Load mock chain from mock_chain.json in the same directory as this script."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mock_path = os.path.join(script_dir, "mock_chain.json")
    if not os.path.exists(mock_path):
        raise FileNotFoundError(f"mock_chain.json not found at {mock_path}")
    with open(mock_path, 'r') as f:
        return json.load(f)

def main(chain_file: str) -> int:
    """Verify hash chain from file. Returns 0 on success, 1 on verification failure, 2 on config error, 3 on file not found."""
    if not os.path.exists(chain_file):
        print("FAIL: Chain file not found")
        return 3
    file_size = os.path.getsize(chain_file)
    use_streaming = file_size > LARGE_FILE_THRESHOLD
    if use_streaming:
        if not IJSON_AVAILABLE:
            print(f"WARNING: Large file ({file_size / (1024*1024):.1f} MB) detected but ijson not installed. Loading into memory may cause OOM.")
            print("Install ijson for streaming support: pip install ijson")
        else:
            print(f"INFO: Large file ({file_size / (1024*1024):.1f} MB) detected. Using streaming parser.")
            try:
                if verify_chain_streaming(chain_file):
                    print("PASS: Hash chain integrity verified")
                    return 0
                else:
                    return 1
            except Exception as e:
                print(f"FAIL: Verification error: {e}")
                return 1
    try:
        with open(chain_file, 'r') as f:
            chain = json.load(f)
        if verify_chain(chain):
            print("PASS: Hash chain integrity verified")
            return 0
        else:
            return 1
    except json.JSONDecodeError:
        print("FAIL: Invalid JSON format")
        return 1
    except Exception as e:
        print(f"FAIL: Verification error: {e}")
        return 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hash Chain Verifier")
    parser.add_argument("--dry-run", action="store_true", help="Run with mock chain data from mock_chain.json")
    parser.add_argument('chain_file', nargs='?', default=None, help='Path to chain JSON file (required unless --dry-run)')
    args = parser.parse_args()
    if not args.dry_run and not args.chain_file:
        parser.error('chain_file required')
    if args.dry_run:
        try:
            chain_data = load_mock_chain()
        except FileNotFoundError as e:
            print(f"FAIL: {e}")
            raise SystemExit(1)
        except json.JSONDecodeError:
            print("FAIL: Invalid JSON in mock_chain.json")
            raise SystemExit(1)
        result = verify_chain(chain_data)
        if result:
            print("PASS: dry-run successful (mock chain verified)")
            raise SystemExit(0)
        print("FAIL: dry-run mock chain failed")
        raise SystemExit(1)
    raise SystemExit(main(args.chain_file))
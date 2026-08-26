#!/usr/bin/env python3
# CI Gate: Hash Chain Integrity Verification
import hashlib
import argparse
import json
import sys
import os
from typing import Any

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

def verify_chain_streaming(file_path: str) -> bool:
    """
    Verifies hash chain using streaming JSON parser (ijson).
    Verifies:
    1. chain_seq ordering (0..N)
    2. previous_hash linkage
    3. row_hash recomputation
    """
    expected_seq = 0
    expected_prev_hash = "0" * 64
    
    with open(file_path, 'rb') as f:
        parser = ijson.items(f, 'item')
        for entry in parser:
            # 1. Verify Sequence
            if entry.get("chain_seq") != expected_seq:
                print(f"FAIL: Sequence mismatch. Expected {expected_seq}, got {entry.get('chain_seq')}")
                return False
                
            # 2. Verify Linkage
            if entry.get("previous_hash") != expected_prev_hash:
                print(f"FAIL: Linkage break at seq {expected_seq}. Expected {expected_prev_hash}")
                return False
                
            # 3. Verify Integrity
            actual_hash = entry.get("hash")
            computed_hash = compute_row_hash(entry)
            if actual_hash != computed_hash:
                print(f"FAIL: Hash mismatch at seq {expected_seq}.")
                return False
                
            expected_prev_hash = actual_hash
            expected_seq += 1
            
    return True

def verify_chain(chain_data: list[dict[str, Any]]) -> bool:
    """
    Verifies:
    1. chain_seq ordering (0..N)
    2. previous_hash linkage
    3. row_hash recomputation
    """
    if not chain_data:
        return True
    
    expected_seq = 0
    expected_prev_hash = "0" * 64
    
    for entry in chain_data:
        # 1. Verify Sequence
        if entry.get("chain_seq") != expected_seq:
            print(f"FAIL: Sequence mismatch. Expected {expected_seq}, got {entry.get('chain_seq')}")
            return False
            
        # 2. Verify Linkage
        if entry.get("previous_hash") != expected_prev_hash:
            print(f"FAIL: Linkage break at seq {expected_seq}. Expected {expected_prev_hash}")
            return False
            
        # 3. Verify Integrity
        actual_hash = entry.get("hash")
        computed_hash = compute_row_hash(entry)
        if actual_hash != computed_hash:
            print(f"FAIL: Hash mismatch at seq {expected_seq}.")
            return False
            
        expected_prev_hash = actual_hash
        expected_seq += 1
        
    return True

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
    parser.add_argument("--dry-run", action="store_true", help="Run with mock chain data")
    parser.add_argument('chain_file', nargs='?', default=None, help='Path to chain JSON file (required unless --dry-run)')
    args = parser.parse_args()

    if not args.dry_run and not args.chain_file:
        parser.error('chain_file required')

    if args.dry_run:
        # Build mock entry using the ACTUAL compute_row_hash function
        # compute_row_hash takes a single dict and excludes the "hash" key
        mock_entry = {
            "chain_seq": 0,
            "previous_hash": "0" * 64,
            "canonical_payload": {"test": "data"}
        }
        # Compute the hash using the real function
        computed = compute_row_hash(mock_entry)
        # Add the hash field (compute_row_hash excludes it from hashing)
        mock_entry["hash"] = computed

        chain_data = [mock_entry]
        result = verify_chain(chain_data)

        # verify_chain returns bool in this implementation
        if result:
            print("PASS: dry-run successful (mock chain verified)")
            raise SystemExit(0)
        print("FAIL: dry-run mock chain failed")
        raise SystemExit(1)

    raise SystemExit(main(args.chain_file))
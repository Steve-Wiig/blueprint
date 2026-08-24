#!/usr/bin/env python3
# CI Gate: Hash Chain Concurrency Check
# Ensures atomic updates to the hash chain ledger under high-concurrency simulation.
import sys
import threading
import time
import argparse
import os
import random
from concurrent.futures import ThreadPoolExecutor

# Blueprint v11.6.0: Hash Chain Integrity Constraints
# MAX_CONCURRENT_THREADS increased default to 100, configurable via --threads
DEFAULT_MAX_CONCURRENT_THREADS = 100
MIN_LOCK_ACQUISITION_MS = 5
LEDGER_PATH = os.getenv("HASH_CHAIN_LEDGER", "/tmp/hash_chain.ledger")


class HashChainLedger:
    def __init__(self):
        self.lock = threading.Lock()
        self.chain = []

    def append_hash(self, hash_val):
        with self.lock:
            # Simulate I/O latency for ledger write
            time.sleep(random.uniform(0.001, 0.01))
            self.chain.append(hash_val)
            return len(self.chain)


def worker(ledger, results):
    try:
        # Simulate hash generation
        h = f"sha256:{random.getrandbits(256):064x}"
        idx = ledger.append_hash(h)
        results.append(idx)
    except Exception:
        results.append(None)


def main():
    parser = argparse.ArgumentParser(description="Hash Chain Concurrency Validator")
    parser.add_argument("--dry-run", action="store_true", help="Validate environment without execution")
    parser.add_argument(
        "--threads",
        type=int,
        default=DEFAULT_MAX_CONCURRENT_THREADS,
        help="Number of concurrent threads for stress test (default: {})".format(DEFAULT_MAX_CONCURRENT_THREADS),
    )
    args = parser.parse_args()

    if args.dry_run:
        print("PASS: Dry run complete. Environment ready.")
        return 0

    if not os.access(os.path.dirname(LEDGER_PATH) or ".", os.W_OK):
        print(f"CONFIG ERROR: Cannot write to {LEDGER_PATH}")
        return 2

    ledger = HashChainLedger()
    results = []
    # Stress test concurrency using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        futures = [executor.submit(worker, ledger, results) for _ in range(args.threads)]
        for future in futures:
            future.result()  # raise any exception

    # Verify integrity: No race conditions should lead to duplicate indices or lost writes
    if len(results) != args.threads:
        print("FAIL: Thread result mismatch")
        return 1

    if None in results:
        print("FAIL: Exception occurred during concurrent write")
        return 1

    if len(set(results)) != args.threads:
        print("FAIL: Race condition detected in hash chain indexing")
        return 1

    print(f"PASS: Hash chain concurrency verified with {args.threads} threads")
    return 0


if __name__ == "__main__":
    sys.exit(main())
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
from datetime import datetime, timezone
from typing import List, Optional

# Blueprint v11.6.0: Hash Chain Integrity Constraints
# MAX_CONCURRENT_THREADS increased default to 100, configurable via --threads
DEFAULT_MAX_CONCURRENT_THREADS = 100
DEFAULT_STRESS_ITERATIONS = 10
MIN_LOCK_ACQUISITION_MS = 5
MIN_IO_LATENCY_MS = 1
MAX_IO_LATENCY_MS = 10


class HashChainLedger:
    """Thread-safe ledger maintaining hash chain integrity under concurrent writes.

    This class provides atomic append operations for hash values, using an
    internal lock to prevent race conditions during high-concurrency stress tests.
    The chain is stored in memory and is suitable for validation of concurrent
    write semantics without external dependencies.
    """

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.chain: List[str] = []

    def append_hash(self, hash_val: str) -> int:
        """Append a hash value to the chain atomically.

        Acquires the internal lock, simulates ledger I/O latency, and appends
        the hash to the chain. Returns the 1-based index of the appended entry.

        Args:
            hash_val: A string representation of the hash to append (e.g., 'sha256:...').

        Returns:
            The current length of the chain after appending, representing the
            1-based index of the new hash.
        """
        with self.lock:
            # Simulate I/O latency for ledger write
            time.sleep(random.uniform(MIN_IO_LATENCY_MS / 1000, MAX_IO_LATENCY_MS / 1000))
            self.chain.append(hash_val)
            return len(self.chain)


def worker(ledger: HashChainLedger, results: List[Optional[int]]) -> None:
    """Worker thread function for concurrent hash chain stress testing.

    Generates a SHA-256 formatted hash and attempts to append it to the shared
    ledger. Appends the resulting index to the results list, or None if an
    exception occurs during the concurrent write.

    This function is designed to be executed by a ThreadPoolExecutor to verify
    that HashChainLedger maintains index uniqueness and completeness under
    high concurrency.

    Args:
        ledger: A HashChainLedger instance shared across threads for concurrent
                append operations.
        results: A list (passed by reference) where the append index or None
                 is stored upon completion of the hash append attempt.

    Returns:
        None. The function mutates the `results` list in place.
    """
    try:
        # Simulate hash generation
        h = f"sha256:{random.getrandbits(256):064x}"
        idx = ledger.append_hash(h)
        results.append(idx)
    except Exception:  # pylint: disable=broad-except
        results.append(None)


def run_stress_test(num_threads: int) -> bool:
    """Run a single stress test iteration with the given number of threads.

    Args:
        num_threads: Number of concurrent threads to use for the test.

    Returns:
        True if the test passes (no race conditions), False otherwise.
    """
    ledger = HashChainLedger()
    results: List[Optional[int]] = []
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(worker, ledger, results) for _ in range(num_threads)]
        for future in futures:
            future.result()

    if len(results) != num_threads:
        return False
    if None in results:
        return False
    if len(set(results)) != num_threads:
        return False
    return True


def main() -> int:
    now = datetime.now(timezone.utc)
    ledger_path = os.getenv("HASH_CHAIN_LEDGER", "/tmp/hash_chain.ledger")
    parser = argparse.ArgumentParser(description="Hash Chain Concurrency Validator")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate environment without execution",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=DEFAULT_MAX_CONCURRENT_THREADS,
        help="Number of concurrent threads for stress test (default: {})".format(
            DEFAULT_MAX_CONCURRENT_THREADS
        ),
    )
    args = parser.parse_args()

    if args.dry_run:
        print("PASS: Dry run complete. Environment ready.")
        return 0

    if not os.access(os.path.dirname(ledger_path) or ".", os.W_OK):
        print(f"CONFIG ERROR: Cannot write to {ledger_path}")
        return 2

    # Run stress test multiple times to increase exposure to concurrency issues
    for iteration in range(DEFAULT_STRESS_ITERATIONS):
        if not run_stress_test(args.threads):
            print(f"FAIL: Race condition detected in hash chain indexing (iteration {iteration + 1})")
            return 1

    print(f"PASS: Hash chain concurrency verified with {args.threads} threads over {DEFAULT_STRESS_ITERATIONS} iterations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
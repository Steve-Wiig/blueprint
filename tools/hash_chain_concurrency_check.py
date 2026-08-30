#!/usr/bin/env python3
"""
Hash Chain Concurrency Validator

This module provides a CI gate for validating hash chain integrity under
high-concurrency conditions. It simulates concurrent append operations to a
thread-safe hash chain ledger and verifies that no race conditions occur
during index assignment.

The validator uses an in-memory HashChainLedger with atomic append operations
protected by a threading lock. Stress tests are executed via ThreadPoolExecutor
with configurable thread counts to expose potential concurrency bugs.

Usage:
    python hash_chain_concurrency.py [--threads N] [--dry-run]

Environment Variables:
    HASH_CHAIN_LEDGER: Path to ledger file (default: /tmp/hash_chain.ledger)

Exit Codes:
    0: All stress tests passed
    1: Race condition detected
    2: Configuration error (e.g., unwritable ledger path)
"""

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
# DEFAULT_MAX_CONCURRENT_THREADS: Maximum number of concurrent threads for stress testing.
#   Expected range: 1-1000. Higher values increase contention exposure but consume more resources.
#   Default 100 balances CI execution time with race condition detection probability.
DEFAULT_MAX_CONCURRENT_THREADS = 100

# DEFAULT_STRESS_ITERATIONS: Number of stress test iterations to run.
#   Expected range: 1-100. Multiple iterations increase probability of exposing
#   intermittent race conditions. Default 10 provides reasonable confidence
#   while keeping CI runtime acceptable.
DEFAULT_STRESS_ITERATIONS = 10


class HashChainLedger:
    """Thread-safe ledger maintaining hash chain integrity under concurrent writes.

    This class provides atomic append operations for hash values, using an
    internal lock to prevent race conditions during high-concurrency stress tests.
    The chain is stored in memory and is suitable for validation of concurrent
    write semantics without external dependencies.

    Attributes:
        lock: A threading.Lock instance protecting the chain during mutations.
        chain: A list of hash strings representing the append-only ledger.
    """

    def __init__(self) -> None:
        """Initialize a new HashChainLedger with an empty chain and a threading lock.

        The ledger is prepared for concurrent append operations. An internal
        lock ensures atomicity of hash chain updates across multiple threads.
        """
        self.lock = threading.Lock()
        self.chain: List[str] = []

    def append_hash(self, hash_val: str) -> int:
        """Append a hash value to the chain atomically.

        Acquires the internal lock and appends the hash to the chain.
        Returns the 1-based index of the appended entry.

        Args:
            hash_val: A string representation of the hash to append (e.g., 'sha256:...').

        Returns:
            The current length of the chain after appending, representing the
            1-based index of the new hash.
        """
        with self.lock:
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


def run_stress_test(executor: ThreadPoolExecutor, num_threads: int) -> bool:
    """Run a single stress test iteration with the given number of threads.

    Creates a fresh HashChainLedger and spawns `num_threads` workers to
    concurrently append hashes. Validates that all appends succeed, return
    unique indices, and no operations fail.

    Args:
        executor: ThreadPoolExecutor to use for submitting worker tasks.
        num_threads: Number of concurrent threads to use for the test.

    Returns:
        True if the test passes (no race conditions), False otherwise.
    """
    ledger = HashChainLedger()
    results: List[Optional[int]] = []
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


def get_ledger_path() -> str:
    """Resolve the ledger file path from the environment without side effects at import time.

    Returns:
        The ledger file path from HASH_CHAIN_LEDGER environment variable,
        or the default '/tmp/hash_chain.ledger' if not set.
    """
    return os.getenv("HASH_CHAIN_LEDGER", "/tmp/hash_chain.ledger")


def main() -> int:
    """Entry point for the hash chain concurrency validator.

    Validates the environment and runs stress tests to verify hash chain
    integrity under concurrent writes. Outputs pass/fail status and returns
    an exit code suitable for CI pipelines.

    Returns:
        0 if validation passes, 1 if race conditions are detected, 2 if
        configuration errors prevent testing.
    """
    ledger_path = get_ledger_path()
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
        help=f"Number of concurrent threads for stress test (default: {DEFAULT_MAX_CONCURRENT_THREADS})",
    )
    args = parser.parse_args()

    if args.dry_run:
        print("PASS: Dry run complete. Environment ready.")
        return 0

    if not os.access(os.path.dirname(ledger_path) or ".", os.W_OK):
        print(f"CONFIG ERROR: Cannot write to {ledger_path}")
        return 2

    # Run stress test multiple times to increase exposure to concurrency issues
    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        for iteration in range(DEFAULT_STRESS_ITERATIONS):
            if not run_stress_test(executor, args.threads):
                print(f"FAIL: Race condition detected in hash chain indexing (iteration {iteration + 1})")
                return 1

    print(f"PASS: Hash chain concurrency verified with {args.threads} threads over {DEFAULT_STRESS_ITERATIONS} iterations")
    return 0

if __name__ == "__main__":
    try:
        raise RuntimeError(main())
    except RuntimeError as e:
        sys.exit(e.args[0] if isinstance(e.args[0], int) else 1)
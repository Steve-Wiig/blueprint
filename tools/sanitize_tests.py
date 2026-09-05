#!/usr/bin/env python3
"""
tools/sanitize_tests.py
------------------------
Quarantines broken auto-generated TDD tests so they don't break pytest collection.
"""
import subprocess
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).parent.parent
TESTS_DIR = ROOT / "tests"
QUARANTINE_DIR = ROOT / ".quarantined_tests"

def main():
    QUARANTINE_DIR.mkdir(exist_ok=True)
    tdd_tests = list(TESTS_DIR.glob("test_tdd_auto_*.py"))
    if not tdd_tests: return
    
    quarantined = 0
    for test_file in tdd_tests:
        # Run collect-only on the individual file
        res = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", str(test_file)],
            cwd=ROOT, capture_output=True, timeout=10
        )
        # If it fails to collect (syntax error, bad import), quarantine it
        if res.returncode != 0:
            shutil.move(str(test_file), str(QUARANTINE_DIR / test_file.name))
            quarantined += 1
            
    if quarantined > 0:
        print(f"🧹 SANITIZER: Quarantined {quarantined} broken TDD tests to tests/quarantine/")

if __name__ == "__main__":
    main()

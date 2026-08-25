#!/usr/bin/env python3
"""
CI Gate: Changelog Completeness Check

This module verifies that every commit since the last Git tag has a corresponding
entry in CHANGELOG.md. It is designed to run in CI pipelines to enforce
changelog maintenance discipline.

The script operates by:
1. Finding the most recent Git tag (using `git describe --tags --abbrev=0`)
2. Enumerating all commits since that tag (using `git log <tag>..HEAD`)
3. Parsing CHANGELOG.md for commit hashes (7-12 hex characters)
4. Reporting any commits missing from the changelog

Exit codes:
    0: All commits accounted for in CHANGELOG.md (PASS)
    1: One or more commits missing from CHANGELOG.md (FAIL)
    2: Configuration error - no Git tags found to compare against
    3: Environment error - not a Git repository (no .git directory)

Side effects:
    - Reads from .git directory and CHANGELOG.md
    - Executes git subprocesses
    - Prints results to stdout
    - Returns exit code for CI integration

Usage:
    python verify_changelog.py [--dry-run] [--changelog-path PATH]

    --dry-run: Validate logic without failing (returns 0 even if missing entries)
    --changelog-path: Path to changelog file (default: CHANGELOG.md)
"""

import os
import sys
import subprocess
import argparse
import re
from typing import List, Optional, Pattern


def main() -> int:
    """
    Verify CHANGELOG.md completeness against git commit history.

    Parses command-line arguments, retrieves commits since the latest tag,
    scans CHANGELOG.md for commit hashes, and reports any missing entries.

    Args:
        None (uses sys.argv via argparse):
            --dry-run (bool): If set, returns 0 even when commits are missing.
                              Useful for testing CI logic without blocking pipelines.
            --changelog-path (str): Path to changelog file (default: CHANGELOG.md)

    Returns:
        int: Exit code indicating verification result:
            0 = PASS (all commits have changelog entries, or --dry-run)
            1 = FAIL (one or more commits missing from CHANGELOG.md)
            2 = CONFIG ERROR (no Git tags found to establish baseline)
            3 = ENV NOT AVAILABLE (not a Git repository; .git directory missing)

    Side effects:
        - Executes `git describe` and `git log` subprocesses
        - Reads CHANGELOG.md from current working directory
        - Prints human-readable status messages to stdout
        - Does not modify any files
    """
    parser = argparse.ArgumentParser(description="Verify CHANGELOG completeness")
    parser.add_argument("--dry-run", action="store_true", help="Validate logic without failing")
    parser.add_argument("--changelog-path", default="CHANGELOG.md", help="Path to changelog file (default: CHANGELOG.md)")
    args: argparse.Namespace = parser.parse_args()

    # Ensure we are in a git repository
    if not os.path.exists(".git"):
        print("ENV_NOT_AVAILABLE: Not a git repository")
        return 3

    try:
        # Get the latest tag
        latest_tag: str = subprocess.check_output(
            ["git", "describe", "--tags", "--abbrev=0"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
    except subprocess.CalledProcessError:
        print("CONFIG ERROR: No tags found to compare against")
        return 2

    # Get list of commits since latest tag
    try:
        commits: list[str] = subprocess.check_output(
            ["git", "log", f"{latest_tag}..HEAD", "--pretty=format:%h %s"]
        ).decode().splitlines()
    except subprocess.CalledProcessError:
        print("FAIL: Could not retrieve commit history")
        return 1

    changelog_path: str = args.changelog_path
    if not os.path.exists(changelog_path):
        print(f"FAIL: {changelog_path} missing")
        return 1

    # Parse changelog line-by-line to build a set of commit hashes found,
    # avoiding loading the entire file into memory for large changelogs.
    commit_hash_pattern: Pattern[str] = re.compile(r'\b([0-9a-f]{7,12})\b')
    changelog_hashes: set[str] = set()

    with open(changelog_path, "r") as f:
        for line in f:
            changelog_hashes.update(commit_hash_pattern.findall(line.lower()))

    missing_entries: list[str] = []
    for commit in commits:
        commit_hash: str = commit.split(" ")[0].lower()
        if commit_hash not in changelog_hashes:
            missing_entries.append(commit)

    if missing_entries:
        print(f"FAIL: The following commits are missing from {changelog_path}:")
        for entry in missing_entries:
            print(f"  - {entry}")
        return 0 if args.dry_run else 1

    print(f"PASS: All commits accounted for in {changelog_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
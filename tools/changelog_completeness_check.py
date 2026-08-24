#!/usr/bin/env python3
"""
CI Gate: Changelog Completeness Check

Verifies that every commit since the last tag has a corresponding entry in CHANGELOG.md.
This script is designed to run in CI pipelines to enforce changelog maintenance.
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

    Returns:
        int: Exit code - 0 for success, 1 for missing entries, 2 for config errors,
             3 for environment issues (not a git repo).
    """
    parser = argparse.ArgumentParser(description="Verify CHANGELOG completeness")
    parser.add_argument("--dry-run", action="store_true", help="Validate logic without failing")
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

    if not os.path.exists("CHANGELOG.md"):
        print("FAIL: CHANGELOG.md missing")
        return 1

    # Parse changelog line-by-line to build a set of commit hashes found,
    # avoiding loading the entire file into memory for large changelogs.
    commit_hash_pattern: Pattern[str] = re.compile(r'\b([0-9a-f]{7,12})\b')
    changelog_hashes: set[str] = set()

    with open("CHANGELOG.md", "r") as f:
        for line in f:
            changelog_hashes.update(commit_hash_pattern.findall(line.lower()))

    missing_entries: list[str] = []
    for commit in commits:
        commit_hash: str = commit.split(" ")[0].lower()
        if commit_hash not in changelog_hashes:
            missing_entries.append(commit)

    if missing_entries:
        print(f"FAIL: The following commits are missing from CHANGELOG.md:")
        for entry in missing_entries:
            print(f"  - {entry}")
        return 0 if args.dry_run else 1

    print("PASS: All commits accounted for in CHANGELOG.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
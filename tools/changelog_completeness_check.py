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
from typing import List, Optional, Pattern, Set


EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_CONFIG_ERROR = 2
EXIT_ENV_ERROR = 3


def get_latest_tag() -> Optional[str]:
    """
    Retrieve the most recent Git tag.

    Returns:
        The latest tag name as a string, or None if no tags exist.
    """
    try:
        tag = subprocess.check_output(
            ["git", "describe", "--tags", "--abbrev=0"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        return tag
    except subprocess.CalledProcessError:
        return None


def get_commits_since_tag(tag: str) -> List[str]:
    """
    Get all commits since the given tag.

    Args:
        tag: The Git tag to compare against.

    Returns:
        List of commit strings in format "%h %s" (short hash + subject).
    """
    try:
        output = subprocess.check_output(
            ["git", "log", f"{tag}..HEAD", "--pretty=format:%h %s"]
        ).decode()
        return output.splitlines() if output else []
    except subprocess.CalledProcessError:
        return []


def parse_changelog_hashes(changelog_path: str) -> Set[str]:
    """
    Parse CHANGELOG.md and extract all commit hashes (7-12 hex chars).

    Args:
        changelog_path: Path to the changelog file.

    Returns:
        Set of lowercase commit hashes found in the changelog.
    """
    commit_hash_pattern: Pattern[str] = re.compile(r'\b([0-9a-f]{7,12})\b')
    changelog_hashes: Set[str] = set()

    with open(changelog_path, "r") as f:
        for line in f:
            changelog_hashes.update(commit_hash_pattern.findall(line.lower()))

    return changelog_hashes


def find_missing_entries(commits: List[str], changelog_hashes: Set[str]) -> List[str]:
    """
    Find commits that are missing from the changelog.

    Args:
        commits: List of commit strings in format "%h %s".
        changelog_hashes: Set of commit hashes found in changelog.

    Returns:
        List of commit strings that are missing from changelog.
    """
    missing_entries: List[str] = []
    for commit in commits:
        commit_hash: str = commit.split(" ")[0].lower()
        if commit_hash not in changelog_hashes:
            missing_entries.append(commit)
    return missing_entries


def print_results(missing_entries: List[str], changelog_path: str, dry_run: bool) -> int:
    """
    Print verification results and return appropriate exit code.

    Args:
        missing_entries: List of commits missing from changelog.
        changelog_path: Path to changelog file (for output messages).
        dry_run: If True, return 0 even when entries are missing.

    Returns:
        Exit code: 0 for PASS, 1 for FAIL (unless dry_run).
    """
    if missing_entries:
        print(f"FAIL: The following commits are missing from {changelog_path}:")
        for entry in missing_entries:
            print(f"  - {entry}")
        return EXIT_PASS if dry_run else EXIT_FAIL

    print(f"PASS: All commits accounted for in {changelog_path}")
    return EXIT_PASS


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
        return EXIT_ENV_ERROR

    # Get the latest tag
    latest_tag = get_latest_tag()
    if latest_tag is None:
        print("CONFIG ERROR: No tags found to compare against")
        return EXIT_CONFIG_ERROR

    # Get list of commits since latest tag
    commits = get_commits_since_tag(latest_tag)
    if not commits and latest_tag:
        # No commits since tag is valid - all accounted for
        pass

    changelog_path: str = args.changelog_path
    if not os.path.exists(changelog_path):
        print(f"FAIL: {changelog_path} missing")
        return EXIT_FAIL

    # Parse changelog for commit hashes
    changelog_hashes = parse_changelog_hashes(changelog_path)

    # Find missing entries
    missing_entries = find_missing_entries(commits, changelog_hashes)

    # Print results and return exit code
    return print_results(missing_entries, changelog_path, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
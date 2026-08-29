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
from typing import List, Optional, Pattern, Set, Iterator


EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_CONFIG_ERROR = 2
EXIT_ENV_ERROR = 3

COMMIT_HASH_PATTERN: Pattern[str] = re.compile(r'\b([0-9a-f]{7,12})\b')  # Git short hashes are 7-12 chars (default 7, configurable up to 40)


class GitRepo:
    """Encapsulate git-related operations."""

    @staticmethod
    def is_git_repo() -> bool:
        return os.path.exists(".git")

    @staticmethod
    def get_latest_tag() -> Optional[str]:
        """
        Retrieve the most recent Git tag.

        Returns:
            The latest tag name as a string, or None if no tags exist.

        Raises:
            FileNotFoundError: If git executable is not found.
        """
        try:
            tag = subprocess.check_output(
                ["git", "describe", "--tags", "--abbrev=0"],
                stderr=subprocess.DEVNULL
            ).decode().strip()
            return tag
        except subprocess.CalledProcessError:
            return None

    @staticmethod
    def iter_commits_since_tag(tag: str) -> Iterator[str]:
        """
        Stream commits since the given tag without loading all into memory.

        Args:
            tag: The Git tag to compare against.

        Yields:
            Commit strings in format "%h %s" (short hash + subject).
        """
        proc = subprocess.Popen(
            ["git", "log", f"{tag}..HEAD", "--pretty=format:%h %s"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        try:
            if proc.stdout:
                for line in proc.stdout:
                    yield line.rstrip("\n")
        finally:
            proc.wait()

    @staticmethod
    def get_commits_since_tag(tag: str) -> List[str]:
        """
        Get all commits since the given tag.

        Args:
            tag: The Git tag to compare against.

        Returns:
            List of commit strings in format "%h %s" (short hash + subject).
        """
        return list(GitRepo.iter_commits_since_tag(tag))


class ChangelogParser:
    """Encapsulate changelog parsing."""

    @staticmethod
    def parse_hashes(changelog_path: str) -> Set[str]:
        """
        Parse CHANGELOG.md and extract all commit hashes (7-12 hex chars).

        Args:
            changelog_path: Path to the changelog file.

        Returns:
            Set of lowercase commit hashes found in the changelog.
        """
        with open(changelog_path, "r") as f:
            content = f.read()
        return set(COMMIT_HASH_PATTERN.findall(content.lower()))

def get_latest_tag() -> Optional[str]:
    """Module-level function for test patching isolation."""
    return GitRepo.get_latest_tag()

def iter_commits_since_tag(tag: str) -> Iterator[str]:
    """Module-level function for backward compatibility with tests."""
    import subprocess
    cmd = ["git", "log", "--format=%h %s", f"{tag}..HEAD"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
    try:
        for line in proc.stdout:
            yield line.rstrip("\n")
    finally:
        proc.stdout.close()
        return_code = proc.wait()
        if return_code != 0:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(f"git log failed with code {return_code}: {stderr}")

def get_commits_since_tag(tag: str) -> List[str]:
    """Module-level function for backward compatibility with tests."""
    return GitRepo.get_commits_since_tag(tag)


def parse_changelog_hashes(changelog_path: str) -> Set[str]:
    """Module-level function for backward compatibility with tests."""
    return ChangelogParser.parse_hashes(changelog_path)


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

    Orchestrates argument parsing, repository inspection, changelog parsing,
    and result reporting while delegating specific responsibilities to
    helper classes.

    Exit codes:
        0 (EXIT_PASS): All commits since latest tag are documented in changelog.
        1 (EXIT_FAIL): Changelog file missing or commits missing from changelog.
        2 (EXIT_CONFIG_ERROR): No git tags found to compare against.
        3 (EXIT_ENV_ERROR): Not a git repository, git command not found,
           or repository invalid (e.g., corrupted).
    """
    parser = argparse.ArgumentParser(description="Verify CHANGELOG completeness")
    parser.add_argument("--dry-run", action="store_true", help="Validate logic without failing")
    parser.add_argument(
        "--changelog-path",
        default="CHANGELOG.md",
        help="Path to changelog file (default: CHANGELOG.md)",
    )
    args: argparse.Namespace = parser.parse_args()

    # Verify repository presence
    if not GitRepo.is_git_repo():
        print("ENV_NOT_AVAILABLE: Not a git repository")
        return EXIT_ENV_ERROR

    # Retrieve latest tag
    try:
        latest_tag = GitRepo.get_latest_tag()
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("ENV_NOT_AVAILABLE: git command not found or repository invalid")
        return EXIT_ENV_ERROR

    if latest_tag is None:
        print("CONFIG ERROR: No tags found to compare against")
        return EXIT_CONFIG_ERROR

    # Gather commits since the latest tag
    commits = GitRepo.get_commits_since_tag(latest_tag)

    # Ensure changelog file exists
    changelog_path: str = args.changelog_path
    if not os.path.exists(changelog_path):
        print(f"FAIL: {changelog_path} missing")
        return EXIT_FAIL

    # Parse changelog for commit hashes
    changelog_hashes = ChangelogParser.parse_hashes(changelog_path)

    # Determine missing entries
    missing_entries = find_missing_entries(commits, changelog_hashes)

    # Report results
    return print_results(missing_entries, changelog_path, args.dry_run)

if __name__ == "__main__":
    sys.exit(main())
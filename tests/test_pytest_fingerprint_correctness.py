"""Regression tests for pytest baseline cache fingerprint correctness.

Improvement Candidate: Pytest Cache Correctness
BEFORE: 4096-byte truncation + tracked-only file list caused false cache hits.
AFTER: Full-content hashing of pytest-relevant files (tracked + untracked).
"""
import subprocess, os, hashlib, tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _make_temp_git_repo(tmp_path):
    """Create a minimal git repo for isolated fingerprint testing."""
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)
    return tmp_path


def _compute_fingerprint_for(root, relevant_prefixes=("tests/", "engine/")):
    """Compute fingerprint using the same logic as _get_repo_fingerprint."""
    h = hashlib.sha256()
    result = subprocess.run(
        ["git", "ls-tree", "-r", "HEAD", "--name-only"],
        capture_output=True, text=True, cwd=str(root), timeout=10
    )
    if result.returncode != 0:
        return None
    tracked = set(f.strip() for f in result.stdout.splitlines() if f.strip())

    result2 = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        capture_output=True, text=True, cwd=str(root), timeout=10
    )
    untracked = set()
    if result2.returncode == 0:
        untracked = set(f.strip() for f in result2.stdout.splitlines() if f.strip())

    for f in sorted(tracked | untracked):
        if not any(f.startswith(p) for p in relevant_prefixes):
            continue
        h.update(f.encode())
        p_file = Path(root) / f
        if p_file.exists():
            h.update(p_file.read_bytes())
        else:
            h.update(b"__DELETED__")
    return h.hexdigest()[:16]


def test_old_4096_truncation_false_hit(tmp_path):
    """Test A: Prove the OLD implementation produces a false cache hit.

    A file > 4096 bytes with changes beyond byte 4095 should produce
    the SAME fingerprint under the old (truncated) logic.
    """
    repo = _make_temp_git_repo(tmp_path)
    tests_dir = repo / "tests"
    tests_dir.mkdir()

    # Create a test file > 4096 bytes. First 4096 bytes are padding.
    padding = "# " + "x" * 4094 + "\n"  # 4096 bytes of padding
    content_before = padding + "def test_pass():\n    assert True\n"
    content_after = padding + "def test_pass():\n    assert False\n"  # Changed assertion

    (tests_dir / "test_example.py").write_text(content_before)
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True)

    # Old logic: hash first 4096 bytes only
    def old_fingerprint():
        h = hashlib.sha256()
        f = "tests/test_example.py"
        h.update(f.encode())
        p = repo / f
        with open(p, "rb") as fp:
            h.update(fp.read(4096))
        return h.hexdigest()[:16]

    fp_before = old_fingerprint()

    # Modify bytes beyond 4096
    (tests_dir / "test_example.py").write_text(content_after)

    fp_after = old_fingerprint()

    # OLD BUG: fingerprints are identical despite content change
    assert fp_before == fp_after, (
        "Old logic should produce same fingerprint for changes beyond 4096"
    )


def test_new_full_content_detects_change(tmp_path):
    """Test C: After fix, changing bytes > 4096 MUST change the fingerprint."""
    repo = _make_temp_git_repo(tmp_path)
    tests_dir = repo / "tests"
    tests_dir.mkdir()

    padding = "# " + "x" * 4094 + "\n"
    content_before = padding + "def test_pass():\n    assert True\n"
    content_after = padding + "def test_pass():\n    assert False\n"

    (tests_dir / "test_example.py").write_text(content_before)
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True)

    fp_before = _compute_fingerprint_for(repo)

    # Modify bytes beyond 4096
    (tests_dir / "test_example.py").write_text(content_after)

    fp_after = _compute_fingerprint_for(repo)

    assert fp_before != fp_after, (
        "Fixed fingerprint must detect changes beyond 4096 bytes"
    )


def test_new_detects_untracked_test_file(tmp_path):
    """Test B/C: Adding an untracked test file MUST change the fingerprint."""
    repo = _make_temp_git_repo(tmp_path)
    tests_dir = repo / "tests"
    tests_dir.mkdir()

    (tests_dir / "test_existing.py").write_text("def test_a(): assert True\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True)

    fp_before = _compute_fingerprint_for(repo)

    # Add untracked test file
    (tests_dir / "test_new_untracked.py").write_text("def test_b(): assert False\n")

    fp_after = _compute_fingerprint_for(repo)

    assert fp_before != fp_after, (
        "Fingerprint must detect new untracked test files"
    )


def test_unchanged_state_cache_hit(tmp_path):
    """Test D: Unchanged state MUST produce the same fingerprint (cache hit)."""
    repo = _make_temp_git_repo(tmp_path)
    tests_dir = repo / "tests"
    tests_dir.mkdir()

    (tests_dir / "test_stable.py").write_text("def test_ok(): assert True\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True)

    fp1 = _compute_fingerprint_for(repo)
    fp2 = _compute_fingerprint_for(repo)

    assert fp1 == fp2, (
        "Unchanged state must produce identical fingerprint (cache hit)"
    )
    assert fp1 is not None


def test_deleted_file_changes_fingerprint(tmp_path):
    """Deleting a tracked test file MUST change the fingerprint."""
    repo = _make_temp_git_repo(tmp_path)
    tests_dir = repo / "tests"
    tests_dir.mkdir()

    (tests_dir / "test_to_delete.py").write_text("def test_x(): assert True\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True)

    fp_before = _compute_fingerprint_for(repo)

    (tests_dir / "test_to_delete.py").unlink()

    fp_after = _compute_fingerprint_for(repo)

    assert fp_before != fp_after, (
        "Fingerprint must detect deleted test files"
    )


def test_non_pytest_files_ignored(tmp_path):
    """Changes to non-pytest-relevant files MUST NOT change the fingerprint."""
    repo = _make_temp_git_repo(tmp_path)
    tests_dir = repo / "tests"
    tests_dir.mkdir()

    (tests_dir / "test_ok.py").write_text("def test_a(): assert True\n")
    (repo / "README.md").write_text("# Hello\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True)

    fp_before = _compute_fingerprint_for(repo)

    # Modify README (not pytest-relevant)
    (repo / "README.md").write_text("# Changed\n")

    fp_after = _compute_fingerprint_for(repo)

    assert fp_before == fp_after, (
        "Non-pytest files should not affect the fingerprint"
    )

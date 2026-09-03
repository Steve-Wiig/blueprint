"""
Regression test for Improvement #4: Baseline pytest Caching

BEFORE: Every advisory re-runs pytest baseline from scratch (~40s).
PROBLEM: Redundant pytest runs when repo state hasn't changed.
CHANGE: run_pytest_cached() memoizes results keyed by
        (repo_fingerprint, targets).
"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture(autouse=True)
def reset_cache():
    """Reset the module-level cache before each test."""
    import overnight.self_improver as si
    si._baseline_cache = {"fingerprint": None, "result": None, "targets": None}
    yield
    si._baseline_cache = {"fingerprint": None, "result": None, "targets": None}


def test_cache_hit_on_unchanged_repo():
    """Two calls with same fingerprint + targets = one pytest run."""
    import overnight.self_improver as si
    
    mock_run = MagicMock(return_value=None)  # pytest passes
    
    with patch.object(si, '_get_repo_fingerprint', return_value='fp_abc123'), \
         patch.object(si, 'run_pytest', mock_run):
        
        r1 = si.run_pytest_cached(['tests/test_a.py'])
        r2 = si.run_pytest_cached(['tests/test_a.py'])
    
    assert mock_run.call_count == 1, "pytest should be called only once (cache hit)"
    assert r1 is None and r2 is None


def test_cache_invalidates_on_repo_change():
    """Changed fingerprint = cache miss, pytest re-runs."""
    import overnight.self_improver as si
    
    fingerprints = iter(['fp_abc123', 'fp_xyz789'])
    mock_run = MagicMock(return_value=None)
    
    with patch.object(si, '_get_repo_fingerprint', side_effect=lambda: next(fingerprints)), \
         patch.object(si, 'run_pytest', mock_run):
        
        si.run_pytest_cached(['tests/test_a.py'])
        si.run_pytest_cached(['tests/test_a.py'])
    
    assert mock_run.call_count == 2, "pytest must re-run when fingerprint changes"


def test_cache_respects_different_targets():
    """Different targets = cache miss. Single-entry cache only remembers last."""
    import overnight.self_improver as si
    
    mock_run = MagicMock(return_value=None)
    
    with patch.object(si, '_get_repo_fingerprint', return_value='fp_abc123'), \
         patch.object(si, 'run_pytest', mock_run):
        
        si.run_pytest_cached(['tests/test_a.py'])   # miss -> run (1)
        si.run_pytest_cached(['tests/test_b.py'])   # different targets -> miss -> run (2)
        si.run_pytest_cached(['tests/test_b.py'])   # same as last -> HIT
    
    assert mock_run.call_count == 2, "Single-entry cache: only last (fp,targets) pair is cached"


def test_sniper_scope_not_cached(tmp_path):
    """The Sniper Scope (after fix applied) must NOT use cache.
    
    This is a structural guarantee: we grep the source to prove
    only the baseline call uses the cached version.
    """
    import overnight.self_improver as si
    import inspect
    source = inspect.getsource(si.apply_auto_fix)
    
    cached_count = source.count('run_pytest_cached')
    uncached_count = source.count('run_pytest(') - cached_count  # subtract cached refs
    
    assert cached_count == 1, f"Expected exactly 1 cached call (baseline), got {cached_count}"
    assert uncached_count >= 1, "Sniper Scope must use uncached run_pytest"

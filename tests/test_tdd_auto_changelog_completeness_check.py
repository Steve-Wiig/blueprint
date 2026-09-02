import pytest
from unittest.mock import MagicMock, patch
from changelog_completeness_check import GitRepo


def test_get_commits_since_tag_returns_iterator_not_list():
    """Test that get_commits_since_tag returns an iterator to avoid O(n) memory."""
    mock_repo = MagicMock(spec=GitRepo)
    
    def mock_iter_commits(tag):
        for i in range(1000):
            yield MagicMock(hexsha=f"commit{i}", message=f"Commit {i}")
    
    mock_repo.iter_commits_since_tag = mock_iter_commits
    
    with patch.object(GitRepo, '__new__', return_value=mock_repo):
        repo = GitRepo()
        result = repo.get_commits_since_tag("v1.0.0")
        
        assert hasattr(result, '__iter__')
        assert not hasattr(result, '__len__') or not isinstance(result, list)
        assert type(result).__name__ in ('generator', 'iterator')
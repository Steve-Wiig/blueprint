"""
Regression test for Improvement #10: Guaranteed code visibility.

BEFORE: If the issue description didn't contain a function name, the pruned
        context omitted ALL functions. The LLM hallucinated the structure.
CHANGE: When no target matches, include every real top-level definition.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

SOURCE = "import os\n\ndef alpha():\n    return 1\n\ndef beta():\n    return 2\n"


def test_no_name_match_still_shows_all_functions():
    import overnight.self_improver as si
    issue = "performance problem in the module"  # contains no function name
    pruned = si._prune_ast_context(SOURCE, issue)
    assert "def alpha" in pruned, "alpha must be visible"
    assert "def beta" in pruned, "beta must be visible"
    assert "import os" in pruned


def test_name_match_gives_focused_context():
    import overnight.self_improver as si
    issue = "bug in alpha function"
    pruned = si._prune_ast_context(SOURCE, issue)
    assert "def alpha" in pruned
    assert "import os" in pruned


def test_large_file_never_exceeds_max():
    import overnight.self_improver as si
    big = "import os\n" + "\n".join(f"def f{i}():\n    return {i}\n" for i in range(500))
    pruned = si._prune_ast_context(big, "no match", max_chars=2000)
    assert len(pruned) <= 2000

"""Regression test for Improvement #11: whole-file raw context."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

def test_small_file_returns_raw_with_comments():
    import overnight.self_improver as si
    src = "# important comment\nimport os\n\ndef alpha():\n    return 1\n"
    assert si._choose_context(src, "bug") == src, "small file must be raw (comments preserved)"

def test_large_file_falls_back_to_pruned():
    import overnight.self_improver as si
    big = "import os\n" + "\n".join(f"def f{i}():\n    return {i}\n" for i in range(2000))
    out = si._choose_context(big, "bug", raw_cap=2000)
    assert len(out) < len(big), 'large file must be pruned, not raw'

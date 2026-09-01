import pytest
from engine.patch_parser import (
    process_llm_patch, parse_patch_blocks, PatchParseError,
    PatchApplyError, ScopeBudgetExceededError, FUZZY_SIMILARITY_THRESHOLD,
)

SAMPLE_PY_FILE = """def hello_world():
    print("Hello, World!")

class MyClass:
    def __init__(self):
        self.value = 42

    def get_value(self):
        return self.value
"""

def test_parse_malformed_missing_divider():
    with pytest.raises(PatchParseError, match="Missing '=======' divider"):
        parse_patch_blocks("<<<<<<< SEARCH\nfoo\n>>>>>>> REPLACE")

def test_apply_exact_match_single_block():
    patch = "<<<<<<< SEARCH\n    print(\"Hello, World!\")\n=======\n    print(\"Hello, LOCAL-SOC!\")\n>>>>>>> REPLACE"
    res = process_llm_patch(SAMPLE_PY_FILE, patch)
    assert res.success
    assert 'print("Hello, LOCAL-SOC!")' in res.modified_content

def test_fuzzy_match_missing_indent():
    patch = (
        "<<<<<<< SEARCH\n"
        "def __init__(self):\n"
        "        self.value = 42\n"
        "=======\n"
        "def __init__(self, val=99):\n"
        "        self.value = val\n"
        ">>>>>>> REPLACE"
    )
    res = process_llm_patch(SAMPLE_PY_FILE, patch)
    assert res.success
    assert res.blocks[0].is_fuzzy_match is True
    assert res.blocks[0].similarity_ratio > FUZZY_SIMILARITY_THRESHOLD

def test_fuzzy_reject_below_threshold():
    patch = "<<<<<<< SEARCH\ncompletely_different_function():\n    pass\n=======\nmalicious_code()\n>>>>>>> REPLACE"
    with pytest.raises(PatchApplyError, match="SEARCH block not found"):
        process_llm_patch(SAMPLE_PY_FILE, patch)

def test_overlapping_blocks_rejected():
    patch = (
        "<<<<<<< SEARCH\n"
        "def hello_world():\n"
        '    print("Hello, World!")\n'
        "=======\n"
        "def hello_world():\n"
        '    print("A")\n'
        ">>>>>>> REPLACE\n\n"
        "<<<<<<< SEARCH\n"
        '    print("Hello, World!")\n'
        "\n"
        "class MyClass:\n"
        "=======\n"
        '    print("B")\n'
        "\n"
        "class MyClass:\n"
        ">>>>>>> REPLACE"
    )
    with pytest.raises(PatchApplyError, match="Overlapping patches detected"):
        process_llm_patch(SAMPLE_PY_FILE, patch)

def test_scope_budget_exceeded_rejected():
    large_search = "\n".join([f"line_{i}" for i in range(600)])
    large_replace = "\n".join([f"hacked_{i}" for i in range(600)])
    patch = f"<<<<<<< SEARCH\n{large_search}\n=======\n{large_replace}\n>>>>>>> REPLACE"
    source = "\n".join([f"line_{i}" for i in range(600)])
    with pytest.raises(ScopeBudgetExceededError, match="Scope Budget Exceeded"):
        process_llm_patch(source, patch)

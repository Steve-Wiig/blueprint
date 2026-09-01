"""
engine/patch_parser.py
----------------------
Production-grade Search/Replace patch parser for LOCAL-SOC-SLM.
Enforces Aider-style contract: <<<<<<< SEARCH ... ======= ... >>>>>>> REPLACE
"""

from __future__ import annotations
import difflib
import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger("local_soc_slm.patch_parser")
logger.setLevel(logging.INFO)

MAX_LINES_CHANGED_PER_PATCH_SET = 500
FUZZY_SIMILARITY_THRESHOLD = 0.85
SEARCH_BLOCK_MARKER = "<<<<<<< SEARCH"
DIVIDER_MARKER = "======="
REPLACE_BLOCK_MARKER = ">>>>>>> REPLACE"

@dataclass(frozen=True)
class PatchBlock:
    search_lines: Tuple[str, ...]
    replace_lines: Tuple[str, ...]
    original_start_line: int = -1
    is_fuzzy_match: bool = False
    similarity_ratio: float = 1.0

@dataclass
class PatchResult:
    success: bool
    applied_blocks: int
    total_lines_changed: int
    error_message: Optional[str] = None
    modified_content: Optional[str] = None
    blocks: List[PatchBlock] = field(default_factory=list)

class PatchParseError(ValueError): pass
class PatchApplyError(RuntimeError): pass
class ScopeBudgetExceededError(PatchApplyError): pass

def parse_patch_blocks(raw_llm_output: str) -> List[PatchBlock]:
    blocks = []
    lines = raw_llm_output.splitlines(keepends=False)
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line != SEARCH_BLOCK_MARKER:
            i += 1
            continue
        i += 1
        search_start = i
        while i < len(lines) and lines[i].strip() != DIVIDER_MARKER:
            i += 1
        if i >= len(lines):
            raise PatchParseError("Unterminated SEARCH block: Missing '=======' divider.")
        search_content = tuple(lines[search_start:i])
        i += 1
        replace_start = i
        while i < len(lines) and lines[i].strip() != REPLACE_BLOCK_MARKER:
            i += 1
        if i >= len(lines):
            raise PatchParseError("Unterminated REPLACE block: Missing '>>>>>>> REPLACE' marker.")
        replace_content = tuple(lines[replace_start:i])
        if not search_content and not replace_content:
            raise PatchParseError("Empty SEARCH and REPLACE block (No-op).")
        blocks.append(PatchBlock(search_lines=search_content, replace_lines=replace_content))
        i += 1
    if not blocks:
        raise PatchParseError("No valid SEARCH/REPLACE blocks found in LLM output.")
    return blocks

def _calculate_lines_changed(search: Tuple[str, ...], replace: Tuple[str, ...]) -> int:
    return max(len(search), len(replace))

def _find_exact_match(source_lines: List[str], search_lines: Tuple[str, ...]) -> Optional[int]:
    if not search_lines: return 0
    first_line = search_lines[0]
    for i, line in enumerate(source_lines):
        if line == first_line:
            if tuple(source_lines[i : i + len(search_lines)]) == search_lines:
                return i
    return None

def _find_fuzzy_match(source_lines: List[str], search_lines: Tuple[str, ...]) -> Optional[Tuple[int, float]]:
    if not search_lines: return (0, 1.0)
    search_str = "\n".join(search_lines)
    best_ratio = 0.0
    best_idx = -1
    search_len = len(search_lines)
    # FIX: Slide a window of the EXACT same size to prevent ratio dilution
    for i in range(len(source_lines) - search_len + 1):
        window = source_lines[i : i + search_len]
        m = difflib.SequenceMatcher(None, "\n".join(window), search_str, autojunk=False)
        ratio = m.ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_idx = i
    if best_ratio >= FUZZY_SIMILARITY_THRESHOLD:
        return (best_idx, best_ratio)
    return None

def apply_patches(source_content: str, blocks: List[PatchBlock]) -> PatchResult:
    source_lines = source_content.splitlines(keepends=False)
    total_lines_changed = 0
    resolved_blocks = []
    for block in blocks:
        lines_changed = _calculate_lines_changed(block.search_lines, block.replace_lines)
        total_lines_changed += lines_changed
        if total_lines_changed > MAX_LINES_CHANGED_PER_PATCH_SET:
            raise ScopeBudgetExceededError(f"Scope Budget Exceeded: {total_lines_changed} lines changed > {MAX_LINES_CHANGED_PER_PATCH_SET} limit.")
        start_idx = _find_exact_match(source_lines, block.search_lines)
        is_fuzzy = False
        ratio = 1.0
        if start_idx is None:
            fuzzy_result = _find_fuzzy_match(source_lines, block.search_lines)
            if fuzzy_result:
                start_idx, ratio = fuzzy_result
                is_fuzzy = True
            else:
                raise PatchApplyError(f"SEARCH block not found (Exact & Fuzzy < {FUZZY_SIMILARITY_THRESHOLD}).")
        resolved_blocks.append(PatchBlock(
            search_lines=block.search_lines, replace_lines=block.replace_lines,
            original_start_line=start_idx, is_fuzzy_match=is_fuzzy, similarity_ratio=ratio
        ))
    resolved_blocks.sort(key=lambda b: b.original_start_line)
    for i in range(len(resolved_blocks) - 1):
        curr = resolved_blocks[i]
        next_b = resolved_blocks[i+1]
        curr_end = curr.original_start_line + len(curr.search_lines)
        if curr_end > next_b.original_start_line:
            raise PatchApplyError(f"Overlapping patches detected: Block at line {curr.original_start_line+1} ends at {curr_end}, overlaps next block at {next_b.original_start_line+1}.")
    working_lines = list(source_lines)
    resolved_blocks.sort(key=lambda b: b.original_start_line, reverse=True)
    for block in resolved_blocks:
        start = block.original_start_line
        end = start + len(block.search_lines)
        working_lines[start:end] = list(block.replace_lines)
    modified_content = "\n".join(working_lines)
    if source_content.endswith("\n") and not modified_content.endswith("\n"):
        modified_content += "\n"
    return PatchResult(success=True, applied_blocks=len(resolved_blocks), total_lines_changed=total_lines_changed, modified_content=modified_content, blocks=resolved_blocks)

def process_llm_patch(source_content: str, llm_output: str) -> PatchResult:
    try:
        blocks = parse_patch_blocks(llm_output)
        return apply_patches(source_content, blocks)
    except (PatchParseError, PatchApplyError, ScopeBudgetExceededError):
        raise
    except Exception as e:
        raise PatchApplyError(f"Internal Engine Error: {e}") from e

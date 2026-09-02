"""
engine/multi_file_patcher.py
----------------------------
Applies atomic multi-file SEARCH/REPLACE blocks with FUZZY MATCHING.
"""
import re
import difflib
from pathlib import Path
from dataclasses import dataclass

@dataclass
class FilePatch:
    file_path: Path
    search: str
    replace: str

def parse_multi_file_diff(raw_diff: str, root_dir: Path) -> list[FilePatch]:
    patches = []
    # Regex to find blocks
    pattern = re.compile(
        r'<<<<<<<\s+(.*?)\s*\n(.*?)\n=======\n(.*?)\n>>>>>>> REPLACE',
        re.DOTALL
    )
    for match in pattern.finditer(raw_diff):
        rel_path = match.group(1).strip()
        search = match.group(2)
        replace = match.group(3)
        patches.append(FilePatch(root_dir / rel_path, search, replace))
    return patches

def apply_multi_file_patches(patches: list[FilePatch]) -> dict[Path, str]:
    modified_files = {}
    
    for patch in patches:
        if not patch.file_path.exists():
            raise ValueError(f"File not found: {patch.file_path}")
            
        original = patch.file_path.read_text()
        new_content = original
        
        # 1. Try Exact Match first
        if patch.search in original:
            new_content = original.replace(patch.search, patch.replace, 1)
        else:
            # 2. FUZZY MATCH FALLBACK (Line-based sliding window)
            orig_lines = original.splitlines(keepends=True)
            search_lines = patch.search.splitlines(keepends=True)
            
            if not search_lines: 
                raise ValueError(f"Empty search block for {patch.file_path}")
                
            best_score = 0.0
            best_start = -1
            window_size = len(search_lines)
            
            for i in range(len(orig_lines) - window_size + 1):
                chunk = "".join(orig_lines[i:i+window_size])
                score = difflib.SequenceMatcher(None, chunk, patch.search).ratio()
                if score > best_score:
                    best_score = score
                    best_start = i
                    
            if best_score > 0.80: # 80% similarity threshold
                # Apply fuzzy replace
                replace_text = patch.replace
                if not replace_text.endswith("\n"): replace_text += "\n"
                new_lines = orig_lines[:best_start] + [replace_text] + orig_lines[best_start+window_size:]
                new_content = "".join(new_lines)
            else:
                raise ValueError(f"Search block not found (Exact & Fuzzy < 0.80) in {patch.file_path}")
                
        modified_files[patch.file_path] = new_content
        
    return modified_files

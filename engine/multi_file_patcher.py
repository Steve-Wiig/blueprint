"""
engine/multi_file_patcher.py
----------------------------
Applies atomic multi-file SEARCH/REPLACE blocks.
Format:
<<<<<<< path/to/file.py
[search]
=======
[replace]
>>>>>>> REPLACE
"""
import re
from pathlib import Path
from dataclasses import dataclass

@dataclass
class FilePatch:
    file_path: Path
    search: str
    replace: str

def parse_multi_file_diff(raw_diff: str, root_dir: Path) -> list[FilePatch]:
    """Parses a multi-file diff string into a list of FilePatch objects."""
    patches = []
    # Regex to find blocks: <<<<<<< path \n search \n ======= \n replace \n >>>>>>>
    pattern = re.compile(
        r'<<<<<<<\s+(.*?)\s*\n(.*?)\n=======\n(.*?)\n>>>>>>> REPLACE',
        re.DOTALL
    )
    
    for match in pattern.finditer(raw_diff):
        rel_path = match.group(1).strip()
        search = match.group(2)
        replace = match.group(3)
        
        # Normalize path
        file_path = root_dir / rel_path
        patches.append(FilePatch(file_path, search, replace))
        
    return patches

def apply_multi_file_patches(patches: list[FilePatch]) -> dict[Path, str]:
    """Applies patches atomically. Returns dict of {path: new_content}.
    Raises ValueError if any search block is not found exactly."""
    
    modified_files = {}
    
    # 1. Validate all patches first (Read-Only pass)
    for patch in patches:
        if not patch.file_path.exists():
            raise ValueError(f"File not found: {patch.file_path}")
            
        original = patch.file_path.read_text()
        if patch.search not in original:
            raise ValueError(f"Search block not found in {patch.file_path}")
            
        # Calculate new content
        new_content = original.replace(patch.search, patch.replace, 1)
        modified_files[patch.file_path] = new_content
        
    # 2. If all valid, write them all (Atomic Write pass)
    # We don't write to disk here, we return the dict so the caller can backup/commit
    return modified_files

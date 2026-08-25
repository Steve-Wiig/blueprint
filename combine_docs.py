#!/usr/bin/env python3
"""Combine all docs/*.md into a master bundle for review."""

from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent
DOCS_DIR = ROOT / "docs"
REVIEW_DIR = ROOT / "overnight" / "reviews"
TEST_OUTPUT = REVIEW_DIR / "MASTER_DOCUMENTATION_BUNDLE_TEST.md"
FINAL_OUTPUT = DOCS_DIR / "MASTER_DOCUMENTATION_BUNDLE.md"

DOC_ORDER = [
    ("Architecture", "ARCHITECTURE.md"),
    ("Operations Runbook", "OPERATIONS_RUNBOOK.md"),
    ("Deployment Runbook", "deployment_runbook.md"),
    ("Lab Setup Guide", "LAB_SETUP_GUIDE.md"),
    ("Operator Manual", "operator_manual.md"),
    ("Overnight Pipeline (v11.9)", "OVERNIGHT_PIPELINE.md"),
]

def combine():
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    
    if not DOCS_DIR.exists():
        print(f"❌ {DOCS_DIR} not found")
        return
    
    sections = []
    total_lines = 0
    found_count = 0
    
    # Header
    header = f"""# LOCAL-SOC-SLM Master Documentation Bundle (TEST COPY)

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**Source:** v11.9.0 Blueprint  
**Status:** REVIEW COPY — not yet promoted to final  
**Total Documents:** {len(DOC_ORDER)}  
**Combined Line Count:** (calculated below)

---

This document combines all operational documentation for the LOCAL-SOC-SLM platform into a single reference bundle optimized for large-context LLM consumption.

"""
    sections.append(header)
    
    # Process each doc
    for title, filename in DOC_ORDER:
        doc_path = DOCS_DIR / filename
        if not doc_path.exists():
            print(f"⚠️  Missing: {filename}")
            continue
        
        content = doc_path.read_text()
        line_count = len(content.splitlines())
        total_lines += line_count
        found_count += 1
        
        section = f"""
---

# {title}

*Source: `docs/{filename}` ({line_count} lines)*

{content}

"""
        sections.append(section)
        print(f"✅ Added: {filename} ({line_count} lines)")
    
    if found_count == 0:
        print("❌ No docs found to combine")
        return
    
    # Update header with actual line count
    combined = "".join(sections)
    combined = combined.replace(
        "**Combined Line Count:** (calculated below)",
        f"**Combined Line Count:** {total_lines} lines"
    )
    combined = combined.replace(
        f"**Total Documents:** {len(DOC_ORDER)}",
        f"**Total Documents:** {found_count}/{len(DOC_ORDER)}"
    )
    
    # Write test output
    TEST_OUTPUT.write_text(combined)
    print(f"\n✅ Test bundle written: {TEST_OUTPUT}")
    print(f"   Total: {total_lines} lines ({len(combined):,} characters)")
    print(f"\n📋 To review:")
    print(f"   cat {TEST_OUTPUT.relative_to(ROOT)} | less")
    print(f"   # or")
    print(f"   head -100 {TEST_OUTPUT.relative_to(ROOT)}")
    print(f"\n📋 To promote to final after review:")
    print(f"   python3 combine_docs.py --promote")

def promote():
    if not TEST_OUTPUT.exists():
        print(f"❌ Test bundle not found at {TEST_OUTPUT}")
        print(f"   Run 'python3 combine_docs.py' first")
        return
    
    # Remove TEST COPY marker
    content = TEST_OUTPUT.read_text()
    content = content.replace("(TEST COPY)", "")
    content = content.replace("**Status:** REVIEW COPY — not yet promoted to final", 
                             "**Status:** FINAL — promoted after review")
    
    FINAL_OUTPUT.write_text(content)
    print(f"✅ Promoted to final: {FINAL_OUTPUT}")
    print(f"   Lines: {len(content.splitlines())}")
    print(f"   Size: {len(content):,} characters")

if __name__ == "__main__":
    import sys
    if "--promote" in sys.argv:
        promote()
    else:
        combine()

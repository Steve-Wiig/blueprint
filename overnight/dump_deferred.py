#!/usr/bin/env python3
"""List or dump deferred fixes for manual LLM triage.

Usage:
  python3 overnight/dump_deferred.py                  # list all deferred, grouped by file
  python3 overnight/dump_deferred.py <file_path> <n>  # dump full context for manual fix
"""
import json, sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
DEFERRED = ROOT / "overnight" / "fix_backlog_deferred.json"

def load():
    if not DEFERRED.exists():
        return []
    try:
        return json.loads(DEFERRED.read_text())
    except Exception:
        return []

def list_all(deferred):
    by_file = defaultdict(list)
    for item in deferred:
        by_file[item["file"]].append(item)
    print(f"{len(deferred)} deferred fixes across {len(by_file)} files:\n")
    for f in sorted(by_file):
        items = by_file[f]
        print(f"📄 {f}  ({len(items)} deferred)")
        for i, item in enumerate(items):
            desc = item["issue"].get("description", "")[:85]
            print(f"   [{i}] (x{item.get('attempts','?')}) {desc}")
        print()
    print("Dump one with: python3 overnight/dump_deferred.py <file_path> <index>")

def dump_one(deferred, target_file, idx):
    matches = [it for it in deferred if it["file"] == target_file]
    if idx >= len(matches):
        print(f"❌ Index {idx} out of range ({len(matches)} deferred for that file)")
        return
    item = matches[idx]
    fpath = ROOT / item["file"]
    content = fpath.read_text() if fpath.exists() else "(file missing)"
    issue = item["issue"]
    print("=" * 60)
    print(f"DEFERRED FIX — manual triage")
    print(f"File:     {item['file']}  ({len(content.splitlines())} lines, {len(content)} chars)")
    print(f"Attempts: {item.get('attempts','?')} — {item.get('deferred_reason','')}")
    print(f"Category: {issue.get('category','')} | Severity: {issue.get('severity','')}")
    print("=" * 60)
    print(f"\nISSUE:\n{issue.get('description','')}\n")
    print(f"SUGGESTED FIX:\n{issue.get('suggestion','')}\n")
    print(f"CURRENT FILE CONTENT:\n{content}")
    print("=" * 60)

def main():
    deferred = load()
    if not deferred:
        print("No deferred fixes yet (run the drain first).")
        return
    if len(sys.argv) == 1:
        list_all(deferred)
    elif len(sys.argv) == 3:
        dump_one(deferred, sys.argv[1], int(sys.argv[2]))
    else:
        print("Usage: dump_deferred.py [<file_path> <index>]")

if __name__ == "__main__":
    main()

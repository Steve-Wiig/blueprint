#!/usr/bin/env python3
"""
Deterministic parser for overnight drain logs.
Extracts structured metrics: failure counts, most-failed files, deferred item analysis.
Outputs JSON for LLM interpretation or direct analysis.

Usage:
    python3 tools/analyze_drain_log.py overnight/run_20260826_014103.log
    python3 tools/analyze_drain_log.py overnight/run_*.log --output analysis.json
"""
import re
import json
import argparse
import sys
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime
from typing import Any, Dict, List, Optional, Union


def parse_log_file(log_path: Path) -> Dict[str, Any]:
    """
    Parse a single drain log file and extract structured metrics.

    Args:
        log_path: Path to the overnight drain log file.

    Returns:
        Dictionary with the following structure:
        {
            "file": str,                    # Path to the log file
            "run_date": str | None,         # Extracted run date (e.g., "Mon Aug 26 01:41:03 UTC 2026")
            "summary": {
                "total_attempts": int,      # Total fix attempts (successful + rejected)
                "successful": int,          # Number of fixes committed
                "rejected": int,            # Number of rejected fixes
                "deferred": int,            # Number of deferred items
                "success_rate": float       # successful / total_attempts (0.0 if no attempts)
            },
            "failure_categories": dict[str, int],  # Category -> count, e.g.:
                # "unterminated_triple_quoted": 5,
                # "unterminated_string": 3,
                # "unclosed_parenthesis": 2,
                # "fix_too_short": 1,
                # "invalid_python": 4,
                # "tests_failed": 2,
                # "other_rejection": 1
            "file_failures": dict[str, int],       # File path -> failure count (top 10)
            "deferred_items": list[dict],          # Each: {"attempts": int, "description": str}
            "passes": list[dict]                   # Each: {"pass_number": int, "remaining": int, "applied": int}
        }

    Example output:
        {
            "file": "overnight/run_20260826_014103.log",
            "run_date": "Mon Aug 26 01:41:03 UTC 2026",
            "summary": {
                "total_attempts": 42,
                "successful": 28,
                "rejected": 12,
                "deferred": 2,
                "success_rate": 0.6666666666666666
            },
            "failure_categories": {
                "unterminated_triple_quoted": 5,
                "tests_failed": 3,
                "invalid_python": 2,
                "other_rejection": 2
            },
            "file_failures": {
                "src/utils/parser.py": 4,
                "tests/test_parser.py": 3
            },
            "deferred_items": [
                {"attempts": 3, "description": "Fix type annotation in complex generic..."},
                {"attempts": 5, "description": "Refactor circular import in..."}
            ],
            "passes": [
                {"pass_number": 1, "remaining": 42, "applied": 15},
                {"pass_number": 2, "remaining": 27, "applied": 8},
                {"pass_number": 3, "remaining": 19, "applied": 5}
            ]
        }
    """
    content: str = log_path.read_text(encoding="utf-8")
    lines: List[str] = content.splitlines()
    
    metrics: Dict[str, Any] = {
        "file": str(log_path),
        "run_date": None,
        "summary": {
            "total_attempts": 0,
            "successful": 0,
            "rejected": 0,
            "deferred": 0,
            "success_rate": 0.0
        },
        "failure_categories": Counter(),
        "file_failures": Counter(),
        "deferred_items": [],
        "passes": []
    }
    
    # Extract run date
    date_match = re.search(r"Overnight run started: (\w+ \w+ \d+ [\d:]+ \w+ \d+)", content)
    if date_match:
        metrics["run_date"] = date_match.group(1)
    
    # Parse line by line
    current_pass: Optional[int] = None
    current_file: Optional[str] = None
    
    for line in lines:
        # Track passes
        pass_match = re.search(r"\[Pass (\d+)\] (\d+) fixes remaining", line)
        if pass_match:
            current_pass = int(pass_match.group(1))
            metrics["passes"].append({
                "pass_number": current_pass,
                "remaining": int(pass_match.group(2)),
                "applied": 0
            })
        
        # Track successful fixes
        if "✅ Fix committed" in line:
            metrics["summary"]["successful"] += 1
            metrics["summary"]["total_attempts"] += 1
            if metrics["passes"]:
                metrics["passes"][-1]["applied"] += 1
        
        # Track file being processed - IMPROVED REGEX
        # Look for patterns like "Generating fix: <description> in <file.py>"
        # or "Generating fix: <description>" followed by file context
        file_match = re.search(r"📝 Generating fix: .*? in (\S+\.py)", line)
        if not file_match:
            # Alternative: look for file path in the issue description
            file_match = re.search(r"Generating fix: .*? (\S+\.py):", line)
        if file_match:
            current_file = file_match.group(1)
        
        # Track rejections
        if "— rejecting" in line:
            metrics["summary"]["rejected"] += 1
            metrics["summary"]["total_attempts"] += 1
            
            # Categorize the rejection
            if "unterminated triple-quoted string" in line:
                metrics["failure_categories"]["unterminated_triple_quoted"] += 1
            elif "unterminated string literal" in line:
                metrics["failure_categories"]["unterminated_string"] += 1
            elif "was never closed" in line:
                metrics["failure_categories"]["unclosed_parenthesis"] += 1
            elif "Fix suspiciously short" in line:
                metrics["failure_categories"]["fix_too_short"] += 1
            elif "not valid Python" in line:
                metrics["failure_categories"]["invalid_python"] += 1
            else:
                metrics["failure_categories"]["other_rejection"] += 1
            
            # Track which file failed
            if current_file:
                metrics["file_failures"][current_file] += 1
        
        # Track test failures
        if "Tests failed — reverting" in line:
            metrics["summary"]["rejected"] += 1
            metrics["summary"]["total_attempts"] += 1
            metrics["failure_categories"]["tests_failed"] += 1
            if current_file:
                metrics["file_failures"][current_file] += 1
        
        # Track deferred items
        if "🗃️  Deferred after" in line:
            metrics["summary"]["deferred"] += 1
            deferred_match = re.search(r"Deferred after (\d+) attempts: (.+)", line)
            if deferred_match:
                metrics["deferred_items"].append({
                    "attempts": int(deferred_match.group(1)),
                    "description": deferred_match.group(2)[:200]  # Truncate long descriptions
                })
    
    # Calculate success rate
    if metrics["summary"]["total_attempts"] > 0:
        metrics["summary"]["success_rate"] = (
            float(metrics["summary"]["successful"]) / metrics["summary"]["total_attempts"]
        )
    
    # Convert Counters to dicts for JSON serialization
    metrics["failure_categories"] = dict(metrics["failure_categories"].most_common())
    metrics["file_failures"] = dict(metrics["file_failures"].most_common(10))
    
    return metrics


def analyze_multiple_logs(log_paths: List[Path]) -> Dict[str, Any]:
    """Analyze multiple log files and aggregate metrics."""
    all_metrics: List[Dict[str, Any]] = []
    aggregated: Dict[str, Any] = {
        "total_runs": len(log_paths),
        "combined_summary": {
            "total_attempts": 0,
            "successful": 0,
            "rejected": 0,
            "deferred": 0,
            "success_rate": 0.0
        },
        "combined_failures": Counter(),
        "combined_file_failures": Counter(),
        "runs": []
    }
    
    for log_path in log_paths:
        metrics = parse_log_file(log_path)
        all_metrics.append(metrics)
        
        # Aggregate
        aggregated["combined_summary"]["total_attempts"] += metrics["summary"]["total_attempts"]
        aggregated["combined_summary"]["successful"] += metrics["summary"]["successful"]
        aggregated["combined_summary"]["rejected"] += metrics["summary"]["rejected"]
        aggregated["combined_summary"]["deferred"] += metrics["summary"]["deferred"]
        
        for cat, count in metrics["failure_categories"].items():
            aggregated["combined_failures"][cat] += count
        
        for file, count in metrics["file_failures"].items():
            aggregated["combined_file_failures"][file] += count
    
    # Calculate combined success rate
    if aggregated["combined_summary"]["total_attempts"] > 0:
        aggregated["combined_summary"]["success_rate"] = (
            float(aggregated["combined_summary"]["successful"]) / 
            aggregated["combined_summary"]["total_attempts"]
        )
    
    aggregated["combined_failures"] = dict(aggregated["combined_failures"].most_common())
    aggregated["combined_file_failures"] = dict(aggregated["combined_file_failures"].most_common(10))
    aggregated["runs"] = all_metrics
    
    return aggregated


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deterministic parser for overnight drain logs"
    )
    parser.add_argument(
        "log_files",
        nargs="+",
        help="Path(s) to log file(s) to analyze"
    )
    parser.add_argument(
        "--output",
        help="Optional: save JSON output to file"
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output"
    )
    args = parser.parse_args()
    
    # Resolve glob patterns
    log_paths: List[Path] = []
    for pattern in args.log_files:
        if "*" in pattern:
            log_paths.extend(sorted(Path(".").glob(pattern)))
        else:
            log_paths.append(Path(pattern))
    
    # Filter to existing files
    log_paths = [p for p in log_paths if p.exists()]
    
    if not log_paths:
        print("❌ No log files found")
        return
    
    print(f"📊 Analyzing {len(log_paths)} log file(s)...\n")
    
    # Analyze
    if len(log_paths) == 1:
        result: Dict[str, Any] = parse_log_file(log_paths[0])
    else:
        result = analyze_multiple_logs(log_paths)
    
    # Output
    indent: Optional[int] = 2 if args.pretty else None
    json_output: str = json.dumps(result, indent=indent, default=str)
    
    if args.output:
        Path(args.output).write_text(json_output, encoding="utf-8")
        print(f"✅ Analysis saved to {args.output}")
    else:
        print(json_output)
    
    # Print summary to stderr for quick review
    print("\n" + "="*70, file=sys.stderr)
    print("📈 SUMMARY", file=sys.stderr)
    print("="*70, file=sys.stderr)
    
    if len(log_paths) == 1:
        s = result["summary"]
        print(f"Total attempts: {s['total_attempts']}", file=sys.stderr)
        print(f"Successful:     {s['successful']}", file=sys.stderr)
        print(f"Rejected:       {s['rejected']}", file=sys.stderr)
        print(f"Deferred:       {s['deferred']}", file=sys.stderr)
        print(f"Success rate:   {s['success_rate']:.1%}", file=sys.stderr)
        
        print(f"\n🔥 Top failing files:", file=sys.stderr)
        for file, count in result["file_failures"].items():
            print(f"  {file}: {count} failures", file=sys.stderr)
    else:
        s = result["combined_summary"]
        print(f"Total runs:     {result['total_runs']}", file=sys.stderr)
        print(f"Total attempts: {s['total_attempts']}", file=sys.stderr)
        print(f"Successful:     {s['successful']}", file=sys.stderr)
        print(f"Rejected:       {s['rejected']}", file=sys.stderr)
        print(f"Deferred:       {s['deferred']}", file=sys.stderr)
        print(f"Success rate:   {s['success_rate']:.1%}", file=sys.stderr)
        
        print(f"\n🔥 Top failing files (combined):", file=sys.stderr)
        for file, count in result["combined_file_failures"].items():
            print(f"  {file}: {count} failures", file=sys.stderr)


if __name__ == "__main__":
    main()
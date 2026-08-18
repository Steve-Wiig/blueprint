#!/usr/bin/env python3
"""
Bulk read-only audit for LOCAL-SOC-SLM Blueprint v11.6.0.
Performs comprehensive validation without modifying any files.
"""
import ast, os, sys, json, re, subprocess, importlib.util
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

BLUEPRINT_ROOT = Path("/home/swiig/Documents/blueprint")

class AuditReport:
    def __init__(self):
        self.sections = []
        self.total_checks = 0
        self.passed = 0
        self.warnings = 0
        self.failed = 0
    
    def section(self, title):
        self.sections.append({"title": title, "items": []})
        return self.sections[-1]
    
    def add(self, status, message, detail=""):
        section = self.sections[-1]
        section["items"].append({"status": status, "message": message, "detail": detail})
        self.total_checks += 1
        if status == "PASS": self.passed += 1
        elif status == "WARN": self.warnings += 1
        elif status == "FAIL": self.failed += 1
    
    def print_report(self):
        print("\n" + "="*70)
        print("BLUEPRINT v11.6.0 BULK AUDIT REPORT")
        print("="*70)
        
        for section in self.sections:
            print(f"\n## {section['title']}")
            for item in section["items"]:
                icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}.get(item["status"], "  ")
                print(f"  {icon} {item['message']}")
                if item["detail"]:
                    for line in item["detail"].split("\n")[:3]:
                        print(f"      {line}")
        
        print("\n" + "="*70)
        print(f"SUMMARY: {self.passed} passed, {self.warnings} warnings, {self.failed} failed ({self.total_checks} total)")
        print("="*70)

def check_python_syntax(filepath):
    """Check if a Python file has valid syntax."""
    try:
        with open(filepath, 'r', errors='replace') as f:
            ast.parse(f.read())
        return "PASS", "Valid syntax"
    except SyntaxError as e:
        return "FAIL", f"Syntax error: {e}"

def check_imports(filepath):
    """Check if all imports in a file can be resolved."""
    try:
        with open(filepath, 'r', errors='replace') as f:
            tree = ast.parse(f.read())
        
        issues = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    try:
                        spec = importlib.util.find_spec(alias.name.split('.')[0])
                        if spec is None:
                            issues.append(f"Cannot find module: {alias.name}")
                    except: pass
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    try:
                        spec = importlib.util.find_spec(node.module.split('.')[0])
                        if spec is None:
                            issues.append(f"Cannot find module: {node.module}")
                    except: pass
        
        if issues:
            return "WARN", f"Unresolved imports", "\n".join(issues[:3])
        return "PASS", "All imports resolvable"
    except:
        return "WARN", "Could not parse imports"

def check_exit_codes(filepath):
    """Check if exit codes are consistent."""
    try:
        with open(filepath, 'r', errors='replace') as f:
            content = f.read()
        
        exit_patterns = re.findall(r'(sys\.exit|exit)\((\d+)\)', content)
        codes = {int(code) for _, code in exit_patterns}
        
        if not codes:
            return "WARN", "No explicit exit codes found"
        
        if codes <= {0, 1, 2, 3}:
            return "PASS", f"Exit codes: {sorted(codes)}"
        else:
            return "WARN", f"Non-standard exit codes: {sorted(codes)}"
    except:
        return "WARN", "Could not check exit codes"

def check_dry_run(filepath):
    """Check if a tool has --dry-run support."""
    try:
        with open(filepath, 'r', errors='replace') as f:
            content = f.read()
        
        if "dry-run" in content or "dry_run" in content:
            return "PASS", "Has --dry-run support"
        return "WARN", "No --dry-run flag found"
    except:
        return "WARN", "Could not check dry-run"

def check_yaml_syntax(filepath):
    """Check if a YAML file is valid."""
    try:
        import yaml
        with open(filepath, 'r', errors='replace') as f:
            yaml.safe_load(f)
        return "PASS", "Valid YAML"
    except ImportError:
        return "WARN", "PyYAML not installed"
    except Exception as e:
        return "FAIL", f"YAML error: {e}"

def check_sql_syntax(filepath):
    """Basic SQL syntax check (looks for common issues)."""
    try:
        with open(filepath, 'r', errors='replace') as f:
            content = f.read()
        
        # Check for common SQL patterns
        if "CREATE TABLE" in content or "CREATE INDEX" in content:
            if ";" not in content:
                return "WARN", "No semicolons found (may be incomplete)"
            return "PASS", "Basic SQL structure valid"
        return "WARN", "No CREATE statements found"
    except:
        return "WARN", "Could not parse SQL"

def check_file_stats(filepath):
    """Get file statistics."""
    try:
        with open(filepath, 'r', errors='replace') as f:
            lines = f.readlines()
        
        total_lines = len(lines)
        code_lines = len([l for l in lines if l.strip() and not l.strip().startswith('#')])
        comment_lines = len([l for l in lines if l.strip().startswith('#')])
        
        return "PASS", f"{total_lines} lines ({code_lines} code, {comment_lines} comments)"
    except:
        return "WARN", "Could not read file"

def check_blueprint_completeness():
    """Check if all referenced files exist."""
    manifest_path = BLUEPRINT_ROOT / "_manifest.md"
    if not manifest_path.exists():
        return "WARN", "No _manifest.md found"
    
    with open(manifest_path, 'r') as f:
        content = f.read()
    
    # Extract file paths from manifest (simple heuristic)
    referenced = set(re.findall(r'[`\[](/?[a-zA-Z0-9_./\-]+\.(?:py|sql|yaml|md))', content))
    
    missing = []
    for path in referenced:
        full_path = BLUEPRINT_ROOT / path.lstrip('/')
        if not full_path.exists():
            missing.append(path)
    
    if missing:
        return "WARN", f"{len(missing)} referenced files missing", "\n".join(missing[:5])
    return "PASS", f"All {len(referenced)} referenced files exist"

def main():
    report = AuditReport()
    
    # Section 1: File Statistics
    section = report.section("FILE STATISTICS")
    py_files = list(BLUEPRINT_ROOT.rglob("*.py"))
    py_files = [f for f in py_files if "overnight" not in str(f) and "__pycache__" not in str(f)]
    
    sql_files = list(BLUEPRINT_ROOT.rglob("*.sql"))
    yaml_files = list(BLUEPRINT_ROOT.rglob("*.yaml"))
    md_files = list(BLUEPRINT_ROOT.rglob("*.md"))
    
    report.add("PASS", f"Python files: {len(py_files)}")
    report.add("PASS", f"SQL files: {len(sql_files)}")
    report.add("PASS", f"YAML files: {len(yaml_files)}")
    report.add("PASS", f"Markdown files: {len(md_files)}")
    
    # Section 2: Python Syntax Validation
    section = report.section("PYTHON SYNTAX VALIDATION")
    for filepath in py_files:
        status, detail = check_python_syntax(filepath)
        rel_path = filepath.relative_to(BLUEPRINT_ROOT)
        report.add(status, f"{rel_path}", detail)
    
    # Section 3: Import Resolution
    section = report.section("IMPORT RESOLUTION")
    for filepath in py_files:
        status, msg, detail = check_imports(filepath)[0], check_imports(filepath)[1], ""
        if len(check_imports(filepath)) == 3:
            detail = check_imports(filepath)[2]
        rel_path = filepath.relative_to(BLUEPRINT_ROOT)
        report.add(status, f"{rel_path}", detail)
    
    # Section 4: Exit Code Consistency
    section = report.section("EXIT CODE CONSISTENCY")
    for filepath in py_files:
        status, msg = check_exit_codes(filepath)
        rel_path = filepath.relative_to(BLUEPRINT_ROOT)
        report.add(status, f"{rel_path}", msg)
    
    # Section 5: Dry-Run Support
    section = report.section("DRY-RUN SUPPORT (tools/)")
    tool_files = [f for f in py_files if "tools/" in str(f)]
    for filepath in tool_files:
        status, msg = check_dry_run(filepath)
        rel_path = filepath.relative_to(BLUEPRINT_ROOT)
        report.add(status, f"{rel_path}", msg)
    
    # Section 6: YAML Validation
    section = report.section("YAML VALIDATION")
    for filepath in yaml_files:
        status, msg = check_yaml_syntax(filepath)
        rel_path = filepath.relative_to(BLUEPRINT_ROOT)
        report.add(status, f"{rel_path}", msg)
    
    # Section 7: SQL Validation
    section = report.section("SQL VALIDATION")
    for filepath in sql_files:
        status, msg = check_sql_syntax(filepath)
        rel_path = filepath.relative_to(BLUEPRINT_ROOT)
        report.add(status, f"{rel_path}", msg)
    
    # Section 8: File Size Statistics
    section = report.section("FILE SIZE ANALYSIS")
    for filepath in py_files[:10]:  # Just show first 10
        status, msg = check_file_stats(filepath)
        rel_path = filepath.relative_to(BLUEPRINT_ROOT)
        report.add(status, f"{rel_path}", msg)
    
    # Section 9: Blueprint Completeness
    section = report.section("BLUEPRINT COMPLETENESS")
    status, msg = check_blueprint_completeness()
    report.add(status, msg)
    
    # Print report
    report.print_report()
    
    # Exit with appropriate code
    if report.failed > 0:
        sys.exit(1)
    elif report.warnings > 0:
        sys.exit(0)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()

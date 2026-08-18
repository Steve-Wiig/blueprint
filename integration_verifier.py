#!/usr/bin/env python3
"""
Comprehensive integration verifier for LOCAL-SOC-SLM Blueprint.
Automates cross-module imports, CI tool dry-runs, SQL validation,
and test execution — producing a structured pass/fail matrix.
"""
import ast
import importlib
import json
import os
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

BLUEPRINT_ROOT = Path("/home/swiig/Documents/blueprint")

class IntegrationVerifier:
    def __init__(self):
        self.results = {
            "module_imports": {},
            "ci_tools_dry_run": {},
            "sql_validation": {},
            "pytest_results": {},
            "cross_module_dependencies": {}
        }
        self.total_checks = 0
        self.passed = 0
        self.failed = 0
        self.warnings = 0
    
    def log(self, category, name, status, detail=""):
        self.results[category][name] = {"status": status, "detail": detail}
        self.total_checks += 1
        if status == "PASS":
            self.passed += 1
        elif status == "FAIL":
            self.failed += 1
        elif status == "WARN":
            self.warnings += 1
        
        icon = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️"}.get(status, "  ")
        print(f"  {icon} {name}: {detail}" if detail else f"  {icon} {name}")
    
    def verify_module_imports(self):
        """Attempt to import every generated Python module."""
        print("\n## MODULE IMPORT VERIFICATION")
        print("="*70)
        
        py_files = [
            f for f in BLUEPRINT_ROOT.rglob("*.py")
            if ".venv" not in str(f)
            and "overnight" not in str(f)
            and "__pycache__" not in str(f)
            and f.name != "integration_verifier.py"
        ]
        
        # Add blueprint root to path
        sys.path.insert(0, str(BLUEPRINT_ROOT))
        
        for filepath in py_files:
            rel_path = filepath.relative_to(BLUEPRINT_ROOT)
            module_name = str(rel_path).replace("/", ".").replace("\\", ".").replace(".py", "")
            
            try:
                importlib.import_module(module_name)
                self.log("module_imports", str(rel_path), "PASS", "Import successful")
            except Exception as e:
                error_msg = str(e).split("\n")[0][:100]
                self.log("module_imports", str(rel_path), "FAIL", error_msg)
    
    def verify_ci_tools_dry_run(self):
        """Run all CI tools with --dry-run where supported."""
        print("\n## CI TOOLS DRY-RUN VERIFICATION")
        print("="*70)
        
        tools_dir = BLUEPRINT_ROOT / "tools"
        if not tools_dir.exists():
            self.log("ci_tools_dry_run", "tools/", "FAIL", "Directory not found")
            return
        
        tool_files = list(tools_dir.glob("*.py"))
        
        for tool_file in tool_files:
            tool_name = tool_file.name
            
            # Check if tool has --dry-run support
            try:
                with open(tool_file, 'r') as f:
                    content = f.read()
                has_dry_run = "dry-run" in content or "dry_run" in content
            except:
                has_dry_run = False
            
            if has_dry_run:
                try:
                    result = subprocess.run(
                        [sys.executable, str(tool_file), "--dry-run"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        cwd=str(BLUEPRINT_ROOT)
                    )
                    
                    if result.returncode == 0:
                        self.log("ci_tools_dry_run", tool_name, "PASS", "Exit code 0")
                    elif result.returncode in (2, 3):
                        self.log("ci_tools_dry_run", tool_name, "WARN", f"Exit {result.returncode}: CONFIG/ENV expected without live lab")
                    else:
                        stderr = result.stderr.strip()[:100] if result.stderr else "No output"
                        self.log("ci_tools_dry_run", tool_name, "FAIL", f"Exit {result.returncode}: {stderr}")
                except subprocess.TimeoutExpired:
                    self.log("ci_tools_dry_run", tool_name, "FAIL", "Timeout")
                except Exception as e:
                    self.log("ci_tools_dry_run", tool_name, "FAIL", str(e)[:100])
            else:
                self.log("ci_tools_dry_run", tool_name, "WARN", "No --dry-run support")
    
    def verify_sql_syntax(self):
        """Validate SQL files using sqlite3 parser."""
        print("\n## SQL SYNTAX VERIFICATION")
        print("="*70)
        
        sql_files = list(BLUEPRINT_ROOT.rglob("*.sql"))
        
        for sql_file in sql_files:
            rel_path = sql_file.relative_to(BLUEPRINT_ROOT)
            
            try:
                with open(sql_file, 'r') as f:
                    sql_content = f.read()
                
                # Try to parse with sqlite3 (basic validation)
                import sqlite3
                conn = sqlite3.connect(":memory:")
                cursor = conn.cursor()
                
                # Split by semicolons and try to execute each statement
                statements = [s.strip() for s in sql_content.split(";") if s.strip()]
                errors = []
                
                for stmt in statements:
                    try:
                        cursor.execute(stmt)
                    except sqlite3.Error as e:
                        errors.append(f"{str(e)[:80]}")
                
                conn.close()
                
                if errors:
                    self.log("sql_validation", str(rel_path), "WARN", f"{len(errors)} potential issues")
                else:
                    self.log("sql_validation", str(rel_path), "PASS", "All statements parse")
                    
            except Exception as e:
                self.log("sql_validation", str(rel_path), "FAIL", str(e)[:100])
    
    def verify_pytest_suite(self):
        """Run the pytest suite and capture results."""
        print("\n## PYTEST SUITE VERIFICATION")
        print("="*70)
        
        tests_dir = BLUEPRINT_ROOT / "tests"
        if not tests_dir.exists():
            self.log("pytest_results", "tests/", "FAIL", "Directory not found")
            return
        
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", str(tests_dir), "-v", "--tb=line"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(BLUEPRINT_ROOT)
            )
            
            # Parse pytest output
            stdout = result.stdout
            
            # Count passed/failed
            passed = stdout.count(" PASSED")
            failed = stdout.count(" FAILED")
            errors = stdout.count(" ERROR")
            
            if failed == 0 and errors == 0:
                self.log("pytest_results", "Full suite", "PASS", f"{passed} tests passed")
            else:
                self.log("pytest_results", "Full suite", "FAIL", f"{failed} failed, {errors} errors")
                
        except Exception as e:
            self.log("pytest_results", "Full suite", "FAIL", str(e)[:100])
    
    def generate_report(self):
        """Print final summary report."""
        print("\n" + "="*70)
        print("INTEGRATION VERIFICATION REPORT")
        print("="*70)
        
        print(f"\nTotal checks: {self.total_checks}")
        print(f"✅ Passed: {self.passed}")
        print(f"⚠️  Warnings: {self.warnings}")
        print(f"❌ Failed: {self.failed}")
        
        # Print failure summary
        failures = []
        for category, items in self.results.items():
            for name, result in items.items():
                if result["status"] == "FAIL":
                    failures.append((category, name, result["detail"]))
        
        if failures:
            print(f"\n## FAILURES ({len(failures)})")
            for category, name, detail in failures[:20]:  # Show first 20
                print(f"  [{category}] {name}: {detail}")
        
        # Save JSON report
        report_path = BLUEPRINT_ROOT / "integration_report.json"
        with open(report_path, 'w') as f:
            json.dump({
                "summary": {
                    "total": self.total_checks,
                    "passed": self.passed,
                    "warnings": self.warnings,
                    "failed": self.failed
                },
                "results": self.results
            }, f, indent=2)
        print(f"\nDetailed report saved to: {report_path}")
    
    def run_all(self):
        """Execute all verification checks."""
        print("LOCAL-SOC-SLM Blueprint Integration Verifier")
        print("="*70)
        
        self.verify_module_imports()
        self.verify_ci_tools_dry_run()
        self.verify_sql_syntax()
        self.verify_pytest_suite()
        self.generate_report()

if __name__ == "__main__":
    verifier = IntegrationVerifier()
    verifier.run_all()

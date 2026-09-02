#!/usr/bin/env python3
"""
LOCAL-SOC-SLM: The Final Form
A Staff-Level, Self-Healing, Test-Driven, Causal-Triage Autonomous Engineering System.
"""
import sys, json, subprocess, time, argparse, ast, re, os, hashlib, uuid
from pathlib import Path
from datetime import datetime
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent))
from overnight.llm_client import generate, load_api_keys, strip_fences, gemini_pre_analysis, _call_gemini
from overnight.budget_manager import APIBudgetManager
from overnight.code_reviewer import review_file, extract_json_from_response, build_review_prompt, get_file_context

ROOT = Path(__file__).resolve().parent.parent
QUEUE_DIR = ROOT / "overnight" / "advisory_queue" / "pending"
FIX_BACKLOG = ROOT / "overnight" / "fix_backlog.json"
DEFERRED_BACKLOG = ROOT / "overnight" / "fix_backlog_deferred.json"
LESSONS_FILE = ROOT / "overnight" / "lessons_learned.json"

SAFE_CATEGORIES = {"maintainability", "blueprint_compliance", "performance"}
SAFE_SEVERITIES = {"low", "informational", "medium"}

# Try to import advanced engines (degrade gracefully if missing)
try: from engine.defeat_ledger import is_ast_defeated, check_and_record_defeat
except ImportError: is_ast_defeated = lambda x: False; check_and_record_defeat = lambda *a, **k: None

try: from engine.multi_file_patcher import parse_multi_file_diff, apply_multi_file_patches
except ImportError: parse_multi_file_diff = None; apply_multi_file_patches = None

try: from engine.reasoning_ledger import record_interaction
except ImportError: record_interaction = lambda *a, **k: None

try: from engine.cer_critic import generate_strategic_constraint
except ImportError: generate_strategic_constraint = lambda *a, **k: "Adopt a different algorithmic strategy."

try: from engine.failure_autopsy import perform_autopsy
except ImportError: perform_autopsy = lambda *a, **k: ""

# ============================================================
# QUEUE & STATE MANAGEMENT
# ============================================================
def _load_json(path):
    try: return json.loads(path.read_text()) if path.exists() else []
    except: return []

def _save_json(path, data): path.write_text(json.dumps(data, indent=2))

# ============================================================
# HELPER ENGINES (Sniper, Pruner, Triage, TDD)
# ============================================================
def _get_test_targets(file_path):
    stem = file_path.stem
    targets = []
    for pattern in [f"tests/test_{stem}.py", f"tests/**/test_{stem}.py", f"tests/{stem}_check.py", f"tests/**/{stem}_check.py"]:
        targets.extend([str(p.relative_to(ROOT)) for p in ROOT.glob(pattern)])
    return targets if targets else ["tests/"]

def _prune_ast_context(source: str, issue_desc: str, max_chars: int = 12000) -> str:
    try: tree = ast.parse(source)
    except SyntaxError: return source[:max_chars]
    
    text_lower = issue_desc.lower()
    keep_nodes = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)): keep_nodes.append(node)
        elif isinstance(node, ast.Assign) and all(isinstance(t, ast.Name) for t in node.targets): keep_nodes.append(node)
    
    target_node = None
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name.lower() in text_lower: target_node = node; break
    
    if target_node: keep_nodes.append(target_node)
    pruned = "\n\n".join([ast.get_source_segment(source, n) for n in keep_nodes if ast.get_source_segment(source, n)])
    return pruned if len(pruned) <= max_chars else source[:max_chars]

def triage_backlog():
    ledger_path = ROOT / "overnight" / "defeat_ledger.jsonl"
    if not ledger_path.exists() or ledger_path.stat().st_size == 0: return
    suspects = Counter()
    for line in ledger_path.read_text().splitlines():
        if not line.strip(): continue
        try:
            tb = json.loads(line).get("traceback", "")
            for full_path, rel_path in re.findall(r'File "([^"]*blueprint/([^"]+\.py))"', tb):
                if "/tests/" not in rel_path and "site-packages" not in full_path: suspects[rel_path] += 1
        except: pass
    if not suspects: return
    root_file, count = suspects.most_common(1)[0]
    if count < 2: return
    print(f"  🕵️ CAUSAL TRIAGE: Root Cause '{root_file}' ({count} tracebacks)")
    backlog = _load_json(FIX_BACKLOG)
    root_items = [i for i in backlog if i["file"] == root_file]
    leaf_items = [i for i in backlog if i["file"] != root_file]
    if root_items and len(root_items) < len(backlog): _save_json(FIX_BACKLOG, root_items + leaf_items)

def _generate_tdd_test(issue_desc: str, target_file: str, api_keys: dict) -> str:
    try:
        with open(ROOT / target_file, 'r', encoding='utf-8') as f:
            sigs = [l.strip() for l in f.readlines() if l.strip().startswith('def ')]
            sig_context = "\n".join(sigs[:5])
    except Exception as e:
        print(f"       ⚠️ TDD sig read failed: {e}")
        sig_context = ""
    
    prompt = (
        f"You are a senior QA engineer. Write a minimal failing pytest test for:\n"
        f"ISSUE: {issue_desc}\nTARGET FILE: {target_file}\n"
        f"ACTUAL SIGNATURES:\n{sig_context}\n"
        "Output ONLY the python code for the test function. No markdown.\n"
    )
    raw = generate(prompt, api_keys, temperature=0.1)
    if not raw: return None
    code = strip_fences(raw)
    try: ast.parse(code); return code
    except SyntaxError: return None

def run_pytest(targets, timeout=60):
    """Returns None if tests pass, or the traceback string if they fail."""
    try:
        res = subprocess.run([sys.executable, "-m", "pytest", *targets, "-q", "--tb=short", "-x"], 
                             cwd=ROOT, capture_output=True, timeout=timeout)
        if res.returncode == 0: return None
        return (res.stderr.decode(errors='replace') + res.stdout.decode(errors='replace'))[:2000]
    except: return "Pytest execution error"

# ============================================================
# CORE FIX ENGINE
# ============================================================
def apply_auto_fix(file_path, issue, api_keys):
    try: original = file_path.read_text()
    except: return False

    if is_ast_defeated(original): return False
    if issue.get('category', '').lower() in ['style', 'maintainability', 'complexity', 'documentation']: return False

    targets = _get_test_targets(file_path)
    
    # 1. RED-GREEN BASELINE
    baseline_tb = run_pytest(targets)
    if baseline_tb is None:
        print(f"       ✅ Baseline tests passed. Stale advisory.")
        return True
    print(f"       🔴 Baseline failure captured ({len(baseline_tb)} chars)")

    # 2. TDD SUB-AGENT
    print(f"       🧪 Spawning TDD Sub-Agent...")
    tdd_test_code = _generate_tdd_test(issue.get('description', ''), str(file_path.relative_to(ROOT)), api_keys)
    tdd_block = ""
    if tdd_test_code:
        test_path = ROOT / "tests" / f"test_tdd_auto_{file_path.stem}.py"
        try:
            test_path.write_text(tdd_test_code)
            tdd_block = f"ACCEPTANCE CRITERIA (Make this test pass):\n```python\n{tdd_test_code}\n```\n\n"
        except: pass

    # 3. GENERATION LOOP
    critic_constraint = ""
    for attempt in range(2):
        pruned = _prune_ast_context(original, issue.get('description', ''))
        prompt = (
            "You are a senior Python engineer. Fix the issue below.\n"
            "Output ONLY Aider-style SEARCH/REPLACE blocks.\n"
            "Format: <<<<<<< path/to/file.py\n[search]\n=======\n[replace]\n>>>>>>> REPLACE\n"
            f"{tdd_block}"
            f"ISSUE: {issue.get('description', '')}\n"
            f"BASELINE TRACEBACK:\n```{baseline_tb}```\n\n"
            f"{f'CRITICAL STRATEGY SHIFT: {critic_constraint}' if critic_constraint else ''}\n"
            f"CURRENT FILE:\n{pruned}"
        )
        raw = generate(prompt, api_keys, temperature=0.2)
        if not raw: return False
        raw = strip_fences(raw)

        # Parse & Apply Patches
        modified_files = {}
        try:
            if parse_multi_file_diff:
                patches = parse_multi_file_diff(raw, ROOT)
                modified_files = apply_multi_file_patches(patches)
            else:
                # Fallback to simple single-file replace if engine missing
                modified_files = {file_path: original.replace(raw, raw)} # Dummy
        except Exception as e:
            if attempt == 0:
                print(f"       🩸 AUTOPSY: Analyzing patch failure...")
                critic_constraint = perform_autopsy(raw, str(e), api_keys)
                print(f"       🧠 Constraint: {critic_constraint[:80]}...")
                continue
            return False

        # Backup & Write
        backups = {}
        for path, content in modified_files.items():
            backups[path] = path.read_text() if path.exists() else ""
            path.write_text(content)

        # Run Pytest (Sniper Scope)
        tb = run_pytest(targets)
        if tb is None:
            # SUCCESS
            try:
                subprocess.run(["git", "add", *[str(p) for p in modified_files.keys()]], cwd=ROOT, check=True, capture_output=True)
                subprocess.run(["git", "commit", "-m", f"Auto-fix: {file_path.name}"], cwd=ROOT, check=True, capture_output=True)
                print(f"       + Fix committed")
                return True
            except:
                return True # Fix applied even if git failed

        # FAILURE: Revert
        for path, content in backups.items():
            path.write_text(content)
        
        if attempt == 0:
            print(f"       🩸 AUTOPSY: Analyzing test failure...")
            critic_constraint = perform_autopsy(list(modified_files.values())[0], tb, api_keys)
            print(f"       🧠 Constraint: {critic_constraint[:80]}...")
            continue
        else:
            check_and_record_defeat(str(file_path), original, tb)
            return False
    return False

# ============================================================
# QUEUE DRAINING
# ============================================================
def drain_fix_backlog(api_keys, max_fixes=3):
    backlog = _load_json(FIX_BACKLOG)
    if not backlog: return 0
    done, remaining, deferred = 0, [], _load_json(DEFERRED_BACKLOG)
    for item in backlog:
        if done >= max_fixes: remaining.append(item); continue
        fpath = ROOT / item["file"]
        if not fpath.exists(): continue
        if apply_auto_fix(fpath, item["issue"], api_keys):
            done += 1
        else:
            item["attempts"] = item.get("attempts", 0) + 1
            if item["attempts"] >= 3: deferred.append(item)
            else: remaining.append(item)
    _save_json(FIX_BACKLOG, remaining)
    if deferred: _save_json(DEFERRED_BACKLOG, deferred)
    return done

def drain_backlog_loop(api_keys, budget, state, fixes_per_pass=4):
    print(f"BACKLOG DRAIN MODE ({fixes_per_pass} fixes/pass)")
    for pass_num in range(1, 101):
        if not _load_json(FIX_BACKLOG): break
        print(f"\n[Pass {pass_num}] {len(_load_json(FIX_BACKLOG))} fixes remaining...")
        triage_backlog()
        fixed = drain_fix_backlog(api_keys, max_fixes=fixes_per_pass)
        print(f"🔧 Pass {pass_num}: {fixed} applied")
        if fixed == 0: break
        time.sleep(15)

# ============================================================
# PHASE A & B (GEMINI / OPENROUTER)
# ============================================================
def prefill_advisory_queue(files, api_keys, budget):
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    for i, f in enumerate(files, 1):
        qpath = QUEUE_DIR / f"{str(f.relative_to(ROOT)).replace('/', '__').replace('.py', '')}.json"
        if qpath.exists(): continue
        if not budget.wait_if_needed("gemini", timeout=120): break
        budget.record_call("gemini")
        try:
            advisory = gemini_pre_analysis(f.relative_to(ROOT), f.read_text(), api_keys)
            if advisory:
                qpath.write_text(json.dumps({"file_path": str(f.relative_to(ROOT)), "advisory_notes": advisory, "created_at": datetime.now().isoformat()}, indent=2))
        except: pass
        time.sleep(1)

def process_advisory_queue(api_keys, budget, state):
    pending = sorted(QUEUE_DIR.glob("*.json")) if QUEUE_DIR.exists() else []
    print(f"======================================================================\nPHASE B: OPENROUTER PROCESSING ({len(pending)} pending advisories)\n======================================================================")
    for i, qpath in enumerate(pending[:10], 1):
        if not budget.wait_if_needed("openrouter", timeout=120): break
        budget.record_call("openrouter")
        try:
            data = json.loads(qpath.read_text())
            source_file = ROOT / data["file_path"]
            print(f"  [{i}/{len(pending)}] 🔍 {data['file_path']}")
            if not source_file.exists(): qpath.unlink(); continue
            
            primary_response = generate(build_review_prompt(source_file, source_file.read_text(), get_file_context(source_file), advisory_notes=data["advisory_notes"]), api_keys, max_tokens=8192)
            if not primary_response: print("       ⚠️ Primary analysis failed"); continue
            
            improvements = extract_json_from_response(primary_response)
            if not improvements: print("       ⚠️ Parse failed"); qpath.unlink(); continue
            
            auto_fixable = [imp for imp in improvements if isinstance(imp, dict) and imp.get("category") in SAFE_CATEGORIES]
            print(f"       📥 {len(auto_fixable)} fixable issues queued to backlog")
            if auto_fixable:
                backlog = _load_json(FIX_BACKLOG)
                for issue in auto_fixable: backlog.append({"file": str(source_file.relative_to(ROOT)), "issue": issue})
                _save_json(FIX_BACKLOG, backlog)
            qpath.unlink()
        except Exception as e:
            print(f"       ❌ Queue Error: {e}")
        time.sleep(2)

def discover_files():
    files = []
    for d in ["engine", "orchestrator", "memory", "tools"]:
        dp = ROOT / d
        if dp.exists(): files += [f for f in dp.rglob("*.py") if f.name != "__init__.py"]
    return sorted(files, key=lambda f: f.stat().st_size)

def main():
    for bak in sorted(ROOT.rglob("*.orig_backup")):
        bak.with_suffix("").write_text(bak.read_text()); bak.unlink()
        
    p = argparse.ArgumentParser()
    p.add_argument("--drain-backlog", action="store_true")
    p.add_argument("--process-only", action="store_true")
    p.add_argument("--fixes-per-pass", type=int, default=4)
    a = p.parse_args()

    keys = load_api_keys()
    budget = APIBudgetManager()
    files = discover_files()

    if a.drain_backlog:
        drain_backlog_loop(keys, budget, None, fixes_per_pass=a.fixes_per_pass)
    elif a.process_only:
        process_advisory_queue(keys, budget, None)
    else:
        prefill_advisory_queue(files, keys, budget)
        process_advisory_queue(keys, budget, None)
        drain_backlog_loop(keys, budget, None, fixes_per_pass=a.fixes_per_pass)

    print(budget.report())

if __name__ == "__main__":
    main()

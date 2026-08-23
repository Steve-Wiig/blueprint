#!/usr/bin/env python3
"""
Queue-based self-improver with Gemini pre-analysis pipeline.

Architecture:
  Phase A (Gemini, abundant free tier):
    Pre-analyze ALL files → save advisories to disk queue
    
  Phase B (OpenRouter, when available):
    Drain the queue → feed advisories to primary models
    Delete advisory file on success

Directory structure:
  overnight/advisory_queue/
  └── pending/          ← Gemini advisories waiting for OpenRouter
      ├── engine__queue_manager.json
      └── tools__embedding_prefix_check.json
  (files deleted after successful OpenRouter processing)
"""
import sys, json, subprocess, time, argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from overnight.llm_client import (
    generate, load_api_keys, strip_fences,
    gemini_pre_analysis, _call_gemini
)
from overnight.budget_manager import APIBudgetManager
from overnight.code_reviewer import review_file, extract_json_from_response, build_review_prompt, get_file_context, count_lines

ROOT = Path(__file__).resolve().parent.parent
QUEUE_DIR = ROOT / "overnight" / "advisory_queue" / "pending"
STATE_FILE = ROOT / "overnight" / "improver_state.json"

SAFE_CATEGORIES = {"maintainability", "blueprint_compliance", "performance"}
SAFE_SEVERITIES = {"low", "informational", "medium"}


# ============================================================
# STATE & QUEUE MANAGEMENT
# ============================================================
def load_state():
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {"fixes": 0, "reverts": 0}

def save_state(s):
    s["last_run"] = datetime.now().isoformat()
    STATE_FILE.write_text(json.dumps(s, indent=2))

def queue_path_for(file_path):
    """Get the advisory queue file path for a source file."""
    safe_name = str(file_path.relative_to(ROOT)).replace("/", "__").replace(".py", "")
    return QUEUE_DIR / f"{safe_name}.json"

FIX_BACKLOG = ROOT / "overnight" / "fix_backlog.json"

def _load_backlog():
    if FIX_BACKLOG.exists():
        try:
            return json.loads(FIX_BACKLOG.read_text())
        except Exception:
            pass
    return []

def _save_backlog(items):
    FIX_BACKLOG.write_text(json.dumps(items, indent=2))

def drain_fix_backlog(api_keys, max_fixes=3):
    """Apply a few backlog fixes per call so budgets recover between them."""
    backlog = _load_backlog()
    if not backlog:
        return 0
    done = 0
    remaining = []
    for item in backlog:
        if done >= max_fixes:
            remaining.append(item)
            continue
        fpath = ROOT / item["file"]
        if not fpath.exists():
            continue
        if apply_auto_fix(fpath, item["issue"], api_keys):
            done += 1
        else:
            remaining.append(item)  # keep for a later iteration
    _save_backlog(remaining)
    return done

def get_pending_advisories():
    """List all pending advisory files."""
    if not QUEUE_DIR.exists():
        return []
    return sorted(QUEUE_DIR.glob("*.json"))


# ============================================================
# PHASE A: GEMINI PRE-FILL (uses abundant free tier)
# ============================================================
def prefill_advisory_queue(files, api_keys, budget):
    """Use Gemini to pre-analyze all files that don't have pending advisories."""
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'='*70}")
    print(f"PHASE A: GEMINI PRE-FILL ({len(files)} files)")
    print(f"{'='*70}")
    
    filled = 0
    skipped = 0
    
    for i, f in enumerate(files, 1):
        qpath = queue_path_for(f)
        
        # Skip if advisory already exists
        if qpath.exists():
            skipped += 1
            continue
        
        # Check Gemini budget (wait if per-minute limit hit, only break on daily)
        if not budget.wait_if_needed("gemini", timeout=120):
            print(f"  ⏱️  Gemini daily budget exhausted, stopping pre-fill")
            break
        budget.record_call("gemini")
        
        try:
            content = f.read_text()
            advisory = gemini_pre_analysis(f.relative_to(ROOT), content, api_keys)
            
            if advisory:
                qpath.write_text(json.dumps({
                    "file_path": str(f.relative_to(ROOT)),
                    "advisory_notes": advisory,
                    "created_at": datetime.now().isoformat(),
                    "status": "pending"
                }, indent=2))
                filled += 1
                print(f"  [{i}/{len(files)}] ✅ {f.relative_to(ROOT)}")
            else:
                print(f"  [{i}/{len(files)}] ⚠️  {f.relative_to(ROOT)} — empty advisory")
        
        except Exception as e:
            print(f"  [{i}/{len(files)}] ❌ {f.relative_to(ROOT)}: {e}")
        
        time.sleep(1)  # Brief pause between Gemini calls
    
    print(f"\n  Pre-fill complete: {filled} new, {skipped} already queued")
    return filled


# ============================================================
# PHASE B: OPENROUTER PROCESSING (drains the queue)
# ============================================================
def _normalize(x):
    if isinstance(x, dict):
        for key in ("improvements", "issues", "findings", "results"):
            if isinstance(x.get(key), list):
                return [i for i in x[key] if isinstance(i, dict)]
        return [x] if x else []
    if isinstance(x, list):
        return [i for i in x if isinstance(i, dict)]
    return []


def process_advisory_queue(api_keys, budget, state, max_items=50):
    """Process pending advisories through OpenRouter when available."""
    pending = get_pending_advisories()
    
    if not pending:
        print(f"\n  📭 Advisory queue is empty — nothing to process")
        return 0
    
    print(f"\n{'='*70}")
    print(f"PHASE B: OPENROUTER PROCESSING ({len(pending)} pending advisories)")
    print(f"{'='*70}")
    
    processed = 0
    
    for i, qpath in enumerate(pending[:max_items], 1):
        try:
            advisory_data = json.loads(qpath.read_text())
            file_rel_path = advisory_data["file_path"]
            advisory_notes = advisory_data["advisory_notes"]
            source_file = ROOT / file_rel_path
            
            if not source_file.exists():
                print(f"  [{i}] ⚠️  Source file missing: {file_rel_path}, removing advisory")
                qpath.unlink()
                continue
            
            print(f"\n  [{i}/{len(pending)}] 🔍 {file_rel_path}")
            print(f"       Advisory from: {advisory_data.get('created_at', 'unknown')}")
            
            # Check OpenRouter budget (wait if per-minute hit, break on daily)
            if not budget.wait_if_needed("openrouter", timeout=120):
                print(f"  ⏱️  OpenRouter daily budget exhausted, stopping")
                break
            budget.record_call("openrouter")
            
            # Read source and build prompt with advisory context
            content = source_file.read_text()
            context = get_file_context(source_file)
            
            # Try OpenRouter with advisory context
            review_prompt = build_review_prompt(source_file, content, context, advisory_notes=advisory_notes)
            
            primary_response = generate(
                review_prompt, api_keys,
                model_type="code", max_tokens=8192, temperature=0.3
            )
            
            if not primary_response:
                print(f"       ⚠️  OpenRouter still unavailable, advisory stays in queue")
                continue  # Leave in queue for next attempt
            
            print(f"       ✅ Primary analysis responded ({len(primary_response)} chars)")
            
# Extract improvements from primary response
            improvements_raw = extract_json_from_response(primary_response)

            improvements_raw = _normalize(improvements_raw)

            # Parse failed -> Gemini repairs the FORMAT (conversion only, not analysis)
            if not improvements_raw:
                print(f"       🔧 Parse failed — Gemini JSON repair pass...")
                budget.record_call("gemini")
                repair_prompt = (
                    "Convert these code-review notes into a valid JSON array. "
                    'Each element: {"description": str, "category": str, '
                    '"severity": str, "suggestion": str}. '
                    "Output ONLY the JSON array, no prose.\n\n"
                    + primary_response[:12000]
                )
                repaired = _call_gemini(repair_prompt, api_keys["gemini"],
                                        max_tokens=4096, temperature=0.1)
                if repaired:
                    improvements_raw = _normalize(extract_json_from_response(repaired))

            if not improvements_raw:
                print(f"       ⚠️  Could not parse response, advisory stays in queue")
                continue
            
            # Validate with Gemini (Phase 3)
            print(f"       🔍 Gemini validating {len(improvements_raw)} findings...")
            budget.record_call("gemini")
            
            from overnight.code_reviewer import build_validation_prompt
            improvements_json = json.dumps(improvements_raw[:20], indent=2)
            validation_prompt = build_validation_prompt(source_file, content, improvements_json)
            validation_response = _call_gemini(validation_prompt, api_keys["gemini"], max_tokens=4096, temperature=0.1)
            
            if validation_response:
                validation_data = extract_json_from_response(validation_response)
                if validation_data and isinstance(validation_data, dict):
                    genuine = validation_data.get("genuine_issue_count", 0)
                    false_pos = validation_data.get("false_positive_count", 0)
                    quality = validation_data.get("overall_quality_score", 70)
                    print(f"       ✅ Validated: {genuine} genuine, {false_pos} false positives, quality {quality}/100")
            
            # SUCCESS — remove advisory from queue
            qpath.unlink()
            processed += 1
            print(f"       🗑️  Advisory processed and removed from queue")
            
            # Check for auto-fixable issues
            auto_fixable = [
                imp for imp in improvements_raw
                if isinstance(imp, dict)
                and imp.get("category") in SAFE_CATEGORIES
                and imp.get("severity") in SAFE_SEVERITIES
                and imp.get("validated", True)
                and not imp.get("false_positive", False)
            ]
            
            if auto_fixable:
                backlog = _load_backlog()
                for issue in auto_fixable:
                    backlog.append({"file": str(source_file.relative_to(ROOT)), "issue": issue})
                _save_backlog(backlog)
                print(f"       📥 {len(auto_fixable)} fixable issue(s) queued to backlog")
            
            time.sleep(2)
            
        except Exception as e:
            print(f"       ❌ Error processing {qpath.name}: {e}")
            continue
    
    print(f"\n  Processing complete: {processed} advisories processed")
    return processed


def apply_auto_fix(file_path, issue, api_keys):
    """Generate and apply a fix with test gating, crash-safe backup, and
    precise git error handling. Every exit path is deliberate."""
    try:
        original = file_path.read_text()
    except Exception as e:
        print(f"       ❌ Cannot read {file_path.name}: {e}")
        return False

    prompt = (
        "You are a senior Python engineer. Fix the issue below in this file.\n"
        "Return ONLY the complete fixed file content. No markdown fences, "
        "no explanations, no comments about the change.\n"
        "Preserve all unrelated behavior. Keep the module importable without "
        "side effects. Use datetime.now(timezone.utc), never utcnow().\n"
        f"Issue: {issue.get('description', '')}\n"
        f"Category: {issue.get('category', '')}\n"
        f"Suggestion: {issue.get('suggestion', '')}\n\n"
        f"Current file content:\n{original[:12000]}\n"
    )
    print(f"       📝 Generating fix: {issue.get('description', '')[:80]}")
    fix_code = generate(prompt, api_keys, temperature=0.2)
    if not fix_code:
        print(f"       ❌ Fix generation failed")
        return False
    fix_code = strip_fences(fix_code)
    if len(fix_code) < 0.5 * len(original):
        print(f"       ❌ Fix suspiciously short ({len(fix_code)} vs {len(original)} chars) — rejecting")
        return False

    # Backup exists ONLY during the pytest window; a leftover .orig_backup at
    # next startup is proof of a crash mid-test (handled by main() recovery).
    backup = file_path.with_suffix(file_path.suffix + ".orig_backup")
    backup.write_text(original)
    file_path.write_text(fix_code)

    tests_passed = False
    timed_out = False
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=no"],
            cwd=ROOT, capture_output=True, timeout=120,
        )
        tests_passed = result.returncode == 0
    except subprocess.TimeoutExpired:
        timed_out = True  # subprocess.run already killed the hung pytest child

    if not tests_passed:
        file_path.write_text(original)
        backup.unlink(missing_ok=True)
        print(f"       ❌ Tests {'timed out (120s)' if timed_out else 'failed'} — reverting")
        return False

    backup.unlink(missing_ok=True)
    try:
        subprocess.run(["git", "add", str(file_path)], cwd=ROOT, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", f"Auto-fix: {file_path.name}"],
                       cwd=ROOT, check=True, capture_output=True)
        print(f"       ✅ Fix committed")
        return True
    except subprocess.CalledProcessError as e:
        err = (e.stdout or b"") + (e.stderr or b"")
        if b"nothing to commit" in err or b"no changes" in err:
            print(f"       ⚠️  No-op fix (nothing changed) — treated as done")
            return True
        print(f"       ❌ git failed: {err.decode(errors='replace')[:200]}")
        return False
def discover_files():
    """Find all reviewable source files."""
    files = []
    for d in ["engine", "orchestrator", "memory", "tools"]:
        dp = ROOT / d
        if dp.exists():
            files += [f for f in dp.rglob("*.py") if f.name != "__init__.py"]
    files.sort(key=lambda f: f.stat().st_size)
    return files


def main():
    # Crash recovery: a killed run may leave a half-applied fix behind
    for bak in sorted(ROOT.rglob("*.orig_backup")):
        target = bak.with_suffix("")
        target.write_text(bak.read_text())
        bak.unlink()
        print(f"  🩹 Crash recovery: restored {target.name} from backup")

    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--max-iterations", type=int, default=5)
    p.add_argument("--prefill-only", action="store_true", help="Only fill advisory queue with Gemini")
    p.add_argument("--process-only", action="store_true", help="Only process existing advisory queue")
    a = p.parse_args()

    keys = load_api_keys()
    budget = APIBudgetManager()
    state = load_state()
    
    files = discover_files()
    print(f"Found {len(files)} source files")
    print(f"Queue directory: {QUEUE_DIR}")
    
    if a.prefill_only:
        prefill_advisory_queue(files, keys, budget)
    elif a.process_only:
        process_advisory_queue(keys, budget, state)
    else:
        # Full loop: prefill then process, repeat
        for iteration in range(1, a.max_iterations + 1):
            print(f"\n{'#'*70}")
            print(f"ITERATION {iteration}/{a.max_iterations}")
            print(f"{'#'*70}")
            
            # Phase A: Fill queue with Gemini pre-analyses
            prefill_advisory_queue(files, keys, budget)
            
            # Phase B: Process queue with OpenRouter
            processed = process_advisory_queue(keys, budget, state)

            # Phase C: apply a few backlog fixes (budget has recovered)
            fixed = drain_fix_backlog(keys, max_fixes=3)
            print(f"  🔧 Backlog fixes applied this iteration: {fixed}")
            
            # Check if queue is empty and budget allows
            remaining = len(get_pending_advisories())
            if remaining == 0:
                print(f"\n  ✅ Queue fully processed!")
                break
            
            print(f"\n  📊 Queue status: {remaining} advisories still pending")
            
            if not budget.can_proceed("openrouter"):
                print(f"  ⏱️  Budget exhausted, stopping for now")
                break
            
            # Wait before next iteration
            print(f"  ⏳ Waiting 60s before next iteration...")
            time.sleep(60)
    
    save_state(state)
    print(f"\n{budget.report()}")


if __name__ == "__main__":
    main()

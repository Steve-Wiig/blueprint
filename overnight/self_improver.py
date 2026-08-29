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
import sys, json, subprocess, time, argparse, ast
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
BACKLOG_LOCK = ROOT / "overnight" / "backlog.lock"  # Human operator lock

def _load_backlog():
    if FIX_BACKLOG.exists():
        try:
            return json.loads(FIX_BACKLOG.read_text())
        except Exception:
            pass
    return []

def _save_backlog(items):
    FIX_BACKLOG.write_text(json.dumps(items, indent=2))

MAX_FIX_RETRIES = 3
DEFERRED_BACKLOG = ROOT / "overnight" / "fix_backlog_deferred.json"


def _load_deferred():
    if DEFERRED_BACKLOG.exists():
        try:
            return json.loads(DEFERRED_BACKLOG.read_text())
        except Exception:
            pass
    return []


def _save_deferred(items):
    DEFERRED_BACKLOG.write_text(json.dumps(items, indent=2))


def drain_fix_backlog(api_keys, max_fixes=3):
    """Apply backlog fixes with retry tracking. Fixes that fail MAX_FIX_RETRIES
    times are moved to a deferred list instead of being retried forever, so we
    stop burning quota on hopeless fixes (large-file truncation, unfixable tests)."""
    
    # HARDENING: Gracefully skip if human operator has locked the backlog for manual editing
    if BACKLOG_LOCK.exists():
        print("       ⚠️  BACKLOG LOCKED: Human operator is editing. Skipping drain pass to prevent overwrite.")
        return 0
        
    backlog = _load_backlog()
    if not backlog:
        return 0
    done = 0
    remaining = []
    deferred = _load_deferred()
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
            item["attempts"] = item.get("attempts", 0) + 1
            if item["attempts"] >= MAX_FIX_RETRIES:
                item["deferred_reason"] = f"failed {item['attempts']} attempts"
                deferred.append(item)
                print(f"       🗃️  Deferred after {item['attempts']} attempts: {item['issue'].get('description', '')[:60]}")
            else:
                remaining.append(item)
    _save_backlog(remaining)
    if deferred:
        _save_deferred(deferred)
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


_REASONING_MARKERS = (
    "here's a thinking process", "here is a thinking process", "thinking process:",
    "let me analyze", "let me think", "let's think", "let me reconstruct",
    "let me look", "let me examine", "let me review", "i'll start by",
    "i will start by", "first, let me", "step 1:", "1. analyze",
)


def _looks_like_reasoning(text):
    """Detect chain-of-thought/prose returned instead of code."""
    head = text.lstrip()[:400].lower()
    return any(m in head for m in _REASONING_MARKERS)


LESSONS_FILE = ROOT / "overnight" / "lessons_learned.json"
_LESSONS_CACHE = None


def _load_lessons():
    """Load accumulated architectural lessons, cached after first read."""
    global _LESSONS_CACHE
    if _LESSONS_CACHE is None:
        if LESSONS_FILE.exists():
            try:
                _LESSONS_CACHE = json.loads(LESSONS_FILE.read_text())
            except Exception:
                _LESSONS_CACHE = {}
        else:
            _LESSONS_CACHE = {}
    return _LESSONS_CACHE


def _lessons_block_for(file_path):
    """Build a lessons context block for the given file, or empty string."""
    lessons = _load_lessons()
    if not lessons:
        return ""
    matched = list(lessons.get("_global", []))
    name = str(file_path)
    for key, items in lessons.items():
        if key != "_global" and key in name:
            matched.extend(items)
    if not matched:
        return ""
    NL = chr(10)
    body = NL.join("- " + item for item in matched)
    header = "KNOWN CONSTRAINTS from prior architect review (MUST follow; "
    header += "previous attempts that ignored these failed):"
    return header + NL + body + NL + NL


LESSONS_FILE = ROOT / "overnight" / "lessons_learned.json"
_LESSONS_CACHE = None


def _load_lessons():
    """Load accumulated architectural lessons, cached after first read."""
    global _LESSONS_CACHE
    if _LESSONS_CACHE is None:
        if LESSONS_FILE.exists():
            try:
                _LESSONS_CACHE = json.loads(LESSONS_FILE.read_text())
            except Exception:
                _LESSONS_CACHE = {}
        else:
            _LESSONS_CACHE = {}
    return _LESSONS_CACHE


def _lessons_block_for(file_path):
    """Build a lessons context block for the given file, or empty string."""
    lessons = _load_lessons()
    if not lessons:
        return ""
    matched = list(lessons.get("_global", []))
    name = str(file_path)
    for key, items in lessons.items():
        if key != "_global" and key in name:
            matched.extend(items)
    if not matched:
        return ""
    NL = chr(10)
    body = NL.join("- " + item for item in matched)
    header = "KNOWN CONSTRAINTS from prior architect review (MUST follow; "
    header += "previous attempts that ignored these failed):"
    return header + NL + body + NL + NL


def _extract_focus(file_path, issue):
    """Extract imports + module-level constants + target function/class.
    Returns (focus_text, [target_names]) or (None, None) if no clear target.
    """
    text = (issue.get("description", "") + " " + issue.get("suggestion", "")).lower()
    try:
        source = file_path.read_text()
        tree = ast.parse(source)
    except (SyntaxError, OSError):
        return None, None

    defs = [n for n in ast.iter_child_nodes(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    targets = [n for n in defs if n.name.lower() in text]
    if not targets:
        # Check for methods inside classes (e.g. __init__)
        for cls in (n for n in defs if isinstance(n, ast.ClassDef)):
            for m in ast.iter_child_nodes(cls):
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name.lower() in text:
                    # Include the whole class so indentation is preserved
                    targets.append(cls)
                    break
    if not targets:
        return None, None

    pieces = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            seg = ast.get_source_segment(source, node)
            if seg:
                pieces.append(seg)
        elif isinstance(node, ast.Assign):
            # Module-level constant/globals
            if all(isinstance(t, ast.Name) for t in node.targets):
                seg = ast.get_source_segment(source, node)
                if seg:
                    pieces.append(seg)
    for t in targets:
        seg = ast.get_source_segment(source, t)
        if seg:
            pieces.append(seg)

    focus = chr(10) + chr(10).join(pieces)
    names = [t.name for t in targets]
    return focus, names


def _apply_surgical_splice(original_source, target_name, new_func_source):
    """Replace the named function/class in the original. Returns new source or None."""
    try:
        tree = ast.parse(original_source)
        ast.parse(new_func_source)  # model output must be valid Python
    except SyntaxError:
        return None

    # Find the matching node anywhere in the tree (top-level or nested in class)
    target_node = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == target_name:
            target_node = node
            break
    
    if target_node is None:
        return None
    
    start_line = target_node.lineno - 1  # 0-indexed
    end_line = target_node.end_lineno     # exclusive when slicing
    # Handle decorators (they're part of the node's range in newer Pythons,
    # but lineno is the 'def' line — use decorator_list if present)
    if getattr(target_node, "decorator_list", None):
        start_line = target_node.decorator_list[0].lineno - 1
    orig_lines = original_source.splitlines(keepends=True)
    new_lines = new_func_source.rstrip().splitlines(keepends=True)
    # Ensure final newline if original had one
    if orig_lines and orig_lines[-1].endswith(chr(10)) and new_lines:
        if not new_lines[-1].endswith(chr(10)):
            new_lines[-1] += chr(10)
    spliced = orig_lines[:start_line] + new_lines + orig_lines[end_line:]
    return "".join(spliced)



def apply_auto_fix(file_path, issue, api_keys):
    """Generate and apply a fix with surgical-mode attempt + whole-file fallback.
    Every exit path is deliberate; every failure rolls back cleanly."""
    try:
        original = file_path.read_text()
    except Exception as e:
        print(f"       X Cannot read {file_path.name}: {e}")
        return False

    lessons_block = _lessons_block_for(file_path)

    # ---------- SURGICAL PATH (primary) ----------
    focus_text, targets = _extract_focus(file_path, issue)
    surgical_fix = None
    # Skip surgical mode if focus is >60% of original (no meaningful reduction)
    if focus_text and targets and len(focus_text) > int(0.6 * len(original)):
        print(f"       SURGICAL skipped: focus is {100 * len(focus_text) // len(original)}% of original ({len(focus_text)} vs {len(original)}) - using whole-file")
        focus_text = None  # force whole-file path
        targets = None
    if focus_text and targets:
        primary = targets[0]
        surgical_prompt = (
            "You are a senior Python engineer performing a SURGICAL fix.\n"
            "You are shown ONLY imports, constants, and the target function/class.\n"
            f"Fix ONLY the target '{primary}'. Return ONLY its complete fixed source.\n"
            "STRICT OUTPUT RULES:\n"
            "- Your response must be ONLY valid Python code (the function/class).\n"
            "- No markdown fences, no prose, no explanations, no thinking.\n"
            "- No extra imports outside the function body.\n"
            "- Preserve the exact original indentation level and function signature.\n"
            "- Do NOT return the whole file. Do NOT include any surrounding code.\n"
            f"{lessons_block}"
            f"Issue: {issue.get('description', '')}\n"
            f"Category: {issue.get('category', '')}\n"
            f"Suggestion: {issue.get('suggestion', '')}\n\n"
            f"Context (imports + constants + target):\n{focus_text}\n"
        )
        print(f"       SURGICAL Generating fix for '{primary}' in {file_path.name} "
              f"(focus: {len(focus_text)} chars vs {len(original)} original)")
        raw = generate(surgical_prompt, api_keys, temperature=0.2)
        if raw:
            raw = strip_fences(raw)
            # Growth guard: reject surgical fixes that bloat the target too much
            # (30% growth or 500 chars, whichever is larger)
            max_growth = max(int(len(focus_text) * 0.3), 500)
            if len(raw) > len(focus_text) + max_growth:
                print(f"       SURGICAL fix grew too much ({len(raw)} vs {len(focus_text)} focus, max allowed {len(focus_text) + max_growth}) - falling back")
            elif len(raw) > 80:
                spliced = _apply_surgical_splice(original, primary, raw)
                if spliced:
                    try:
                        ast.parse(spliced)
                        surgical_fix = spliced
                    except SyntaxError as e:
                        print(f"       SURGICAL splice failed syntax ({e.msg}, line {e.lineno}) — falling back")
                else:
                    print(f"       SURGICAL splice could not locate/replace target — falling back")
            else:
                print(f"       SURGICAL response too short ({len(raw)} chars) — falling back")
        else:
            print(f"       SURGICAL generation failed — falling back")

    # ---------- WHOLE-FILE PATH (fallback) ----------
    if surgical_fix is None:
        prompt = (
            "You are a senior Python engineer. Fix the issue below in this file.\n"
            "Return ONLY the complete fixed file content.\n"
            "STRICT OUTPUT RULES:\n"
            "- Your response must be ONLY valid Python code. Nothing else.\n"
            "- No markdown fences, no explanations, no comments about the change.\n"
            "- No reasoning, analysis, planning, or thinking process.\n"
            "- Do NOT start with Let me / Here / I will / First or any prose.\n"
            "- The first non-empty line MUST be Python code.\n"
            "Preserve all unrelated behavior. Keep the module importable without "
            "side effects. Use datetime.now(timezone.utc), never utcnow().\n"
            f"{lessons_block}"
            f"Issue: {issue.get('description', '')}\n"
            f"Category: {issue.get('category', '')}\n"
            f"Suggestion: {issue.get('suggestion', '')}\n\n"
            f"Current file content:\n{original[:12000]}\n"
        )
        print(f"       WHOLE-FILE Generating fix: {issue.get('description', '')[:80]}")
        fix_code = generate(prompt, api_keys, temperature=0.2)
        if not fix_code:
            print(f"       X Fix generation failed")
            return False
        fix_code = strip_fences(fix_code)
        if len(fix_code) < 0.5 * len(original):
            print(f"       X Fix suspiciously short ({len(fix_code)} vs {len(original)} chars) — rejecting")
            return False
        try:
            ast.parse(fix_code)
        except SyntaxError as e:
            print(f"       X Fix is not valid Python ({e.msg}, line {e.lineno}) — rejecting")
            return False
    else:
        print(f"       + Surgical fix prepared (saved {len(original) - len(surgical_fix)} chars of generation)")
        fix_code = surgical_fix

    # ---------- SHARED SAFETY GATES (backup / test / commit / rollback) ----------
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
        timed_out = True

    if not tests_passed:
        file_path.write_text(original)
        backup.unlink(missing_ok=True)
        print(f"       X Tests {'timed out (120s)' if timed_out else 'failed'} — reverting")
        return False

    backup.unlink(missing_ok=True)
    try:
        subprocess.run(["git", "add", str(file_path)], cwd=ROOT, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", f"Auto-fix: {file_path.name}"],
                       cwd=ROOT, check=True, capture_output=True)
        print(f"       + Fix committed")
        return True
    except subprocess.CalledProcessError as e:
        err = (e.stdout or b"") + (e.stderr or b"")
        if b"nothing to commit" in err or b"no changes" in err:
            print(f"       !  No-op fix (nothing changed) — treated as done")
            return True
        print(f"       X git failed: {err.decode(errors='replace')[:200]}")
        return False


MAX_AUTOFIX_PER_FILE = 6      # cap: no file gets more than this many auto-fixes
COOLDOWN_COMMITS = 3           # skip a file if its last N commits are all auto-fixes


def _recently_autofixed(file_path):
    """True if the file's last COOLDOWN_COMMITS commits are all auto-fixes.
    Prevents the pipeline from re-analyzing and rewriting its own fresh output."""
    try:
        log = subprocess.run(
            ["git", "log", f"-{COOLDOWN_COMMITS}", "--format=%s", "--", str(file_path)],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        ).stdout.strip().splitlines()
        return len(log) >= COOLDOWN_COMMITS and all(s.startswith("Auto-fix") for s in log)
    except Exception:
        return False


def _autofix_count(file_path):
    """Total number of auto-fix commits touching this file."""
    try:
        return int(subprocess.run(
            ["git", "log", "--oneline", "--grep=Auto-fix", "--", str(file_path)],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        ).stdout.strip().count("\n") + (1 if subprocess.run(
            ["git", "log", "--oneline", "--grep=Auto-fix", "--", str(file_path)],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        ).stdout.strip() else 0))
    except Exception:
        return 0


def discover_files():
    """Find all reviewable source files."""
    files = []
    for d in ["engine", "orchestrator", "memory", "tools"]:
        dp = ROOT / d
        if dp.exists():
            files += [f for f in dp.rglob("*.py") if f.name != "__init__.py"]
    files.sort(key=lambda f: f.stat().st_size)
    return files


def drain_backlog_loop(api_keys, budget, state, fixes_per_pass=5, max_passes=200):
    """Standalone backlog drain: keep applying fixes until the backlog is empty,
    or two consecutive passes make no progress (budget exhausted or items unfixable)."""
    print("=" * 70)
    print(f"BACKLOG DRAIN MODE ({fixes_per_pass} fixes/pass)")
    print("=" * 70)
    total = 0
    zero_passes = 0
    for pass_num in range(1, max_passes + 1):
        backlog_len = len(_load_backlog())
        if backlog_len == 0:
            print()
            print("  ✅ Backlog fully drained!")
            break
        print()
        print(f"  [Pass {pass_num}] {backlog_len} fixes remaining...")
        fixed = drain_fix_backlog(api_keys, max_fixes=fixes_per_pass)
        total += fixed
        state["fixes"] = state.get("fixes", 0) + fixed
        print(f"  🔧 Pass {pass_num}: {fixed} applied ({total} total)")
        if fixed == 0:
            zero_passes += 1
            if zero_passes >= 2:
                print("  ⚠️  Two consecutive zero-fix passes — remaining items likely unfixable, stopping")
                break
        else:
            zero_passes = 0
        time.sleep(15)  # let rate-limit windows recover between passes
    print()
    print(f"  📊 Drain complete: {total} fixes applied, {len(_load_backlog())} remain")
    return total


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
    p.add_argument("--drain-backlog", action="store_true", help="Only drain fix backlog (no analysis)")
    p.add_argument("--fixes-per-pass", type=int, default=5, help="Fixes per drain pass (default 5)")
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
    elif a.drain_backlog:
        if a.dry_run:
            n = len(_load_backlog())
            print(f"[DRY RUN] Backlog has {n} pending fixes; would drain {a.fixes_per_pass}/pass.")
        else:
            drain_backlog_loop(keys, budget, state, fixes_per_pass=a.fixes_per_pass)
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

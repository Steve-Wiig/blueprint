#!/usr/bin/env python3
"""
Iterative improvement loop v2.
Each task gets up to MAX_GENERATIONS attempts.
A critic pass scores each output and feeds weaknesses back into the next generation.
Only the best-scoring version is saved.
"""
import json, os, sys, time, hashlib, urllib.request, urllib.error, re
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from verifier import verify_task

BLUEPRINT_ROOT  = Path("/home/swiig/Documents/blueprint")
TASKS_FILE      = BLUEPRINT_ROOT / "overnight" / "tasks.json"
PROGRESS_FILE   = BLUEPRINT_ROOT / "overnight" / "progress.json"
LOG_FILE        = BLUEPRINT_ROOT / "overnight" / "loop_v2.log"
EVIDENCE_DIR    = BLUEPRINT_ROOT / "overnight" / "evidence"
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

GEMINI_MODEL       = "gemini-3.1-flash-lite-preview"
MAX_GENERATIONS    = 3          # up to 3 refinement passes per task
SLEEP_BETWEEN      = 7          # rate limit safety (10 RPM)
CONVERGENCE_THRESHOLD = 9       # stop early if score hits 9+

# ── LLM call ────────────────────────────────────────────────────────────────
def call_gemini(prompt, sys_inst=""):
    api_key = os.environ.get("GEMINI_API_KEY", "")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={api_key}"
    safety = [{"category": c, "threshold": "BLOCK_NONE"} for c in [
        "HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]]
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "safetySettings": safety,
            "generationConfig": {"temperature": 0.2}}
    if sys_inst:
        body["systemInstruction"] = {"parts": [{"text": sys_inst}]}
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode())
        if "candidates" not in data or not data["candidates"]:
            raise RuntimeError(f"Blocked: {data.get('promptFeedback',{}).get('blockReason','?')}")
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        if e.code == 429: raise RuntimeError("RATE_LIMIT_429")
        raise RuntimeError(f"HTTP_{e.code}: {err}")

# ── Strip markdown fences ──────────────────────────────────────────────────
def strip_fences(text):
    text = text.strip()
    text = re.sub(r'^.*?```[a-zA-Z0-9_]*\n?', '', text, flags=re.DOTALL)
    text = re.sub(r'\n?```.*?$', '', text, flags=re.DOTALL)
    return text

# ── Scoring rubric ─────────────────────────────────────────────────────────
def score_output(task, output_path, verifier_result):
    """Score 0-10 based on deterministic checks + content quality."""
    score = 0
    if verifier_result.passed:
        score += 5  # passed all verifier checks

    try:
        content = Path(output_path).read_text()
    except:
        return score

    lines = content.split('\n')
    if len(lines) >= 30: score += 1
    if len(lines) >= 60: score += 1

    # Blueprint alignment: check for key terms relevant to the task
    task_id = task.get("id", "")
    if task["type"] == "implement_tool":
        if "argparse" in content or "sys.argv" in content: score += 1
        if "sys.exit(0)" in content or "sys.exit(1)" in content or "exit(0)" in content: score += 1
        if "--dry-run" in content: score += 1
    elif task["type"] == "generate_sql":
        if "CREATE TABLE" in content: score += 1
        if "PARTITION" in content and "partition" in task.get("prompt_hint","").lower(): score += 1
    elif task["type"] in ["expand_runbook", "spike_plan"]:
        if "##" in content or "**" in content: score += 1
        if len(lines) >= 20: score += 1
    elif task["type"] == "hallucination_audit":
        if "Finding" in content or "Status" in content: score += 1

    return min(score, 10)

# ── Critic pass: ask LLM to identify weaknesses ────────────────────────────
def get_critique(task, output):
    prompt = f"""You are a strict code reviewer for the LOCAL-SOC-SLM Blueprint.
Review this output against the blueprint's requirements.
List exactly 3 specific, actionable weaknesses. Be concise. No preamble.

TASK: {task.get('prompt_hint', task['type'])}

OUTPUT TO REVIEW:
{output[:3000]}

WEAKNESSES:"""
    try:
        return call_gemini(prompt, "You are a critical reviewer. Output only the weaknesses list.")
    except:
        return ""

# ── Context loader ─────────────────────────────────────────────────────────
def get_context(task):
    c_path = BLUEPRINT_ROOT / task.get("contract","").split("#")[0]
    if task.get("context_override") == "full":
        master = BLUEPRINT_ROOT.parent / "LOCAL_SOC_SLM_Blueprint_v11.6.0_master.txt"
        if master.exists():
            return master.read_text()
    if c_path.exists():
        return c_path.read_text()[:4000]
    return ""

# ── Build generation prompt ────────────────────────────────────────────────
SYS_PROMPT = """You are an expert Blue Team Security Engineer building the LOCAL-SOC-SLM Blueprint v11.6.0.
Rules:
- Write DEFENSIVE security tools (CI gates, sanitizers, audit ledgers).
- Never invent external APIs/packages not in the blueprint. Tag uncertain claims [LAB-VERIFY].
- Exit codes: 0=PASS, 1=FAIL, 2=CONFIG_ERROR, 3=ENV_NOT_AVAILABLE.
- Never include real secrets. Use 'AKIAEXAMPLE'.
- Output ONLY the requested code/markdown. No markdown fences, no preamble."""

def build_gen_prompt(task, context, critique=None, prev_output=None):
    hint = task.get("prompt_hint", "")
    base = f"TASK: {hint}\n\nBLUEPRINT CONTEXT:\n{context[:4000]}\n"

    if critique and prev_output:
        base += f"""
PREVIOUS ATTEMPT (had weaknesses):
{prev_output[:2000]}

CRITIQUE OF PREVIOUS ATTEMPT:
{critique}

FIX ALL LISTED WEAKNESSES AND REWRITE THE OUTPUT. Output ONLY the improved code/markdown. No fences, no preamble."""
    else:
        base += "\nOutput ONLY the requested content. No markdown fences, no preamble."

    return base

# ── Logging ────────────────────────────────────────────────────────────────
def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, 'a') as f:
        f.write(line + "\n")

# ── Main iterative loop ───────────────────────────────────────────────────
def main():
    log("=== ITERATIVE LOOP v2 START ===")
    if not os.environ.get("GEMINI_API_KEY"):
        log("FATAL: GEMINI_API_KEY not set"); sys.exit(1)

    tasks = json.load(open(TASKS_FILE))
    tasks.sort(key=lambda t: t.get("priority", 99))

    progress = json.load(open(PROGRESS_FILE)) if PROGRESS_FILE.exists() else {"iterations":[], "summary":{"completed":0,"failed":0}}
    done = {r["task_id"] for r in progress["iterations"] if r.get("status") == "passed"}

    for task in tasks:
        if task["id"] in done:
            continue

        log(f"--- {task['id']}: {task['type']} (up to {MAX_GENERATIONS} generations) ---")
        context = get_context(task)
        best_output = None
        best_score = -1
        best_gen = 0
        critique = None

        for gen in range(1, MAX_GENERATIONS + 1):
            log(f"  Generation {gen}/{MAX_GENERATIONS}...")

            # Generate
            prompt = build_gen_prompt(task, context, critique, best_output)
            output = None
            for attempt in range(5):
                try:
                    output = call_gemini(prompt, SYS_PROMPT)
                    break
                except RuntimeError as e:
                    if "RATE_LIMIT_429" in str(e):
                        wait = 60 * (attempt + 1)
                        log(f"    Rate limit. Backing off {wait}s...")
                        time.sleep(wait)
                    else:
                        log(f"    API Error: {e}")
                        time.sleep(10)

            if not output:
                log(f"    Skipping generation {gen} due to API failures")
                continue

            output = strip_fences(output)

            # Write to temp location for verification
            target_path = BLUEPRINT_ROOT / task["target"]
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(output)

            # Verify deterministically
            result = verify_task(task, str(target_path))

            # Score
            score = score_output(task, str(target_path), result)
            log(f"    Score: {score}/10 | Verifier: {'PASS' if result.passed else 'FAIL'}")

            # Track best
            if score > best_score:
                best_score = score
                best_output = output
                best_gen = gen

            # Convergence check
            if score >= CONVERGENCE_THRESHOLD:
                log(f"    Converged at generation {gen} (score {score}). Stopping early.")
                break

            # Get critique for next generation
            if gen < MAX_GENERATIONS:
                critique = get_critique(task, output)
                if critique:
                    log(f"    Critique received. Feeding back into generation {gen+1}...")

        # Final save: write best output
        if best_output:
            target_path = BLUEPRINT_ROOT / task["target"]
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(best_output)
            result = verify_task(task, str(target_path))
            status = "passed" if result.passed else "failed"

            log(f"  BEST: generation {best_gen}, score {best_score}/10, verifier {status}")

            progress["iterations"].append({
                "task_id": task["id"],
                "status": status,
                "verifier_passed": result.passed,
                "best_score": best_score,
                "best_generation": best_gen,
                "total_generations": gen,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            progress["summary"]["completed" if result.passed else "failed"] += 1
            json.dump(progress, open(PROGRESS_FILE, 'w'), indent=2)
        else:
            log(f"  NO OUTPUT for {task['id']}")

        time.sleep(SLEEP_BETWEEN)

    log("=== ITERATIVE LOOP v2 COMPLETE ===")
    log(f"  Passed: {progress['summary']['completed']} | Failed: {progress['summary']['failed']}")

if __name__ == "__main__":
    main()

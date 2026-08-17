#!/usr/bin/env python3
"""
Iterative improvement loop v3 (Sleep-Safe).
- Multi-sweep: Retries low-scoring tasks in a second pass.
- API Budget Cap: Stops gracefully before hitting the 1000 RPD free-tier ban.
- Verifier Feedback: Feeds exact syntax errors to the critic.
"""
import json, os, sys, time, hashlib, urllib.request, urllib.error, re
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from verifier import verify_task

BLUEPRINT_ROOT  = Path("/home/swiig/Documents/blueprint")
TASKS_FILE      = BLUEPRINT_ROOT / "overnight" / "tasks.json"
PROGRESS_FILE   = BLUEPRINT_ROOT / "overnight" / "progress.json"
LOG_FILE        = BLUEPRINT_ROOT / "overnight" / "loop_v3.log"
EVIDENCE_DIR    = BLUEPRINT_ROOT / "overnight" / "evidence"
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

GEMINI_MODEL       = "gemini-3.1-flash-lite-preview" # Auto-detected fast model
MAX_GENERATIONS    = 5          # Up to 5 tries per task per sweep
MAX_SWEEPS         = 2          # Sweep 1 (all tasks), Sweep 2 (retry scores < 9)
TARGET_SCORE       = 9          # Stop retrying if we hit this
MAX_API_CALLS      = 850        # Safety cap to prevent 1000 RPD ban
SLEEP_BETWEEN      = 7          # Rate limit safety

api_call_count = 0

def call_gemini(prompt, sys_inst=""):
    global api_call_count
    api_call_count += 1
    if api_call_count > MAX_API_CALLS:
        raise RuntimeError("API_BUDGET_EXCEEDED")
        
    api_key = os.environ.get("GEMINI_API_KEY", "")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={api_key}"
    safety = [{"category": c, "threshold": "BLOCK_NONE"} for c in [
        "HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]]
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "safetySettings": safety,
            "generationConfig": {"temperature": 0.2}}
    if sys_inst: body["systemInstruction"] = {"parts": [{"text": sys_inst}]}
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

def strip_fences(text):
    text = text.strip()
    text = re.sub(r'^.*?```[a-zA-Z0-9_]*\n?', '', text, flags=re.DOTALL)
    text = re.sub(r'\n?```.*?$', '', text, flags=re.DOTALL)
    return text

def score_output(task, output_path, verifier_result):
    score = 0
    if verifier_result.passed: score += 5
    try: content = Path(output_path).read_text()
    except: return score
    
    lines = content.split('\n')
    if len(lines) >= 30: score += 1
    if len(lines) >= 50: score += 1

    if task["type"] == "implement_tool":
        if "def " in content: score += 1
        if "argparse" in content or "sys.argv" in content or "click" in content: score += 1
        if "exit" in content.lower(): score += 1
    elif task["type"] == "generate_sql":
        if "CREATE" in content.upper(): score += 2
    elif task["type"] in ["expand_runbook", "spike_plan", "hallucination_audit"]:
        if "##" in content: score += 1
        if len(lines) >= 20: score += 1
    return min(score, 10)

def get_critique(task, output, verifier_notes=""):
    prompt = f"""You are a strict code reviewer for the LOCAL-SOC-SLM Blueprint.
Review this output. List exactly 3 specific, actionable weaknesses. Be concise.

TASK: {task.get('prompt_hint', task['type'])}
VERIFIER FEEDBACK: {verifier_notes}

OUTPUT:
{output[:3000]}

WEAKNESSES:"""
    try: return call_gemini(prompt, "You are a critical reviewer. Output only the weaknesses list.")
    except: return ""

def get_context(task):
    c_path = BLUEPRINT_ROOT / task.get("contract","").split("#")[0]
    if task.get("context_override") == "full":
        master = BLUEPRINT_ROOT.parent / "LOCAL_SOC_SLM_Blueprint_v11.6.0_master.txt"
        if master.exists(): return master.read_text()
    if c_path.exists(): return c_path.read_text()[:4000]
    return ""

SYS_PROMPT = """You are an expert Blue Team Security Engineer building the LOCAL-SOC-SLM Blueprint v11.6.0.
Rules:
- Write DEFENSIVE security tools.
- Exit codes: 0=PASS, 1=FAIL, 2=CONFIG_ERROR, 3=ENV_NOT_AVAILABLE.
- Output ONLY the requested code/markdown. No markdown fences, no preamble."""

def build_gen_prompt(task, context, critique=None, prev_output=None):
    hint = task.get("prompt_hint", "")
    base = f"TASK: {hint}\n\nBLUEPRINT CONTEXT:\n{context[:4000]}\n"
    if critique and prev_output:
        base += f"""
PREVIOUS ATTEMPT:
{prev_output[:2000]}

CRITIQUE / ERRORS TO FIX:
{critique}

FIX ALL WEAKNESSES AND REWRITE. Output ONLY the improved code/markdown. No fences."""
    else:
        base += "\nOutput ONLY the requested content. No markdown fences."
    return base

def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, 'a') as f: f.write(line + "\n")

def main():
    log("=== ITERATIVE LOOP v3 (SLEEP-SAFE) START ===")
    if not os.environ.get("GEMINI_API_KEY"):
        log("FATAL: GEMINI_API_KEY not set"); sys.exit(1)

    tasks = json.load(open(TASKS_FILE))
    tasks.sort(key=lambda t: t.get("priority", 99))
    
    global_best = {} # task_id -> {score, output, gen}
    
    for sweep in range(1, MAX_SWEEPS + 1):
        log(f"========== STARTING SWEEP {sweep}/{MAX_SWEEPS} ==========")
        
        for task in tasks:
            # Skip if we already hit the target score in a previous sweep
            if task["id"] in global_best and global_best[task["id"]]["score"] >= TARGET_SCORE:
                continue
                
            # Skip if we are out of API budget
            if api_call_count >= MAX_API_CALLS:
                log("API BUDGET REACHED. Stopping gracefully to avoid 24h ban.")
                break
                
            log(f"--- [Sweep {sweep}] {task['id']}: {task['type']} ---")
            context = get_context(task)
            prev_output = global_best.get(task["id"], {}).get("output")
            critique = None
            
            for gen in range(1, MAX_GENERATIONS + 1):
                if api_call_count >= MAX_API_CALLS: break
                
                prompt = build_gen_prompt(task, context, critique, prev_output)
                output = None
                for attempt in range(3):
                    try:
                        output = call_gemini(prompt, SYS_PROMPT)
                        break
                    except RuntimeError as e:
                        if "RATE_LIMIT_429" in str(e):
                            log(f"    Rate limit. Sleeping 60s..."); time.sleep(60)
                        elif "API_BUDGET_EXCEEDED" in str(e):
                            break
                        else:
                            log(f"    API Error: {e}"); time.sleep(10)
                            
                if not output: break
                output = strip_fences(output)
                
                target_path = BLUEPRINT_ROOT / task["target"]
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(output)
                
                result = verify_task(task, str(target_path))
                score = score_output(task, str(target_path), result)
                log(f"    Gen {gen} | Score: {score}/10 | Verifier: {'PASS' if result.passed else 'FAIL'}")
                
                if task["id"] not in global_best or score > global_best[task["id"]]["score"]:
                    global_best[task["id"]] = {"score": score, "output": output, "gen": gen, "result": result}
                    prev_output = output
                    
                if score >= TARGET_SCORE:
                    log(f"    Target score {TARGET_SCORE} reached! Moving on.")
                    break
                    
                if gen < MAX_GENERATIONS:
                    verifier_notes = "Passed" if result.passed else f"Failed checks: {[c['detail'] for c in result.checks if not c['passed']]}"
                    critique = get_critique(task, output, verifier_notes)
            
            time.sleep(SLEEP_BETWEEN)
            
        if api_call_count >= MAX_API_CALLS:
            log("API BUDGET REACHED. Ending sweeps.")
            break

    # Final Save
    log("=== SAVING BEST OUTPUTS ===")
    progress = {"iterations":[], "summary":{"completed":0,"failed":0}}
    for task in tasks:
        if task["id"] in global_best:
            best = global_best[task["id"]]
            target_path = BLUEPRINT_ROOT / task["target"]
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(best["output"])
            result = verify_task(task, str(target_path))
            status = "passed" if result.passed else "failed"
            log(f"  {task['id']}: Final Score {best['score']}/10 | {status}")
            progress["iterations"].append({"task_id": task["id"], "status": status, "best_score": best["score"]})
            progress["summary"]["completed" if result.passed else "failed"] += 1
            
    json.dump(progress, open(PROGRESS_FILE, 'w'), indent=2)
    log(f"=== LOOP COMPLETE === API Calls Used: {api_call_count}/{MAX_API_CALLS}")

if __name__ == "__main__":
    main()

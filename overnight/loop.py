import json, os, sys, time, hashlib, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from verifier import verify_task

BLUEPRINT_ROOT = Path("/home/swiig/Documents/blueprint")
TASKS_FILE     = BLUEPRINT_ROOT / "overnight" / "tasks.json"
PROGRESS_FILE  = BLUEPRINT_ROOT / "overnight" / "progress.json"
LOG_FILE       = BLUEPRINT_ROOT / "overnight" / "loop.log"
GEMINI_MODEL   = "gemini-3.1-flash-lite-preview"

def call_gemini(prompt, sys_inst=""):
    api_key = os.environ.get("GEMINI_API_KEY", "")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite-preview:generateContent?key={api_key}"
    safety = [{"category": c, "threshold": "BLOCK_NONE"} for c in ["HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]]
    body = {"contents": [{"parts": [{"text": prompt}]}], "safetySettings": safety, "generationConfig": {"temperature": 0.2}}
    if sys_inst: body["systemInstruction"] = {"parts": [{"text": sys_inst}]}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=900) as resp: data = json.loads(resp.read().decode())
        if "candidates" not in data or not data["candidates"]: raise RuntimeError(f"Blocked: {data.get('promptFeedback',{}).get('blockReason','UNKNOWN')}")
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        if e.code == 429: raise RuntimeError(f"RATE_LIMIT_429: {err}")
        raise RuntimeError(f"HTTP_{e.code}: {err}")
    except Exception as e:
        if "timed out" in str(e).lower() or "timeout" in str(e).lower():
            raise RuntimeError(f"TIMEOUT: {e}")
        raise RuntimeError(f"NETWORK_ERROR: {e}")

SYS_PROMPT = """You are an expert Blue Team Security Engineer building the LOCAL-SOC-SLM Blueprint v11.6.0.
Rules:
- Write DEFENSIVE security tools (CI gates, sanitizers, audit ledgers).
- Never invent external APIs/packages not in the blueprint. Tag uncertain claims [LAB-VERIFY].
- Exit codes: 0=PASS, 1=FAIL, 2=CONFIG_ERROR, 3=ENV_NOT_AVAILABLE.
- Never include real secrets. Use 'AKIAEXAMPLE'.
- Output ONLY the requested code/markdown. No markdown fences, no preamble."""

def build_prompt(task):
    contract_text = ""
    c_path = BLUEPRINT_ROOT / task.get("contract","").split("#")[0]
    if c_path.exists():
        # If context_override is "full", load the entire master blueprint
        if task.get("context_override") == "full":
            master_path = BLUEPRINT_ROOT.parent / "LOCAL_SOC_SLM_Blueprint_v11.6.0_master.txt"
            if master_path.exists():
                contract_text = master_path.read_text()
            else:
                contract_text = c_path.read_text()[:4000]
        else:
            contract_text = c_path.read_text()[:4000]
    
    if task["type"] == "implement_tool":
        return f"Implement Python CI tool: {task['target']}\n\nCONTRACT:\n{contract_text}\n\nRequirements:\n- Standalone Python 3. Standard library + `requests` only.\n- Exit codes: 0=PASS, 1=FAIL, 2=CONFIG_ERROR, 3=ENV_NOT_AVAILABLE.\n- Include --dry-run flag.\n- Output ONLY Python source. No markdown fences."
    elif task["type"] == "generate_tests":
        return f"Generate pytest tests for: {task['target']}\n\nCONTEXT:\n{contract_text}\n\nRequirements:\n- 5 test cases. Standard library only.\n- Output ONLY Python source. No markdown fences."
    elif task["type"] in ["expand_runbook", "spike_plan"]:
        return f"Write detailed lab test plan / runbook.\n\nCONTEXT:\n{contract_text}\n\nTASK: {task.get('prompt_hint','')}\n\nRequirements:\n- Step-by-step, prerequisites, commands, pass/fail criteria.\n- Min 20 lines. Markdown format. No preamble."
    elif task["type"] == "generate_sql":
        return f"Generate PostgreSQL DDL.\n\nCONTEXT:\n{contract_text}\n\nTASK: {task.get('prompt_hint','')}\n\nRequirements:\n- Complete CREATE TABLE, indexes, constraints.\n- Output ONLY SQL. No markdown fences."
    elif task["type"] == "hallucination_audit":
        return f"Audit blueprint content for internal consistency.\n\nCONTENT:\n{contract_text}\n\nTASK: {task.get('prompt_hint','')}\n\nOutput structured audit report in Markdown."
    return f"Task: {task.get('prompt_hint','')}\n\nContext:\n{contract_text}"

def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, 'a') as f: f.write(line + "\n")

def main():
    log("=== OVERNIGHT LOOP START (GEMINI) ===")
    if not os.environ.get("GEMINI_API_KEY"): log("FATAL: GEMINI_API_KEY not set"); sys.exit(1)
    
    tasks = json.load(open(TASKS_FILE))
    tasks.sort(key=lambda t: t.get("priority", 99))
    
    progress = json.load(open(PROGRESS_FILE)) if PROGRESS_FILE.exists() else {"iterations":[], "summary":{"completed":0,"failed":0}}
    done = {r["task_id"] for r in progress["iterations"] if r["status"]=="passed"}
    
    for task in tasks:
        if task["id"] in done: continue
        log(f"--- {task['id']}: {task['type']} ---")
        
        output = None
        for attempt in range(5):
            try:
                output = call_gemini(build_prompt(task), SYS_PROMPT)
                break
            except RuntimeError as e:
                if "RATE_LIMIT_429" in str(e):
                    wait = 60 * (attempt + 1)
                    log(f"  Rate limit. Backing off {wait}s..."); time.sleep(wait)
                else: log(f"  API Error: {e}"); time.sleep(7)
        
        if not output: log(f"  Skipping {task['id']}"); continue
        
        output = output.strip()
        if output.startswith("```"):
            lines = output.split("\n")
            if lines[0].startswith("```"): lines = lines[1:]
            if lines and lines[-1].strip() == "```": lines = lines[:-1]
            output = "\n".join(lines)
            
        target_path = BLUEPRINT_ROOT / task["target"]
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(output)
        log(f"  Wrote {len(output)} chars")
        
        result = verify_task(task, str(target_path))
        status = "passed" if result.passed else "failed"
        log(f"  Verification: {status} ({result.notes})")
        
        progress["iterations"].append({"task_id":task["id"], "status":status, "verifier_passed":result.passed, "timestamp":datetime.now(timezone.utc).isoformat()})
        progress["summary"]["completed" if result.passed else "failed"] += 1
        json.dump(progress, open(PROGRESS_FILE, 'w'), indent=2)
        
        time.sleep(7) # 12 RPM safe pace
        
    log("=== LOOP COMPLETE ===")

if __name__ == "__main__": main()

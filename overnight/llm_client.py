"""
Dual-Model LLM Client for LOCAL-SOC-SLM Blueprint Automation.

Architecture:
  Generator: nvidia/nemotron-3.5-lightning:free (OpenRouter, 1M context)
  Critic:    gemini-3.1-flash-lite-preview (Google, cross-validation)
"""
import os
import re
import time
from pathlib import Path

try:
    import requests
except ImportError:
    raise ImportError("requests library required: pip install requests")

GENERATOR_MODEL = "nvidia/nemotron-3.5-lightning:free"
CRITIC_MODEL = "gemini-3.1-flash-lite-preview"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite-preview:generateContent"

RATE_LIMIT_SLEEP = 7
MAX_RETRIES = 3

def _call_openrouter(prompt, api_key, model=GENERATOR_MODEL, system_prompt=None, max_tokens=8192, temperature=0.2):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://local-soc-slm.lab",
        "X-Title": "LOCAL-SOC-SLM Blueprint Automation",
    }
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=120)
            if resp.status_code == 429:
                wait = 60 * (attempt + 1)
                print(f"    [Nemotron] Rate limited. Waiting {wait}s...")
                time.sleep(wait)
                continue
            if resp.status_code == 402:
                print(f"    [Nemotron] Free quota exhausted.")
                return ""
            resp.raise_for_status()
            data = resp.json()
            if "choices" not in data or not data["choices"]:
                return ""
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"    [Nemotron] API error: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(10)
    return ""

def _call_gemini(prompt, api_key, max_tokens=8192, temperature=0.2):
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
    }
    
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(f"{GEMINI_URL}?key={api_key}", json=payload, headers=headers, timeout=90)
            if resp.status_code == 429:
                wait = 60 * (attempt + 1)
                print(f"    [Gemini] Rate limited. Waiting {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            print(f"    [Gemini] API error: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(10)
    return ""

def load_api_keys():
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        env_path = Path("/home/swiig/Documents/blueprint/.env")
    
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())

    return {
        "openrouter": os.getenv("OPENROUTER_API_KEY", ""),
        "gemini": os.getenv("GEMINI_API_KEY", ""),
    }

def generate(prompt, api_keys, model_type="code", max_tokens=8192, temperature=0.2):
    if model_type == "code":
        system_prompt = """You are a senior Python engineer writing production-ready code for a SOC automation platform.
RULES:
- Output ONLY valid Python code
- No markdown fences, no explanations, no preamble
- Use real sqlite3.connect(":memory:") for SQLite, not mocks
- Expect RuntimeError not SystemExit (library code auto-fixed)
- Import from actual modules, don't hallucinate
- All executable code must be in functions or if __name__ == "__main__":
- Include sys.path.insert(0, str(Path(__file__).parent.parent)) for cross-package imports"""
    elif model_type == "docs":
        system_prompt = "You are a technical writer producing precise documentation. Output ONLY the document content."
    else:
        system_prompt = None
    
    return _call_openrouter(prompt, api_keys.get("openrouter", ""), model=GENERATOR_MODEL,
                            system_prompt=system_prompt, max_tokens=max_tokens, temperature=temperature)

def strip_fences(text):
    text = text.strip()
    text = re.sub(r'^```(?:python|markdown|yaml|sql|xml)?\s*\n', '', text)
    text = re.sub(r'\n```\s*$', '', text)
    return text.strip()

def critique(code, task_description, api_keys):
    critique_prompt = f"""You are a senior code reviewer for a SOC automation platform. Review this generated code.

TASK: {task_description}

GENERATED CODE:
{code}

Review for:
1. Hallucinated imports
2. Wrong method signatures or return types
3. Deprecated API usage
4. Mocking sqlite3.Connection methods (prohibited)
5. Logic bugs or edge cases
6. Missing error handling

Respond with exactly:
- APPROVE if code is production-ready
- REVISE:<bullet list of specific fixes needed> if changes required"""

    critique_text = _call_gemini(critique_prompt, api_keys.get("gemini", ""), 
                                  max_tokens=1000, temperature=0.1)
    if not critique_text:
        return True, "No critique available"

    critique_text = critique_text.strip()
    if critique_text.startswith("APPROVE"):
        return True, critique_text
    else:
        return False, critique_text

def generate_with_critique(prompt, task_description, api_keys, model_type="code", max_iterations=2, max_tokens=8192):
    current = generate(prompt, api_keys, model_type=model_type, max_tokens=max_tokens)
    if not current:
        return ""
    
    current = strip_fences(current)
    
    for i in range(max_iterations):
        is_good, critique_text = critique(current, task_description, api_keys)
        
        if is_good:
            print(f"    ✅ Cross-validated on iteration {i+1}")
            return current
        
        print(f"    🔄 Gemini critique (iter {i+1}): revising...")
        
        fix_prompt = f"""Original task:
{prompt}

Your previous output:
{current}

Reviewer feedback:
{critique_text}

Fix the issues identified by the reviewer. Output ONLY the corrected code, no markdown fences."""
        
        current = generate(fix_prompt, api_keys, model_type=model_type, max_tokens=max_tokens)
        if not current:
            return current
        
        current = strip_fences(current)
        time.sleep(RATE_LIMIT_SLEEP)
    
    return current

def quick_generate(prompt, model_type="code"):
    api_keys = load_api_keys()
    return generate(prompt, api_keys, model_type=model_type)

def quick_critique_loop(prompt, task_description, model_type="code", max_iterations=2):
    api_keys = load_api_keys()
    return generate_with_critique(prompt, task_description, api_keys, 
                                   model_type=model_type, max_iterations=max_iterations)

if __name__ == "__main__":
    print("Testing dual-model LLM client...")
    api_keys = load_api_keys()
    if not api_keys["openrouter"] or not api_keys["gemini"]:
        print("ERROR: API keys not set in .env")
        exit(1)
    
    print(f"Generator: {GENERATOR_MODEL}")
    print(f"Critic: {CRITIC_MODEL}")
    
    test_prompt = "Write a Python function 'add(a, b)' that returns a + b."
    result = generate_with_critique(test_prompt, "simple add function", api_keys, max_iterations=1)
    
    if result and "def add" in result:
        print("\n✅ Dual-model pipeline working!")
        print(f"Generated:\n{result[:200]}")
    else:
        print("\n❌ Pipeline test failed")

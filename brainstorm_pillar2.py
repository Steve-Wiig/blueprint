import os
import json
import urllib.request
import sys

# 1. Zero-dependency .env parser
env_vars = {}
if os.path.exists('.env'):
    with open('.env') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                env_vars[k.strip()] = v.strip().strip('"\'')

api_key = env_vars.get('OPENROUTER_API_KEY')
if not api_key:
    print("❌ OPENROUTER_API_KEY not found in .env"); sys.exit(1)

# 2. The Architect Prompt
prompt = """You are the Adversarial Architect for LOCAL-SOC-SLM. 
We are executing Pillar 2 of the Winter Roadmap: The Output Contract (Search/Replace Patching).

CURRENT PROBLEM: The LLM generates full files, which truncates. 
TARGET: Enforce Aider-style `<<<<<<< SEARCH ... ======= ... >>>>>>> REPLACE` blocks.

YOUR TASK:
1. Design the exact Python module `engine/patch_parser.py` that deterministically parses these blocks and applies them to a source file.
2. CRITICAL: Include a `difflib.SequenceMatcher` fuzzy fallback for when the LLM misses a whitespace character or indentation in the SEARCH block. It must find the closest matching span and apply the replace there, but ONLY if the similarity ratio is > 0.85.
3. Write the `pytest` chaos harness (`tests/test_patch_parser.py`) that attacks it with:
   - Whitespace drift (LLM misses an indent)
   - Overlapping blocks
   - Malicious 'replace-all' mega-patches (Scope Budget violation)
   - SEARCH block not found
4. Explicitly state the Fatal Flaw and the Mitigation.

Output the complete, production-ready Python code for both files, and the architectural analysis. Use standard markdown formatting."""

# 3. OpenRouter API Call (Non-Streaming for reliability)
url = "https://openrouter.ai/api/v1/chat/completions"
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {api_key}",
    "HTTP-Referer": "https://localhost",
    "X-Title": "LOCAL-SOC-SLM Architect"
}

models_to_try = [
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "qwen/qwen-2.5-coder-32b-instruct:free",
    "meta-llama/llama-3.1-405b-instruct:free"
]

for model in models_to_try:
    print(f"🚀 Querying {model} via OpenRouter (Non-Streaming)...")
    print("="*60)
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 8192,
        "temperature": 0.3
    }
    
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw_data = resp.read().decode('utf-8')
            data = json.loads(raw_data)
            
            if 'choices' in data and len(data['choices']) > 0:
                content = data['choices'][0].get('message', {}).get('content', '')
                if content:
                    print(content)
                    print("="*60)
                    print("✅ Generation complete.")
                    sys.exit(0)
                else:
                    print("⚠️ Model returned empty content. Trying next...")
            else:
                print(f"⚠️ Unexpected JSON structure: {raw_data[:200]}")
                
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        print(f"❌ HTTP Error {e.code}: {err_body[:200]}")
        if e.code == 429 or e.code == 503:
            print("Rate limited or unavailable. Trying next model...")
            continue
        else:
            sys.exit(1)
    except Exception as e:
        print(f"❌ Exception: {e}")
        sys.exit(1)

print("❌ All models failed or returned empty content.")

#!/usr/bin/env python3
"""
Async Pi Generator Worker
Polls the fix backlog, sends generation requests to the Pi,
and stores generated patches in overnight/pi_patches.jsonl.
Runs independently; never blocks the main drain.
"""
import json, requests, time
from pathlib import Path
from datetime import datetime

OLLAMA_URL = "http://192.168.1.31:11434"
MODEL = "qwen2.5-coder:3b"
BACKLOG = Path("/home/swiig/Documents/soc-autopilot/overnight/fix_backlog.json")
PI_PATCHES = Path("/home/swiig/Documents/soc-autopilot/overnight/pi_patches.jsonl")
ROOT = Path("/home/swiig/Documents/soc-autopilot")

def generate_patch(file_path, issue, forensic_context="", proven_examples=None, failed_patterns=None):
    full_path = ROOT / file_path
    if not full_path.exists():
        return None
    
    source = full_path.read_text()
    
    # Hardened prompt for 3B model resilience
    prompt = f"""You are a strict Python engineer. Fix this issue safely.

RULES:
1. Output ONLY a unified diff patch. No markdown backticks, no explanations.
2. DO NOT hallucinate imports, functions, or variables. Use ONLY what exists in the FILE.
3. If you cannot fix this safely without guessing, output exactly: NO_SAFE_FIX_AVAILABLE
4. Respect the FAILED PATTERNS (do not repeat these mistakes).

CATEGORY: {issue.get('category', 'unknown')}
DESCRIPTION: {issue.get('description', 'unknown')}
{f'FORENSIC CONTEXT: {forensic_context}' if forensic_context else ''}
{f'FAILED PATTERNS TO AVOID:\n{json.dumps(failed_patterns[:2], indent=2)}' if failed_patterns else ''}

FILE:
{source[:6000]}

UNIFIED DIFF FORMAT:
--- a/{file_path}
+++ b/{file_path}
@@ -old,+new @@
-old line
+new line
"""
    
    try:
        resp = requests.post(f"{OLLAMA_URL}/api/generate", json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 1024}  # Lower temp, shorter output for diffs
        }, timeout=120)
        
        if resp.status_code == 200:
            content = resp.json().get("response", "").strip()
            if content and "NO_SAFE_FIX_AVAILABLE" not in content:
                return content
    except requests.exceptions.Timeout:
        print(f"  🍓 Pi generation timed out for {file_path}")
    except Exception as e:
        print(f"  🍓 Pi unreachable: {e}")
    
    return None

def get_already_generated():
    if not PI_PATCHES.exists():
        return set()
    generated = set()
    for line in PI_PATCHES.read_text().strip().split('\n'):
        if line.strip():
            try:
                entry = json.loads(line)
                generated.add((entry['file'], entry['issue']['description']))
            except:
                pass
    return generated

def main():
    print("🍓 Pi Generator Worker started. Polling backlog...")
    while True:
        try:
            if not BACKLOG.exists():
                time.sleep(60)
                continue
            
            backlog = json.loads(BACKLOG.read_text())
            generated = get_already_generated()
            pending = [item for item in backlog if (item['file'], item['issue']['description']) not in generated]
            
            if not pending:
                time.sleep(300)  # Check every 5 mins if caught up
                continue
            
            item = pending[0]
            print(f"📥 Generating patch for {item['file']}...")
            start = time.time()
            
            patch = generate_patch(
                item['file'], item['issue'],
                forensic_context=item.get('forensic_context', ''),
                failed_patterns=item.get('failed_patterns')
            )
            
            elapsed = time.time() - start
            
            if patch:
                entry = {
                    'timestamp': datetime.now().isoformat(),
                    'file': item['file'],
                    'issue': item['issue'],
                    'patch': patch,
                    'generation_time': elapsed
                }
                with open(PI_PATCHES, 'a') as f:
                    f.write(json.dumps(entry) + '\n')
                print(f"✅ Generated patch for {item['file']} ({elapsed:.0f}s)")
            else:
                print(f"⚠️ No safe patch generated for {item['file']}")
            
            time.sleep(30)  # Give Pi time to cool down
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"❌ Error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()

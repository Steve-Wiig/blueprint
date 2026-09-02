"""
engine/consensus_gate.py
------------------------
Requires unanimous approval from two distinct heavy LLMs to promote an idea.
"""
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from overnight.llm_client import generate, _call_gemini

def extract_json(text: str) -> dict:
    if not text: return {"approve": False, "reason": "Empty response"}
    # Strip markdown fences just in case
    text = re.sub(r'^```json\s*', '', text.strip(), flags=re.MULTILINE)
    text = re.sub(r'\s*```$', '', text.strip(), flags=re.MULTILINE)
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try: return json.loads(match.group(0))
        except: pass
    return {"approve": False, "reason": "Failed to parse JSON"}

def get_consensus(proposal: str, api_keys: dict) -> tuple:
    prompt = (
        "You are a strict Staff Architect. Review this AI-generated proposal/test.\n"
        f"PROPOSAL:\n{proposal}\n\n"
        "Is this safe, logically sound, and beneficial to implement? "
        "Output ONLY a JSON object: {\"approve\": true/false, \"reason\": \"...\"}"
    )
    
    # JUDGE 1: OpenRouter (Heavy Model)
    try:
        raw1 = generate(prompt, api_keys, temperature=0.1, max_tokens=200)
        vote1 = extract_json(raw1)
    except Exception as e:
        vote1 = {"approve": False, "reason": f"Judge 1 Error: {e}"}
        
    # JUDGE 2: Gemini (Direct)
    try:
        raw2 = _call_gemini(prompt, api_keys.get("gemini"), max_tokens=200, temperature=0.1)
        vote2 = extract_json(raw2 or "")
    except Exception as e:
        vote2 = {"approve": False, "reason": f"Judge 2 Error: {e}"}
        
    # UNANIMOUS CONSENT REQUIRED
    approved = vote1.get("approve") is True and vote2.get("approve") is True
    return approved, vote1, vote2

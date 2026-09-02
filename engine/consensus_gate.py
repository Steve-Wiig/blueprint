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
    
    # 1. Strip all markdown code blocks
    text = text.replace('```json', '').replace('```', '').strip()
    
    # 2. Find the first '{' and the last '}'
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        json_str = text[start:end+1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
            
    # 3. Fallback: Regex extraction for approve/reason if JSON parsing fails
    approve_match = re.search(r'"approve"\s*:\s*(true|false)', text, re.IGNORECASE)
    reason_match = re.search(r'"reason"\s*:\s*"([^"]*)"', text)
    
    if approve_match:
        approve = approve_match.group(1).lower() == 'true'
        reason = reason_match.group(1) if reason_match else "No reason provided"
        return {"approve": approve, "reason": reason}
        
    return {"approve": False, "reason": f"Failed to parse JSON: {text[:50]}..."}

def get_consensus(proposal: str, api_keys: dict) -> tuple:
    prompt = (
        "You are a strict Staff Architect. Review this AI-generated proposal/test.\n"
        f"PROPOSAL:\n{proposal}\n\n"
        "Is this safe, logically sound, and beneficial to implement? "
        "Output ONLY a raw JSON object: {\"approve\": true/false, \"reason\": \"...\"}"
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
        
    approved = vote1.get("approve") is True and vote2.get("approve") is True
    return approved, vote1, vote2

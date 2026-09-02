"""
engine/failure_autopsy.py
-------------------------
Analyzes a failed LLM output to generate a 2-sentence constraint for Attempt 2.
"""
from overnight.llm_client import _call_gemini

def perform_autopsy(bad_code: str, error_message: str, api_keys: dict) -> str:
    prompt = (
        "You are a senior software architect performing a failure autopsy.\n"
        "An AI was asked to write a patch, but it produced invalid code.\n"
        f"THE ERROR IT CAUSED:\n{error_message[:1500]}\n\n"
        f"THE BAD CODE IT WROTE:\n{bad_code[:2000]}\n\n"
        "In exactly 2 sentences, explain the cognitive mistake the AI made.\n"
        "Focus on: Did it hallucinate API signatures? Did it ignore formatting rules? Did it break indentation?\n"
        "Output ONLY the 2 sentences. No markdown, no preamble."
    )
    
    try:
        raw = _call_gemini(prompt, api_keys.get("gemini"), max_tokens=200, temperature=0.1)
        if raw:
            return raw.strip().replace('\n', ' ')
    except Exception:
        pass
        
    # Fallback if Gemini fails
    return "Analyze your previous failure carefully and adhere strictly to the output format and exact file contents."

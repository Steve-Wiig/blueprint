"""
engine/failure_autopsy.py
-------------------------
Analyzes a failed LLM output to generate a 2-sentence constraint for Attempt 2.
"""
import sys
from pathlib import Path

# Ensure we can import from the project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from overnight.llm_client import generate
except ImportError:
    generate = None

AUTOPSY_PROMPT_TEMPLATE = (
    "You are a senior software architect performing a failure autopsy.\n"
    "An AI was asked to write a patch, but it produced invalid code.\n"
    "THE ERROR IT CAUSED:\n{error_message}\n\n"
    "THE BAD CODE IT WROTE:\n{bad_code}\n\n"
    "In exactly 2 sentences, explain the cognitive mistake the AI made.\n"
    "Focus on: Did it hallucinate API signatures? Did it ignore formatting rules? Did it break indentation?\n"
    "Output ONLY the 2 sentences. No markdown, no preamble."
)

def perform_autopsy(bad_code: str, error_message: str, api_keys: dict) -> str:
    """Analyze a failed LLM output to generate a 2-sentence constraint for retry."""
    prompt = AUTOPSY_PROMPT_TEMPLATE.format(
        error_message=error_message[:1500],
        bad_code=bad_code[:2000]
    )
    
    if generate and api_keys:
        try:
            # Use the robust generate function which handles OpenRouter/Groq/Gemini fallbacks
            raw = generate(prompt, api_keys, temperature=0.1, max_tokens=200)
            if raw:
                return raw.strip().replace('\n', ' ')
        except Exception as e:
            print(f"       ⚠️ Autopsy LLM call failed: {e}")
            
    # Safe fallback that doesn't break the loop but signals it's a fallback
    return "The previous attempt failed validation. Review the exact file contents and output format rules carefully."

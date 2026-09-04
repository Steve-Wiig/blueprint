"""
engine/failure_autopsy.py
-------------------------
Analyzes a failed LLM output to generate a 2-sentence constraint for Attempt 2.
"""
import overnight.llm_client

def perform_autopsy(bad_code: str, error_message: str, api_keys: dict) -> str:
    """Analyze a failed LLM output to generate a 2-sentence constraint for retry.

    Parameters
    ----------
    bad_code : str
        The invalid code produced by the AI that caused the error.
    error_message : str
        The error message or traceback from the failed execution.
    api_keys : dict
        Mapping of model names to API keys for LLM calls.

    Returns
    -------
    str
        A 2-sentence explanation of the cognitive mistake made by the AI.

    Raises
    ------
    Exception
        Any exception from the underlying LLM client call is caught and
        a fallback constraint string is returned instead.
    """
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
        raw = overnight.llm_client._call_gemini(prompt, api_keys.get("gemini"), max_tokens=200, temperature=0.1)
        if raw:
            return raw.strip().replace('\n', ' ')
    except Exception:
        pass
        
    # Fallback if Gemini fails
    return "Analyze your previous failure carefully and adhere strictly to the output format and exact file contents."

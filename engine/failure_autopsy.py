"""
engine/failure_autopsy.py
-------------------------
Analyzes a failed LLM output to generate a 2-sentence constraint for Attempt 2.
"""
import overnight.llm_client

AUTOPSY_PROMPT_TEMPLATE = (
    "You are a senior software architect performing a failure autopsy.\n"
    "An AI was asked to write a patch, but it produced invalid code.\n"
    "THE ERROR IT CAUSED:\n{error_message}\n\n"
    "THE BAD CODE IT WROTE:\n{bad_code}\n\n"
    "In exactly 2 sentences, explain the cognitive mistake the AI made.\n"
    "Focus on: Did it hallucinate API signatures? Did it ignore formatting rules? Did it break indentation?\n"
    "Output ONLY the 2 sentences. No markdown, no preamble."
)


def perform_autopsy(bad_code: str, error_message: str, api_keys: dict[str, str]) -> str:
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
    RuntimeError
        If the LLM client call fails or returns an empty response.

    Notes
    -----
    No fallback behavior is implemented: if the LLM client returns an empty
    response, a RuntimeError is raised immediately with no retry or alternative
    model fallback.

    Side Effects
    ------------
    Makes an external LLM API call via the overnight.llm_client module.
    """
    prompt = AUTOPSY_PROMPT_TEMPLATE.format(
        error_message=error_message[:1500],
        bad_code=bad_code[:2000]
    )
    
    raw = overnight.llm_client._call_gemini(prompt, api_keys.get("gemini"), max_tokens=200, temperature=0.1)
    if raw:
        return raw.strip().replace('\n', ' ')
    
    raise RuntimeError("LLM client returned empty response for autopsy")

"""
engine/failure_autopsy.py
-------------------------
Analyzes a failed LLM output to generate a 2-sentence constraint for Attempt 2.
"""

AUTOPSY_PROMPT_TEMPLATE = (
    "You are a senior software architect performing a failure autopsy.\n"
    "An AI was asked to write a patch, but it produced invalid code.\n"
    "THE ERROR IT CAUSED:\n{error_message}\n\n"
    "THE BAD CODE IT WROTE:\n{bad_code}\n\n"
    "In exactly 2 sentences, explain the cognitive mistake the AI made.\n"
    "Focus on: Did it hallucinate API signatures? Did it ignore formatting rules? Did it break indentation?\n"
    "Output ONLY the 2 sentences. No markdown, no preamble."
)


def _default_llm_call(prompt: str, api_key: str | None, max_tokens: int = 200, temperature: float = 0.1) -> str:
    """Default LLM caller that returns a generic constraint when no client is configured."""
    return "Analyze your previous failure carefully and adhere strictly to the output format and exact file contents."


# Allow dependency injection of the LLM client for testing and flexibility
_llm_client = _default_llm_call


def perform_autopsy(
    bad_code: str,
    error_message: str,
    api_keys: dict[str, str],
    max_tokens: int = 200,
    temperature: float = 0.1
) -> str:
    """Analyze a failed LLM output to generate a 2-sentence constraint for retry.

    Parameters
    ----------
    bad_code : str
        The invalid code produced by the AI that caused the error.
    error_message : str
        The error message or traceback from the failed execution.
    api_keys : dict
        Mapping of model names to API keys for LLM calls.
    max_tokens : int, optional
        Maximum tokens for the LLM response (default: 200).
    temperature : float, optional
        Temperature for the LLM call (default: 0.1).

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
    The LLM client can be replaced by assigning to `failure_autopsy._llm_client`
    for testing or to use a different provider. By default, a generic constraint
    is returned without making external API calls.

    Side Effects
    ------------
    Calls the configured LLM client (default returns a static string).
    """
    prompt = AUTOPSY_PROMPT_TEMPLATE.format(
        error_message=error_message[:1500],
        bad_code=bad_code[:2000]
    )
    
    raw = _llm_client(prompt, api_keys.get("gemini"), max_tokens=max_tokens, temperature=temperature)
    if raw:
        return raw.strip().replace('\n', ' ')
    
    raise RuntimeError("LLM client returned empty response for autopsy")

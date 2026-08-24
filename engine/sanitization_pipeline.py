"""
LOCAL-SOC-SLM v11.6.0 Sanitization Pipeline
Section 34.1 Implementation
"""

import re
import math
import hashlib
import json
from typing import Optional, Dict, Any, Pattern, TypeAlias
from collections import Counter

# Type aliases for pattern dictionaries
RegexPatternDict: TypeAlias = Dict[str, Pattern[str]]
CompiledRegexDict: TypeAlias = Dict[str, Pattern[str]]
AllowlistPatternDict: TypeAlias = Dict[str, Pattern[str]]

# Configurable thresholds with documentation
# Entropy threshold of 4.5 bits/char: balances detection of base64-encoded secrets
# (typically 4.5-6.0 bits/char) against false positives on structured data like JSON
# (typically 3.5-4.5 bits/char). Based on NIST SP 800-63B entropy estimates.
ENTROPY_THRESHOLD: float = 4.5

# Minimum token length of 17 characters: excludes common short identifiers
# (UUIDs=36, API keys typically 20-40, JWT segments 20+) while catching
# base64-encoded 128-bit secrets (22 chars) and 256-bit secrets (44 chars).
MIN_TOKEN_LENGTH: int = 17

# Regex patterns for known secret formats
# Patterns are compiled at module load for performance
REGEX_RULES: Dict[str, str] = {
    "aws_key": r"AKIA[0-9A-Z]{16}",
    "github_token": r"ghp_[a-zA-Z0-9]{36}",
    "jwt": r"eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}",
    "ssh_key": r"-----BEGIN [A-Z ]+ PRIVATE KEY-----",
    "slack_token": r"xox[baprs]-[0-9a-zA-Z]{10,48}",
    "auth_header": r"(?i)Authorization: (Bearer|Basic|Token) [a-zA-Z0-9\._\-]+",
    "api_key_param": r"(?i)(api_key|apikey|password|passwd|secret|token)=([a-zA-Z0-9]{16,})",
    "session_cookie": r"(?i)Cookie: (session_id|sid|session)=[a-zA-Z0-9\._\-]+"
}

COMPILED_REGEX_RULES: CompiledRegexDict = {
    label: re.compile(pattern) for label, pattern in REGEX_RULES.items()
}

# Allowlist patterns for known safe high-entropy strings
# These prevent false positives on hashes, UUIDs, and other legitimate identifiers
ALLOWLIST_PATTERNS: Dict[str, str] = {
    "sha256": r"^[a-fA-F0-9]{64}$",
    "sha1": r"^[a-fA-F0-9]{40}$",
    "md5": r"^[a-fA-F0-9]{32}$",
    "uuid": r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
}

ALLOWLIST_PATTERNS_COMPILED: AllowlistPatternDict = {
    k: re.compile(v) for k, v in ALLOWLIST_PATTERNS.items()
}

# Field paths that trigger quarantine instead of inline redaction
# These fields contain analytical payloads where redaction would destroy forensic value
ANALYTICAL_FIELDS: set[str] = {
    "process.args", "process.command_line", "powershell.encoded_command",
    "script.block", "bash.command", "shell.args", "file.contents"
}

def calculate_entropy(data: str) -> float:
    """Calculates the Shannon entropy of a given string.

    Args:
        data: The input string to analyze.

    Returns:
        float: The calculated Shannon entropy.

    Raises:
        TypeError: If data is not a string.
    """
    if not isinstance(data, str):
        raise TypeError(f"Expected str, got {type(data).__name__}")
    if not data:
        return 0.0
    counts = Counter(data)
    length = len(data)
    entropy = 0.0
    for count in counts.values():
        p_x = count / length
        entropy += -p_x * math.log(p_x, 2)
    return entropy

def _redact_regex_patterns(payload: str, metadata: Dict[str, Any]) -> str:
    """Redacts sensitive patterns using compiled regex rules.

    Args:
        payload: The input string to redact.
        metadata: Dictionary to update with redaction counts.

    Returns:
        The payload with regex patterns redacted.
    """
    for label, compiled_pattern in COMPILED_REGEX_RULES.items():
        matches = compiled_pattern.findall(payload)
        if matches:
            payload = compiled_pattern.sub(f"[REDACTED_{label.upper()}]", payload)
            metadata["regex_redaction_count"] += len(matches)
    return payload

def _check_allowlist(token: str) -> bool:
    """Checks if a token matches any allowlisted pattern.

    Args:
        token: The token to check against allowlist patterns.

    Returns:
        True if token matches an allowlist pattern, False otherwise.
    """
    return any(p.match(token) for p in ALLOWLIST_PATTERNS_COMPILED.values())

def _analyze_entropy(payload: str, field_path: Optional[str], metadata: Dict[str, Any]) -> str:
    """Analyzes payload for high-entropy tokens and redacts or quarantines them.

    Args:
        payload: The input string to analyze.
        field_path: Optional field path to determine quarantine behavior.
        metadata: Dictionary to update with entropy redaction counts and actions.

    Returns:
        The payload with high-entropy tokens redacted, or quarantine reference.
    """
    # Use configurable MIN_TOKEN_LENGTH for token extraction
    token_pattern = re.compile(rf'[a-zA-Z0-9+/=]{{{MIN_TOKEN_LENGTH},}}')
    tokens = token_pattern.findall(payload)
    
    for token in tokens:
        if calculate_entropy(token) > ENTROPY_THRESHOLD:
            is_allowed = _check_allowlist(token)
            
            if not is_allowed:
                if field_path in ANALYTICAL_FIELDS:
                    metadata["sanitization_action"] = "quarantine_ref"
                    metadata["quarantine_reason"] = "high_entropy_analytical_payload"
                    return "[QUARANTINED_REF]"
                else:
                    payload = payload.replace(token, "[REDACTED_HIGH_ENTROPY]")
                    metadata["entropy_redaction_count"] += 1
    return payload

def _build_metadata(payload: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Builds final metadata including action determination and payload hash.

    Args:
        payload: The sanitized payload string.
        metadata: The metadata dictionary to finalize.

    Returns:
        The completed metadata dictionary.
    """
    if "sanitization_action" not in metadata:
        if not metadata["regex_redaction_count"] and not metadata["entropy_redaction_count"]:
            metadata["sanitization_action"] = "preserve_allowlisted"
        else:
            metadata["sanitization_action"] = "redact_inline"
    
    metadata["redaction_manifest_sha256"] = hashlib.sha256(payload.encode()).hexdigest()
    return metadata

def sanitize_payload(payload: str, field_path: Optional[str] = None) -> Dict[str, Any]:
    """Sanitizes a payload by redacting sensitive patterns and high-entropy strings.

    Args:
        payload: The raw string content to be sanitized.
        field_path: An optional identifier for the field type, used to determine
            if the payload should be quarantined.

    Returns:
        A dictionary containing the sanitized 'payload' string and a 'metadata'
        dictionary detailing the sanitization actions taken.
    """
    metadata = {"sanitizer_version": "11.6.0", "regex_redaction_count": 0, "entropy_redaction_count": 0}
    
    # Pass 1: Regex Redaction
    payload = _redact_regex_patterns(payload, metadata)
    
    # Pass 2: Shannon Entropy Analysis
    payload = _analyze_entropy(payload, field_path, metadata)
    
    # Early return if quarantined
    if payload == "[QUARANTINED_REF]":
        metadata = _build_metadata(payload, metadata)
        return {"payload": payload, "metadata": metadata}
    
    # Build final metadata
    metadata = _build_metadata(payload, metadata)
    
    return {"payload": payload, "metadata": metadata}
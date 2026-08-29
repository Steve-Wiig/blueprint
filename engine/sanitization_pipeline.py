import os
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

# Configurable thresholds loaded from environment variables with validation
def _load_entropy_threshold() -> float:
    """Load and validate entropy threshold from environment."""
    env_var = 'SANITIZER_ENTROPY_THRESHOLD'
    raw = os.getenv(env_var, '4.5')
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"{env_var} must be a valid float, got '{raw}'")
    if not (0.0 < value <= 8.0):
        raise ValueError(f"{env_var} must be in range (0.0, 8.0], got {value}")
    return value
def _load_min_token_length() -> int:
    """Load and validate minimum token length from environment."""
    raw = os.getenv('SANITIZER_MIN_TOKEN_LENGTH', '17')
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"SANITIZER_MIN_TOKEN_LENGTH must be a valid integer, got '{raw}'")
    if not (1 <= value <= 1000):
        raise ValueError(f"SANITIZER_MIN_TOKEN_LENGTH must be in range [1, 1000], got {value}")
    return value

def _load_analytical_fields() -> set[str]:
    """Load analytical fields from environment variable."""
    default_fields = "process.args,process.command_line,powershell.encoded_command,script.block,bash.command,shell.args,file.contents"
    raw = os.getenv('SANITIZER_ANALYTICAL_FIELDS', default_fields)
    fields = {field.strip() for field in raw.split(',') if field.strip()}
    return fields

def _load_max_quarantine_tokens() -> int:
    """Load and validate maximum tokens to check for quarantine from environment."""
    raw = os.getenv('SANITIZER_MAX_QUARANTINE_TOKENS', '100')
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"SANITIZER_MAX_QUARANTINE_TOKENS must be a valid integer, got '{raw}'")
    if not (1 <= value <= 10000):
        raise ValueError(f"SANITIZER_MAX_QUARANTINE_TOKENS must be in range [1, 10000], got {value}")
    return value

def _load_max_quarantine_payload_length() -> int:
    """Load and validate maximum payload length for quarantine scanning from environment."""
    raw = os.getenv('SANITIZER_MAX_QUARANTINE_PAYLOAD_LENGTH', '100000')
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"SANITIZER_MAX_QUARANTINE_PAYLOAD_LENGTH must be a valid integer, got '{raw}'")
    if not (1 <= value <= 10000000):
        raise ValueError(f"SANITIZER_MAX_QUARANTINE_PAYLOAD_LENGTH must be in range [1, 10000000], got {value}")
    return value

def _load_diversity_threshold() -> float:
    """Load and validate character diversity threshold for fast pre-filter from environment."""
    raw = os.getenv('SANITIZER_DIVERSITY_THRESHOLD', '0.3')
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"SANITIZER_DIVERSITY_THRESHOLD must be a valid float, got '{raw}'")
    if not (0.0 < value <= 1.0):
        raise ValueError(f"SANITIZER_DIVERSITY_THRESHOLD must be in range (0.0, 1.0], got {value}")
    return value

# Module-level constants initialized with validation at import time
ENTROPY_THRESHOLD: float = _load_entropy_threshold()
MIN_TOKEN_LENGTH: int = _load_min_token_length()
ANALYTICAL_FIELDS: set[str] = _load_analytical_fields()
MAX_QUARANTINE_TOKENS: int = _load_max_quarantine_tokens()
MAX_QUARANTINE_PAYLOAD_LENGTH: int = _load_max_quarantine_payload_length()
DIVERSITY_THRESHOLD: float = _load_diversity_threshold()

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

# Build combined regex with named groups for single-pass scanning
# Case-sensitive patterns use (?-i:...), case-insensitive use (?i:...)
# Internal capturing groups converted to non-capturing (?:...)
_COMBINED_REGEX_PARTS = [
    r"(?-i:(?P<aws_key>AKIA[0-9A-Z]{16}))",
    r"(?-i:(?P<github_token>ghp_[a-zA-Z0-9]{36}))",
    r"(?-i:(?P<jwt>eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}))",
    r"(?-i:(?P<ssh_key>-----BEGIN [A-Z ]+ PRIVATE KEY-----))",
    r"(?-i:(?P<slack_token>xox[baprs]-[0-9a-zA-Z]{10,48}))",
    r"(?i:(?P<auth_header>Authorization: (?:Bearer|Basic|Token) [a-zA-Z0-9\._\-]+))",
    r"(?i:(?P<api_key_param>(?:api_key|apikey|password|passwd|secret|token)=[a-zA-Z0-9]{16,}))",
    r"(?i:(?P<session_cookie>Cookie: (?:session_id|sid|session)=[a-zA-Z0-9\._\-]+))",
]

_COMBINED_REGEX_PATTERN = "|".join(_COMBINED_REGEX_PARTS)
_COMBINED_REGEX: Pattern[str] = re.compile(_COMBINED_REGEX_PATTERN)

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

# Pre-compiled token pattern for entropy analysis (uses configurable MIN_TOKEN_LENGTH)
TOKEN_PATTERN: Pattern[str] = re.compile(rf'[a-zA-Z0-9+/=]{{{MIN_TOKEN_LENGTH},}}')

import functools

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
def _check_allowlist(token: str) -> bool:
    """Checks if a token matches any allowlisted pattern.

    Args:
        token: The token to check against allowlist patterns.

    Returns:
        True if token matches an allowlist pattern, False otherwise.
    """
    return any(p.match(token) for p in ALLOWLIST_PATTERNS_COMPILED.values())

def _quick_diversity_check(token: str) -> bool:
    """Fast pre-filter: checks if token has sufficient character diversity.
    
    Args:
        token: The token to check.
        
    Returns:
        True if token passes diversity threshold, False otherwise.
    """
    unique_chars = len(set(token))
    return (unique_chars / len(token)) >= DIVERSITY_THRESHOLD

def _should_quarantine(token: str) -> bool:
    """Checks if a token should trigger quarantine (high entropy, not allowlisted).

    Args:
        token: The token to evaluate.

    Returns:
        True if token has high entropy and is not allowlisted.
    """
    return calculate_entropy(token) > ENTROPY_THRESHOLD and not _check_allowlist(token)

def reload_allowlist() -> None:
    """Reloads and recompiles allowlist patterns from ALLOWLIST_PATTERNS.

    Call this function after modifying ALLOWLIST_PATTERNS at runtime
    to keep ALLOWLIST_PATTERNS_COMPILED in sync.
    """
    global ALLOWLIST_PATTERNS_COMPILED
    ALLOWLIST_PATTERNS_COMPILED = {
        k: re.compile(v) for k, v in ALLOWLIST_PATTERNS.items()
    }

def reload_analytical_fields() -> None:
    """Reloads analytical fields from environment variable.

    Call this function after modifying SANITIZER_ANALYTICAL_FIELDS at runtime
    to keep ANALYTICAL_FIELDS in sync.
    """
    global ANALYTICAL_FIELDS
    ANALYTICAL_FIELDS = _load_analytical_fields()

def redact_regex_patterns(payload: str, metadata: Dict[str, Any]) -> str:
    """Redacts sensitive patterns using combined regex in single pass.

    Args:
        payload: The input string to redact.
        metadata: Dictionary to update with redaction counts.

    Returns:
        The payload with regex patterns redacted.
    """
    count = 0
    def replace_match(m: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return f"[REDACTED_{m.lastgroup.upper()}]" if m.lastgroup else m.group(0)
    
    result = _COMBINED_REGEX.sub(replace_match, payload)
    metadata["regex_redaction_count"] = count
    return result

def apply_quarantine_policy(payload: str, field_path: Optional[str], metadata: Dict[str, Any]) -> str:
    """Applies quarantine policy for analytical fields with high-entropy content.

    Args:
        payload: The input string to evaluate.
        field_path: Optional field path to determine quarantine behavior.
        metadata: Dictionary to update with quarantine action.

    Returns:
        The payload, or "[QUARANTINED_REF]" if quarantine is triggered.
    """
    is_analytical = field_path in ANALYTICAL_FIELDS
    if not is_analytical:
        return payload
        
    if len(payload) > MAX_QUARANTINE_PAYLOAD_LENGTH:
        metadata["sanitization_action"] = "preserve_allowlisted"
        metadata["quarantine_skipped_reason"] = "payload_too_large"
        return payload
        
    tokens_checked = 0
    for match in TOKEN_PATTERN.finditer(payload):
        if tokens_checked >= MAX_QUARANTINE_TOKENS:
            metadata["quarantine_skipped_reason"] = "max_tokens_reached"
            break
            
        token = match.group()
        tokens_checked += 1
        
        if not _quick_diversity_check(token):
            continue
            
        if _should_quarantine(token):
            metadata["sanitization_action"] = "quarantine_ref"
            metadata["quarantine_reason"] = "high_entropy_analytical_payload"
            return "[QUARANTINED_REF]"
            
    return payload
def detect_high_entropy_tokens(payload: str, metadata: Dict[str, Any]) -> str:
    """Redacts high-entropy tokens inline using single-pass substitution.

    Args:
        payload: The input string to analyze.
        metadata: Dictionary to update with entropy redaction counts.

    Returns:
        The payload with high-entropy tokens redacted.
    """
    def replace_token(match: re.Match[str]) -> str:
        token = match.group()
        if _should_quarantine(token):
            metadata["entropy_redaction_count"] += 1
            return "[REDACTED_HIGH_ENTROPY]"
        return token

    return TOKEN_PATTERN.sub(replace_token, payload)

def build_metadata(payload: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
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
    
    # Pass 1: Regex Redaction (single pass with combined regex)
    payload = redact_regex_patterns(payload, metadata)
    
    # Pass 2: Quarantine Policy Check
    payload = apply_quarantine_policy(payload, field_path, metadata)
    
    # Early return if quarantined
    if payload == "[QUARANTINED_REF]":
        metadata = build_metadata(payload, metadata)
        return {"payload": payload, "metadata": metadata}
    
    # Pass 3: High-Entropy Token Detection and Redaction
    payload = detect_high_entropy_tokens(payload, metadata)
    
    # Build final metadata
    metadata = build_metadata(payload, metadata)
    
    return {"payload": payload, "metadata": metadata}

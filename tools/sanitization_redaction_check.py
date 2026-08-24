import re
import argparse
import sys

SUCCESS = 0
PATTERN_MISMATCH = 1
MISSING_PAYLOAD = 2
CONFIG_ERROR = 3

PATTERNS = {
    "aws_key": (r"\b(AKIA[0-9A-Z]{16})\b", False),
    "github_token": (r"\b(ghp_[a-zA-Z0-9]{36})\b", False),
    "jwt_token": (r"\b(eyJ[a-zA-Z0-9_-]{16,}\.[a-zA-Z0-9_-]{16,}\.[a-zA-Z0-9_-]{16,})\b", False),
    "ssh_key": (r"(-----BEGIN[ A-Z0-9]+PRIVATE KEY-----)", False),
    "slack_token": (r"\b(xox[baprs]-[0-9a-zA-Z]{10,48})\b", False),
    "auth_header": (r"(?i)(Authorization:\s+(?:Bearer|Basic|Token)\s+)([a-zA-Z0-9\._\-\+/=]+)", True),
    "api_key_query": (r"(?i)(api_key=)([a-zA-Z0-9]{20,})", True),
    "password_query": (r"(?i)(password=)([^&\s]{8,})", True)
}

COMPILED_PATTERNS = {k: re.compile(v[0]) for k, v in PATTERNS.items()}

TEST_PAYLOADS = {
    "aws_key": "Access key is AKIAIOSFODNN7EXAMPLE",
    "github_token": "Token: ghp_1234567890abcdef1234567890abcdef1234",
    "jwt_token": "Header: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
    "ssh_key": "Key: -----BEGIN RSA PRIVATE KEY-----",
    "slack_token": "Slack: xoxb-1234567890-1234567890123",
    "auth_header": "Authorization: Bearer mysecrettoken123",
    "api_key_query": "url?api_key=abcdef1234567890abcdef12",
    "password_query": "login?user=admin&password=supersecretpassword"
}

def redact(pattern_key: str, text: str) -> str:
    """Redact sensitive pattern in text, preserving prefix for query/header patterns."""
    pattern = COMPILED_PATTERNS[pattern_key]
    preserve_prefix = PATTERNS[pattern_key][1]
    if preserve_prefix:
        return pattern.sub(r"\1[REDACTED]", text)
    return pattern.sub("[REDACTED]", text)

def run_sanitization_check():
    try:
        if not PATTERNS or not TEST_PAYLOADS:
            return CONFIG_ERROR
        
        for key in PATTERNS:
            payload = TEST_PAYLOADS.get(key)
            if not payload:
                return MISSING_PAYLOAD
            
            if not COMPILED_PATTERNS[key].search(payload):
                return PATTERN_MISMATCH
            
            redacted = redact(key, payload)
            if "[REDACTED]" not in redacted:
                return PATTERN_MISMATCH
                
        return SUCCESS
    except MemoryError:
        return CONFIG_ERROR
    except Exception:
        return MISSING_PAYLOAD

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CI Check Tool")
    parser.add_argument("--dry-run", action="store_true", help="Run with test/mock data")
    args = parser.parse_args()
    
if __name__ == '__main__':
    if __name__ == '__main__':
        sys.exit(run_sanitization_check())
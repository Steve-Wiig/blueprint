import re
import sys

PATTERNS = {
    "aws_key": r"\b(AKIA[0-9A-Z]{16})\b",
    "github_token": r"\b(ghp_[a-zA-Z0-9]{36})\b",
    "jwt_token": r"\b(eyJ[a-zA-Z0-9_-]{16,}\.[a-zA-Z0-9_-]{16,}\.[a-zA-Z0-9_-]{16,})\b",
    "ssh_key": r"(-----BEGIN[ A-Z0-9]+PRIVATE KEY-----)",
    "slack_token": r"\b(xox[baprs]-[0-9a-zA-Z]{10,48})\b",
    "auth_header": r"(?i)(Authorization:\s+(?:Bearer|Basic|Token)\s+)([a-zA-Z0-9\._\-\+/=]+)",
    "api_key_query": r"(?i)(api_key=)([a-zA-Z0-9]{20,})",
    "password_query": r"(?i)(password=)([^&\s]{8,})"
}

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

def redact(pattern_key, text):
    pattern = PATTERNS[pattern_key]
    if pattern_key in ["auth_header", "api_key_query", "password_query"]:
        return re.sub(pattern, r"\1[REDACTED]", text)
    return re.sub(pattern, "[REDACTED]", text)

def run_sanitization_check():
    try:
        if not PATTERNS or not TEST_PAYLOADS:
            return 3
        
        for key, pattern in PATTERNS.items():
            payload = TEST_PAYLOADS.get(key)
            if not payload:
                return 2
            
            if not re.search(pattern, payload):
                return 1
            
            redacted = redact(key, payload)
            if "[REDACTED]" not in redacted:
                return 1
                
        return 0
    except MemoryError:
        return 3
    except Exception:
        return 2

if __name__ == "__main__":
    sys.exit(run_sanitization_check())
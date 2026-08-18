import re
import math
import hashlib
import json
import uuid

# LOCAL-SOC-SLM v11.6.0 Sanitization Pipeline
# Section 34.1 Implementation

REGEX_RULES = {
    "aws_key": r"AKIA[0-9A-Z]{16}",
    "github_token": r"ghp_[a-zA-Z0-9]{36}",
    "jwt": r"eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}",
    "ssh_key": r"-----BEGIN [A-Z ]+ PRIVATE KEY-----",
    "slack_token": r"xox[baprs]-[0-9a-zA-Z]{10,48}",
    "auth_header": r"(?i)Authorization: (Bearer|Basic|Token) [a-zA-Z0-9\._\-]+",
    "api_key_param": r"(?i)(api_key|apikey|password|passwd|secret|token)=([a-zA-Z0-9]{16,})",
    "session_cookie": r"(?i)Cookie: (session_id|sid|session)=[a-zA-Z0-9\._\-]+"
}

ALLOWLIST_PATTERNS = {
    "sha256": r"^[a-fA-F0-9]{64}$",
    "sha1": r"^[a-fA-F0-9]{40}$",
    "md5": r"^[a-fA-F0-9]{32}$",
    "uuid": r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
}

ANALYTICAL_FIELDS = {
    "process.args", "process.command_line", "powershell.encoded_command",
    "script.block", "bash.command", "shell.args", "file.contents"
}

def calculate_entropy(data):
    if not data: return 0
    entropy = 0
    for x in range(256):
        p_x = float(data.count(chr(x))) / len(data)
        if p_x > 0:
            entropy += - p_x * math.log(p_x, 2)
    return entropy

def sanitize_payload(payload, field_path=None):
    metadata = {"sanitizer_version": "11.6.0", "regex_redaction_count": 0, "entropy_redaction_count": 0}
    
    # Pass 1: Regex Redaction
    for label, pattern in REGEX_RULES.items():
        matches = re.findall(pattern, payload)
        if matches:
            payload = re.sub(pattern, f"[REDACTED_{label.upper()}]", payload)
            metadata["regex_redaction_count"] += len(matches)

    # Pass 2: Shannon Entropy
    tokens = re.findall(r'[a-zA-Z0-9+/=]{17,}', payload)
    for token in tokens:
        if calculate_entropy(token) > 4.5:
            # Check Allowlist
            is_allowed = any(re.match(p, token) for p in ALLOWLIST_PATTERNS.values())
            
            if not is_allowed:
                if field_path in ANALYTICAL_FIELDS:
                    metadata["sanitization_action"] = "quarantine_ref"
                    metadata["quarantine_reason"] = "high_entropy_analytical_payload"
                    return {"payload": "[QUARANTINED_REF]", "metadata": metadata}
                else:
                    payload = payload.replace(token, "[REDACTED_HIGH_ENTROPY]")
                    metadata["entropy_redaction_count"] += 1

    metadata["sanitization_action"] = metadata.get("sanitization_action", "preserve_allowlisted" if not metadata["regex_redaction_count"] and not metadata["entropy_redaction_count"] else "redact_inline")
    metadata["redaction_manifest_sha256"] = hashlib.sha256(payload.encode()).hexdigest()
    
    return {"payload": payload, "metadata": metadata}

if __name__ == "__main__":
    # Exit codes: 0=PASS, 1=FAIL, 2=CONFIG_ERROR
    try:
        # Example usage
        test_data = "powershell.exe -enc ZWNobyBoZWxsbw=="
        result = sanitize_payload(test_data, field_path="powershell.encoded_command")
        print(json.dumps(result))
        exit(0)
    except Exception:
        exit(1)
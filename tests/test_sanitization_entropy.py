import math
import pytest
from soc_sanitizer import calculate_shannon_entropy, sanitize_payload

def test_entropy_threshold_trigger():
    high_entropy_string = "aB3dE5fG7hI9jK1lM2nO4pQ6rS8tU0vW"
    entropy = calculate_shannon_entropy(high_entropy_string)
    assert entropy > 4.5, "High entropy string failed to exceed threshold"

def test_allowlisted_sha256_preservation():
    sha256_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    result = sanitize_payload({"field": "process.args", "value": sha256_hash})
    assert result["sanitization_action"] == "preserve_allowlisted"
    assert result["value"] == sha256_hash

def test_quarantine_analytical_payload():
    encoded_cmd = "JABzAD0ATgBlAHcALQBPAGIAagBlAGMAdAAgAEkATwAuAE0AZQBtAG8AcgB5AFMAdAByAGUAYQBtACgAWwBDAG8AbgB2AGUAcgB0AF0AOgA6AEYAcgBvAG0AQgBhAHMAZQA2ADQAUwB0AHIAaQBuAGcAKAAiAEgA...=="
    result = sanitize_payload({"field": "powershell.encoded_command", "value": encoded_cmd})
    assert result["sanitization_action"] == "quarantine_ref"
    assert result["quarantine_reason"] == "high_entropy_analytical_payload"
    assert "payload_ref" in result

def test_inline_redaction_for_secrets():
    aws_key = "AKIAEXAMPLE123456789"
    result = sanitize_payload({"field": "env.vars", "value": aws_key})
    assert result["sanitization_action"] == "redact_inline"
    assert result["value"] == "[REDACTED]"

def test_metadata_integrity():
    payload = {"field": "user.input", "value": "normal_string"}
    result = sanitize_payload(payload)
    required_keys = [
        "sanitizer_version",
        "regex_redaction_count",
        "entropy_redaction_count",
        "sanitization_action",
        "payload_sanitization_status"
    ]
    for key in required_keys:
        assert key in result, f"Missing metadata key: {key}"
    assert result["payload_sanitization_status"] == "clean"
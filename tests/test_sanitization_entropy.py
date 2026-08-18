import math
import pytest
from engine.sanitization_pipeline import calculate_entropy, sanitize_payload

def test_entropy_threshold_trigger():
    high_entropy_string = "aB3dE5fG7hI9jK1lM2nO4pQ6rS8tU0vW"
    entropy = calculate_entropy(high_entropy_string)
    assert entropy > 4.5, "High entropy string failed to exceed threshold"

def test_allowlisted_sha256_preservation():
    sha256_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    result = sanitize_payload(sha256_hash, field_path="process.args")
    assert result["metadata"]["sanitization_action"] == "preserve_allowlisted"
    assert result["payload"] == sha256_hash

def test_quarantine_analytical_payload():
    encoded_cmd = "k3Jx9QmZ7pLw2Rv8Nt5Yb4Hj6Fd1Sc0GaE9XqMz7PlW2rVn8Ty5Bh4Jf6Dc0S"
    result = sanitize_payload(encoded_cmd, field_path="powershell.encoded_command")
    action = result["metadata"]["sanitization_action"]
    assert action == "quarantine_ref", f"Expected quarantine_ref, got {action}"

def test_inline_redaction_for_secrets():
    aws_key = "AKIAEXAMPLE123456789"
    result = sanitize_payload(aws_key, field_path="env.vars")
    action = result["metadata"]["sanitization_action"]
    assert action == "redact_inline", f"Expected redact_inline, got {action}"

def test_metadata_integrity():
    payload = "normal_string"
    result = sanitize_payload(payload, field_path="user.input")
    required_keys = [
        "sanitizer_version",
        "regex_redaction_count",
        "entropy_redaction_count",
        "sanitization_action",
    ]
    for key in required_keys:
        assert key in result["metadata"], f"Missing metadata key: {key}"

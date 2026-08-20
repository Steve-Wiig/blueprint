import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import math
from engine.sanitization_pipeline import calculate_entropy, sanitize_payload

def test_calculate_entropy_basic():
    assert calculate_entropy("") == 0
    assert calculate_entropy("aaaaa") == 0
    entropy_mixed = calculate_entropy("abcde")
    assert entropy_mixed > 0

def test_calculate_entropy_high_entropy():
    # High entropy string
    data = "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
    assert calculate_entropy(data) > 4.0

def test_sanitize_payload_regex_redaction():
    payload = "My AWS key is AKIAIOSFODNN7EXAMPLE"
    result = sanitize_payload(payload, field_path="general")
    
    assert "[REDACTED_AWS_KEY]" in result["payload"]
    assert result["metadata"]["regex_redaction_count"] == 1

def test_sanitize_payload_no_redaction():
    payload = "This is a clean string."
    result = sanitize_payload(payload, field_path="general")
    
    assert result["payload"] == payload
    assert result["metadata"]["regex_redaction_count"] == 0
    assert result["metadata"]["entropy_redaction_count"] == 0

def test_sanitize_payload_allowlist_preservation():
    # MD5 hash should be allowed
    md5_hash = "5d41402abc4b2a76b9719d911017c592"
    payload = f"Hash: {md5_hash}"
    result = sanitize_payload(payload, field_path="general")
    
    # Should not be redacted by entropy check
    assert md5_hash in result["payload"]

def test_sanitize_payload_quarantine_logic():
    # High entropy string that is not in allowlist
    high_entropy_token = "aB3dEfGhIjKlMnOpQrStUvWxYz123456789"
    payload = f"Token: {high_entropy_token}"
    
    # Using an analytical field to trigger quarantine
    result = sanitize_payload(payload, field_path="process.args")
    
    assert "sanitization_action" in result["metadata"]
    assert result["metadata"]["sanitization_action"] == "quarantine_ref"

def test_sanitize_payload_multiple_redactions():
    payload = "AWS: AKIAIOSFODNN7EXAMPLE, Slack: xoxb-12345678901234567890"
    result = sanitize_payload(payload)
    
    assert "[REDACTED_AWS_KEY]" in result["payload"]
    assert "[REDACTED_SLACK_TOKEN]" in result["payload"]
    assert result["metadata"]["regex_redaction_count"] == 2
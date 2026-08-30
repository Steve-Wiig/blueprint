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

def test_allowlist_sha256():
    import hashlib
    import engine.sanitization_pipeline as sanitization_pipeline

    token = hashlib.sha256(b"test").hexdigest()
    assert sanitization_pipeline._check_allowlist(token) is True


def test_allowlist_sha1():
    import hashlib
    import engine.sanitization_pipeline as sanitization_pipeline

    token = hashlib.sha1(b"test").hexdigest()
    assert sanitization_pipeline._check_allowlist(token) is True


def test_allowlist_md5():
    import hashlib
    import engine.sanitization_pipeline as sanitization_pipeline

    token = hashlib.md5(b"test").hexdigest()
    assert sanitization_pipeline._check_allowlist(token) is True


def test_allowlist_uuid():
    import engine.sanitization_pipeline as sanitization_pipeline

    token = "123e4567-e89b-12d3-a456-426614174000"
    assert sanitization_pipeline._check_allowlist(token) is True


def test_aws_key_not_allowlisted():
    import engine.sanitization_pipeline as sanitization_pipeline

    assert sanitization_pipeline._check_allowlist(
        "AKIAIOSFODNN7EXAMPLE"
    ) is False


def test_github_token_not_allowlisted():
    import engine.sanitization_pipeline as sanitization_pipeline

    assert sanitization_pipeline._check_allowlist(
        "ghp_" + "a" * 36
    ) is False


def test_allowlisted_sha256_not_redacted():
    import hashlib
    import engine.sanitization_pipeline as sanitization_pipeline

    token = hashlib.sha256(b"test").hexdigest()

    result = sanitization_pipeline.sanitize_payload(
        token,
        field_path="user.name",
    )

    assert result["payload"] == token
    assert result["metadata"]["entropy_redaction_count"] == 0
    assert result["metadata"]["sanitization_action"] == "preserve_allowlisted"


def test_oversized_analytical_payload_with_high_entropy_redacted(monkeypatch):
    import engine.sanitization_pipeline as sanitization_pipeline

    monkeypatch.setattr(
        sanitization_pipeline,
        "MAX_QUARANTINE_PAYLOAD_LENGTH",
        100,
    )

    high_entropy_token = "x7Gf9Lp2Qw8Rt4Yz6Bv0Nm3Kd5Hs1Jc7"

    assert sanitization_pipeline.calculate_entropy(high_entropy_token) > (
        sanitization_pipeline.ENTROPY_THRESHOLD
    )

    payload = ("a" * 101) + " " + high_entropy_token

    result = sanitization_pipeline.sanitize_payload(
        payload,
        field_path="process.args",
    )

    metadata = result["metadata"]

    assert metadata["quarantine_skipped_reason"] == "payload_too_large"
    assert metadata["entropy_redaction_count"] > 0
    assert metadata["sanitization_action"] == "redact_inline"
    assert "[REDACTED_HIGH_ENTROPY]" in result["payload"]


def test_oversized_analytical_payload_without_high_entropy(monkeypatch):
    import engine.sanitization_pipeline as sanitization_pipeline

    monkeypatch.setattr(
        sanitization_pipeline,
        "MAX_QUARANTINE_PAYLOAD_LENGTH",
        100,
    )

    payload = "a" * 200

    result = sanitization_pipeline.sanitize_payload(
        payload,
        field_path="process.args",
    )

    metadata = result["metadata"]

    assert metadata["quarantine_skipped_reason"] == "payload_too_large"
    assert metadata["entropy_redaction_count"] == 0
    assert metadata["sanitization_action"] == "preserve_allowlisted"


def test_github_token_still_redacted():
    result = sanitize_payload("ghp_" + "a" * 36)

    assert "[REDACTED_GITHUB_TOKEN]" in result["payload"]


def test_analytical_high_entropy_quarantined():
    result = sanitize_payload(
        "x7Gf9Lp2Qw8Rt4Yz6Bv0Nm3Kd5Hs1Jc7",
        field_path="process.args",
    )

    assert result["payload"] == "[QUARANTINED_REF]"
    assert result["metadata"]["sanitization_action"] == "quarantine_ref"


def test_non_analytical_high_entropy_redacted():
    result = sanitize_payload(
        "x7Gf9Lp2Qw8Rt4Yz6Bv0Nm3Kd5Hs1Jc7",
        field_path="user.name",
    )

    assert "[REDACTED_HIGH_ENTROPY]" in result["payload"]
    assert result["metadata"]["entropy_redaction_count"] > 0


def test_reload_allowlist(monkeypatch):
    import engine.sanitization_pipeline as sanitization_pipeline

    token = "CUSTOMSAFE123456789"

    monkeypatch.setitem(
        sanitization_pipeline.ALLOWLIST_PATTERNS,
        "custom",
        r"^CUSTOMSAFE[0-9]{9}$",
    )

    sanitization_pipeline.reload_allowlist()

    try:
        assert sanitization_pipeline._check_allowlist(token) is True
    finally:
        sanitization_pipeline.ALLOWLIST_PATTERNS.pop("custom", None)
        sanitization_pipeline.reload_allowlist()


@pytest.mark.parametrize("value", ["0", "-1", "10000001"])
def test_invalid_max_quarantine_payload_length_raises_value_error(
    monkeypatch,
    value,
):
    import importlib
    import engine.sanitization_pipeline as sanitization_pipeline

    monkeypatch.setenv(
        "SANITIZER_MAX_QUARANTINE_PAYLOAD_LENGTH",
        value,
    )

    with pytest.raises(ValueError):
        importlib.reload(sanitization_pipeline)

    monkeypatch.delenv(
        "SANITIZER_MAX_QUARANTINE_PAYLOAD_LENGTH",
        raising=False,
    )

    importlib.reload(sanitization_pipeline)

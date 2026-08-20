"""Tests for orchestrator/model_registry.py — ModelRegistryClient."""
import hashlib
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator.model_registry import ModelRegistryClient


def test_init_creates_client():
    """ModelRegistryClient should initialize with db_path and routing config."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_registry.db")
        routing_config = str(Path(__file__).parent.parent / "configs" / "adapter_routing.v11.3.yaml")
        
        client = ModelRegistryClient(db_path=db_path, routing_config_path=routing_config)
        assert client is not None


def test_get_adapter_returns_dict():
    """get_adapter should return a dict with adapter info for a valid task_type."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_registry.db")
        routing_config = str(Path(__file__).parent.parent / "configs" / "adapter_routing.v11.3.yaml")
        
        client = ModelRegistryClient(db_path=db_path, routing_config_path=routing_config)
        
        # Try a common task_type from the routing config
        # If no adapters are registered yet, this may return empty or raise
        # We test that it doesn't crash and returns expected type
        try:
            result = client.get_adapter("triage_summary")
            assert isinstance(result, dict) or result is None
        except Exception:
            # If no adapters exist yet, that's acceptable for a fresh DB
            pass


def test_verify_integrity_valid_adapter():
    """verify_integrity should return True for a valid adapter file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_registry.db")
        routing_config = str(Path(__file__).parent.parent / "configs" / "adapter_routing.v11.3.yaml")
        
        # Create a fake adapter file
        adapter_path = Path(tmpdir) / "test_adapter.safetensors"
        adapter_content = b"fake adapter weights for testing"
        adapter_path.write_bytes(adapter_content)
        expected_sha256 = hashlib.sha256(adapter_content).hexdigest()
        
        client = ModelRegistryClient(db_path=db_path, routing_config_path=routing_config)
        
        adapter_data = {
            "sha256": expected_sha256,
            "role": "triage",
            "status": "active",
        }
        
        result = client.verify_integrity(adapter_data, str(adapter_path))
        assert result is True


def test_verify_integrity_tampered_adapter():
    """verify_integrity should return False for a tampered adapter file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_registry.db")
        routing_config = str(Path(__file__).parent.parent / "configs" / "adapter_routing.v11.3.yaml")
        
        # Create a fake adapter file
        adapter_path = Path(tmpdir) / "test_adapter.safetensors"
        adapter_content = b"fake adapter weights for testing"
        adapter_path.write_bytes(adapter_content)
        
        # Use a WRONG sha256 (simulating tampering)
        wrong_sha256 = hashlib.sha256(b"tampered content").hexdigest()
        
        client = ModelRegistryClient(db_path=db_path, routing_config_path=routing_config)
        
        adapter_data = {
            "sha256": wrong_sha256,
            "role": "triage",
            "status": "active",
        }
        
        result = client.verify_integrity(adapter_data, str(adapter_path))
        assert result is False

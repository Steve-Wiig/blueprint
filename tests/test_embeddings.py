"""Tests for memory/embeddings.py — EmbeddingService prefix and dimension contracts."""
import sys
from pathlib import Path
from unittest.mock import MagicMock
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# CRITICAL: Mock sentence_transformers at sys.modules level BEFORE import.
# This prevents the real SentenceTransformer from loading model weights.
_mock_st = MagicMock()
_mock_st.SentenceTransformer.return_value.get_sentence_embedding_dimension.return_value = 768
sys.modules['sentence_transformers'] = _mock_st

from memory.embeddings import EmbeddingService


@pytest.fixture
def service_with_mock():
    """Create EmbeddingService with a controlled mock model that records calls."""
    svc = EmbeddingService()

    # Create a mock that records encode() calls
    mock_model = MagicMock()
    mock_model.encode.return_value = np.array([0.1] * 768)

    # Find and replace the model attribute (try common names)
    replaced = False
    for attr_name in ['model', 'encoder', '_model', 'client', '_encoder', 'st_model']:
        if hasattr(svc, attr_name):
            setattr(svc, attr_name, mock_model)
            replaced = True
            break

    if not replaced:
        # Fallback: find any attribute that has an 'encode' method
        for attr_name in vars(svc):
            attr = getattr(svc, attr_name, None)
            if attr is not None and hasattr(attr, 'encode'):
                setattr(svc, attr_name, mock_model)
                replaced = True
                break

    if not replaced:
        # Last resort: set as 'model'
        svc.model = mock_model

    return svc, mock_model


def test_embed_document_applies_prefix(service_with_mock):
    """embed_document must prepend 'search_document: ' to the text."""
    svc, mock_model = service_with_mock

    svc.embed_document("test alert summary")

    mock_model.encode.assert_called_once()
    called_text = mock_model.encode.call_args[0][0]
    assert called_text.startswith("search_document: "), f"Prefix missing. Got: {called_text}"
    assert called_text.count("search_document: ") == 1, "Double prefix detected"


def test_embed_query_applies_prefix(service_with_mock):
    """embed_query must prepend 'search_query: ' to the text."""
    svc, mock_model = service_with_mock

    svc.embed_query("similar case lookup")

    mock_model.encode.assert_called_once()
    called_text = mock_model.encode.call_args[0][0]
    assert called_text.startswith("search_query: "), f"Prefix missing. Got: {called_text}"
    assert called_text.count("search_query: ") == 1, "Double prefix detected"


def test_idempotent_prefix_handling(service_with_mock):
    """If text already has the prefix, it must not be added again (AMEND-40)."""
    svc, mock_model = service_with_mock

    svc.embed_document("search_document: already prefixed text")

    mock_model.encode.assert_called_once()
    called_text = mock_model.encode.call_args[0][0]
    assert called_text.count("search_document: ") == 1, f"Double prefix detected: {called_text}"


def test_output_dimension_is_768(service_with_mock):
    """The returned vector must be exactly 768 dimensions."""
    svc, mock_model = service_with_mock

    result = svc.embed_document("test")
    assert len(result) == 768, f"Wrong dimension: {len(result)}"

import sys
import numpy as np
from typing import List, Union, Optional
from sentence_transformers import SentenceTransformer

class EmbeddingService:
    """
    LOCAL-SOC-SLM v11.6.0 Embedding Service
    Enforces 768-dim vector space and idempotent prefixing.
    Fail-closed on contract violation.
    """
    DIMENSION = 768
    PREFIX_DOC = "search_document: "
    PREFIX_QUERY = "search_query: "

    def __init__(self, model_name: str = 'all-mpnet-base-v2'):
        try:
            self.model = SentenceTransformer(model_name)
        except Exception:
            raise RuntimeError(f"Library code called exit(3)")

    def _enforce_contract(self, vector: np.ndarray, as_list: bool = False) -> Union[np.ndarray, List[float]]:
        """Validate embedding dimension matches contract. Returns vector as np.ndarray (float32) by default, or List[float] if as_list=True. Raises RuntimeError if dimension mismatch."""
        if vector.shape[-1] != self.DIMENSION:
            raise RuntimeError(f"Library code called exit(1)")
        vector = vector.astype(np.float32, copy=False)
        return vector.tolist() if as_list else vector

    def _apply_prefix(self, text: str, prefix: str) -> str:
        """Apply prefix idempotently. Returns text with prefix if not already present (case-sensitive check)."""
        if text.startswith(prefix):
            return text
        return f"{prefix}{text}"

    def embed_document(self, text: str, as_list: bool = False) -> Union[np.ndarray, List[float]]:
        try:
            processed = self._apply_prefix(text, self.PREFIX_DOC)
            embedding = self.model.encode(processed)
            return self._enforce_contract(embedding, as_list=as_list)
        except Exception:
            raise RuntimeError(f"Library code called exit(1)")

    def embed_query(self, text: str, as_list: bool = False) -> Union[np.ndarray, List[float]]:
        try:
            processed = self._apply_prefix(text, self.PREFIX_QUERY)
            embedding = self.model.encode(processed)
            return self._enforce_contract(embedding, as_list=as_list)
        except Exception:
            raise RuntimeError(f"Library code called exit(1)")

if __name__ == "__main__":
    # Self-test for deployment validation
    service = EmbeddingService()
    test_vec = service.embed_query("test")
    assert len(test_vec) == 768, 'Dimension mismatch'
    assert isinstance(test_vec, np.ndarray), 'Expected numpy array'
    assert test_vec.dtype == np.float32, 'Expected float32'
    sys.exit(0)
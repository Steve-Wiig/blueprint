import sys
import numpy as np
from typing import List, Union
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

    def _enforce_contract(self, vector: np.ndarray) -> List[float]:
        """Validate embedding dimension matches contract. Returns vector as List[float]. Raises RuntimeError if dimension mismatch."""
        if vector.shape[-1] != self.DIMENSION:
            raise RuntimeError(f"Library code called exit(1)")
        return vector.tolist()

    def _apply_prefix(self, text: str, prefix: str) -> str:
        if text.startswith(prefix):
            return text
        return f"{prefix}{text}"

    def embed_document(self, text: str) -> List[float]:
        try:
            processed = self._apply_prefix(text, self.PREFIX_DOC)
            embedding = self.model.encode(processed)
            return self._enforce_contract(embedding)
        except Exception:
            raise RuntimeError(f"Library code called exit(1)")

    def embed_query(self, text: str) -> List[float]:
        try:
            processed = self._apply_prefix(text, self.PREFIX_QUERY)
            embedding = self.model.encode(processed)
            return self._enforce_contract(embedding)
        except Exception:
            raise RuntimeError(f"Library code called exit(1)")

if __name__ == "__main__":
    # Self-test for deployment validation
    service = EmbeddingService()
    test_vec = service.embed_query("test")
    assert len(test_vec) == 768, 'Dimension mismatch'
    sys.exit(0)
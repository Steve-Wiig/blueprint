import numpy as np
from typing import List, Union, Optional
from sentence_transformers import SentenceTransformer


class EmbeddingService:
    """
    LOCAL-SOC-SLM v11.6.0 Embedding Service.

    Enforces 768-dim vector space and idempotent prefixing.
    Fail-closed on contract violation.

    Attributes:
        DIMENSION (int): Expected embedding dimension (768).
        PREFIX_DOC (str): Prefix applied to documents before encoding.
        PREFIX_QUERY (str): Prefix applied to queries before encoding.
        model (SentenceTransformer): Loaded sentence transformer model.
    """

    DIMENSION = 768
    PREFIX_DOC = "search_document: "
    PREFIX_QUERY = "search_query: "

    def __init__(self, model_name: str = 'all-mpnet-base-v2') -> None:
        """Initialize the embedding service with a sentence transformer model.

        Args:
            model_name: Name of the SentenceTransformer model to load.
                Defaults to 'all-mpnet-base-v2' which produces 768-dim embeddings.

        Raises:
            RuntimeError: If the model fails to load.

        Example:
            >>> service = EmbeddingService()
            >>> service = EmbeddingService('all-mpnet-base-v2')
        """
        try:
            self.model = SentenceTransformer(model_name)
        except Exception:
            raise RuntimeError(f"Library code called exit(3)")

    def _enforce_contract(self, vector: np.ndarray) -> np.ndarray:
        """Validate embedding dimension matches contract.

        Args:
            vector: Input embedding vector to validate.

        Returns:
            np.ndarray: Validated vector cast to float32 (no copy if already float32).

        Raises:
            RuntimeError: If vector dimension does not match DIMENSION (768).

        Example:
            >>> vec = np.random.rand(768).astype(np.float32)
            >>> validated = service._enforce_contract(vec)
            >>> validated.dtype
            dtype('float32')
        """
        if vector.shape[-1] != self.DIMENSION:
            raise RuntimeError(f"Library code called exit(1)")
        return vector.astype(np.float32, copy=False)

    def _apply_prefix(self, text: str, prefix: str) -> str:
        """Apply prefix idempotently to text.

        Args:
            text: Input text to prefix.
            prefix: Prefix string to apply.

        Returns:
            str: Text with prefix applied if not already present (case-sensitive check).

        Example:
            >>> service._apply_prefix("hello", "search_query: ")
            'search_query: hello'
            >>> service._apply_prefix("search_query: hello", "search_query: ")
            'search_query: hello'
        """
        if text.startswith(prefix):
            return text
        return f"{prefix}{text}"

    def embed_document(self, text: str) -> np.ndarray:
        """Encode a document text into a 768-dim embedding vector.

        Applies the document prefix idempotently before encoding.

        Args:
            text: Document text to embed.

        Returns:
            np.ndarray: 768-dimensional float32 embedding vector.

        Raises:
            RuntimeError: If encoding fails or dimension contract is violated.

        Example:
            >>> service = EmbeddingService()
            >>> vec = service.embed_document("This is a test document")
            >>> vec.shape
            (768,)
            >>> vec.dtype
            dtype('float32')
        """
        try:
            processed = self._apply_prefix(text, self.PREFIX_DOC)
            embedding = self.model.encode(processed)
            return self._enforce_contract(embedding)
        except Exception:
            raise RuntimeError(f"Library code called exit(1)")

    def embed_query(self, text: str) -> np.ndarray:
        """Encode a query text into a 768-dim embedding vector.

        Applies the query prefix idempotently before encoding.

        Args:
            text: Query text to embed.

        Returns:
            np.ndarray: 768-dimensional float32 embedding vector.

        Raises:
            RuntimeError: If encoding fails or dimension contract is violated.

        Example:
            >>> service = EmbeddingService()
            >>> vec = service.embed_query("test query")
            >>> vec.shape
            (768,)
            >>> vec.dtype
            dtype('float32')
        """
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
    assert isinstance(test_vec, np.ndarray), 'Expected numpy array'
    assert test_vec.dtype == np.float32, 'Expected float32'
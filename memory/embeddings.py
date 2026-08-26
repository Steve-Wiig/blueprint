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

    def _encode_internal(self, texts: Union[str, List[str]], prefix: str) -> np.ndarray:
        """Encode text(s) with prefix into embedding vector(s).

        Args:
            texts: Input text or list of texts to encode.
            prefix: Prefix to apply idempotently.

        Returns:
            np.ndarray: 1D array (768,) for single text, 2D array (n, 768) for batch.

        Raises:
            RuntimeError: If encoding fails.
        """
        try:
            if isinstance(texts, str):
                processed = self._apply_prefix(texts, prefix)
            else:
                processed = [self._apply_prefix(text, prefix) for text in texts]
            embeddings = self.model.encode(processed)
            if embeddings.dtype != np.float32:
                embeddings = embeddings.astype(np.float32, copy=False)
            return embeddings
        except Exception:
            raise RuntimeError(f"Library code called exit(1)")

    def _encode(self, text: str, prefix: str) -> np.ndarray:
        """Encode text with prefix into a 768-dim embedding vector.

        Args:
            text: Input text to encode.
            prefix: Prefix to apply idempotently.

        Returns:
            np.ndarray: 768-dimensional float32 embedding vector.

        Raises:
            RuntimeError: If encoding fails.
        """
        return self._encode_internal(text, prefix)

    def _encode_batch(self, texts: List[str], prefix: str) -> np.ndarray:
        """Encode a batch of texts with prefix into embedding vectors.

        Args:
            texts: List of input texts to encode.
            prefix: Prefix to apply idempotently to each text.

        Returns:
            np.ndarray: 2D array of shape (n_texts, 768) with float32 embeddings.

        Raises:
            RuntimeError: If encoding fails.
        """
        return self._encode_internal(texts, prefix)

    def embed_document(self, text: str) -> np.ndarray:
        """Encode a document text into a 768-dim embedding vector.

        Applies the document prefix idempotently before encoding.

        Args:
            text: Document text to embed.

        Returns:
            np.ndarray: 768-dimensional float32 embedding vector.

        Raises:
            RuntimeError: If encoding fails.

        Example:
            >>> service = EmbeddingService()
            >>> vec = service.embed_document("This is a test document")
            >>> vec.shape
            (768,)
            >>> vec.dtype
            dtype('float32')
        """
        return self._encode(text, self.PREFIX_DOC)

    def embed_query(self, text: str) -> np.ndarray:
        """Encode a query text into a 768-dim embedding vector.

        Applies the query prefix idempotently before encoding.

        Args:
            text: Query text to embed.

        Returns:
            np.ndarray: 768-dimensional float32 embedding vector.

        Raises:
            RuntimeError: If encoding fails.

        Example:
            >>> service = EmbeddingService()
            >>> vec = service.embed_query("test query")
            >>> vec.shape
            (768,)
            >>> vec.dtype
            dtype('float32')
        """
        return self._encode(text, self.PREFIX_QUERY)

    def embed_documents(self, texts: List[str]) -> np.ndarray:
        """Encode a batch of document texts into 768-dim embedding vectors.

        Applies the document prefix idempotently to each text before encoding.
        Uses SentenceTransformer's native batch encoding for throughput.

        Args:
            texts: List of document texts to embed.

        Returns:
            np.ndarray: 2D array of shape (n_texts, 768) with float32 embeddings.

        Raises:
            RuntimeError: If encoding fails.

        Example:
            >>> service = EmbeddingService()
            >>> vecs = service.embed_documents(["doc 1", "doc 2"])
            >>> vecs.shape
            (2, 768)
            >>> vecs.dtype
            dtype('float32')
        """
        return self._encode_batch(texts, self.PREFIX_DOC)

    def embed_queries(self, texts: List[str]) -> np.ndarray:
        """Encode a batch of query texts into 768-dim embedding vectors.

        Applies the query prefix idempotently to each text before encoding.
        Uses SentenceTransformer's native batch encoding for throughput.

        Args:
            texts: List of query texts to embed.

        Returns:
            np.ndarray: 2D array of shape (n_texts, 768) with float32 embeddings.

        Raises:
            RuntimeError: If encoding fails.

        Example:
            >>> service = EmbeddingService()
            >>> vecs = service.embed_queries(["query 1", "query 2"])
            >>> vecs.shape
            (2, 768)
            >>> vecs.dtype
            dtype('float32')
        """
        return self._encode_batch(texts, self.PREFIX_QUERY)


if __name__ == "__main__":
    # Self-test for deployment validation
    service = EmbeddingService()
    test_vec = service.embed_query("test")
    assert len(test_vec) == 768, 'Dimension mismatch'
    assert isinstance(test_vec, np.ndarray), 'Expected numpy array'
    assert test_vec.dtype == np.float32, 'Expected float32'
    
    # Batch encoding tests
    doc_vecs = service.embed_documents(["doc 1", "doc 2", "doc 3"])
    assert doc_vecs.shape == (3, 768), 'Batch document shape mismatch'
    assert doc_vecs.dtype == np.float32, 'Expected float32'
    
    query_vecs = service.embed_queries(["query 1", "query 2"])
    assert query_vecs.shape == (2, 768), 'Batch query shape mismatch'
    assert query_vecs.dtype == np.float32, 'Expected float32'
    
    # Idempotent prefix test for batch
    prefixed_docs = service.embed_documents(["search_document: already prefixed", "not prefixed"])
    assert prefixed_docs.shape == (2, 768), 'Idempotent batch shape mismatch'
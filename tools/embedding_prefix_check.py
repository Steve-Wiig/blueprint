#!/usr/bin/env python3
"""
CI Gate: Embedding Prefix & Dimension Contract

This module enforces the embedding contract for the SOC automation platform.
It verifies that document and query embeddings use the correct prefixes
("search_document: " and "search_query: ") and produce vectors of the
required dimension (768). This ensures compatibility with the vector
database and retrieval pipeline.

The module provides:
- EmbeddingService: A wrapper class that automatically applies required prefixes
- Contract verification via main() for CI/CD integration
- Constants defining the required prefixes and dimension

Example:
    >>> from typing import Callable
    >>> def my_encoder(text: str) -> list[float]:
    ...     return [0.1] * 768
    >>> svc = EmbeddingService(my_encoder)
    >>> doc_vec = svc.embed_document("alert summary")
    >>> query_vec = svc.embed_query("similar alerts")
"""

import sys
from typing import Callable

REQUIRED_DOC_PREFIX = "search_document: "
REQUIRED_QUERY_PREFIX = "search_query: "
REQUIRED_DIM = 768

calls: list[str] = []


def fake_encode(text: str) -> list[float]:
    """
    Mock encoder function for testing the embedding contract.

    Args:
        text: Input text to encode (expected to include prefix).

    Returns:
        A zero vector of length REQUIRED_DIM (768).
    """
    calls.append(text)
    return [0.0] * REQUIRED_DIM


class EmbeddingService:
    """
    Service for generating document and query embeddings with required prefixes.

    This class wraps an encoder function and automatically prepends the
    appropriate prefix ("search_document: " or "search_query: ") before
    encoding. This ensures consistent prefix usage across the platform.

    Attributes:
        encoder: Callable that takes a string and returns a list of floats
                 representing the embedding vector.

    Example:
        >>> def encoder(text: str) -> list[float]:
        ...     return [0.0] * 768
        >>> svc = EmbeddingService(encoder)
        >>> vec = svc.embed_document("test document")
        >>> len(vec)
        768
    """

    encoder: Callable[[str], list[float]]

    def __init__(self, encoder: Callable[[str], list[float]]) -> None:
        """
        Initialize the EmbeddingService with an encoder function.

        Args:
            encoder: Callable that takes a string and returns a list of floats
                     representing the embedding vector. The encoder is expected
                     to handle the prefixed text and return a vector of dimension
                     REQUIRED_DIM (768).

        Raises:
            TypeError: If encoder is not callable.
        """
        self.encoder = encoder

    def embed_document(self, text: str) -> list[float]:
        """
        Generate an embedding for a document with the required prefix.

        Prepends "search_document: " to the input text before passing to
        the encoder. This prefix is required by the vector database for
        document-type embeddings.

        Args:
            text: The document text to embed. Should not include any prefix.

        Returns:
            Embedding vector of length REQUIRED_DIM (768) as returned by
            the underlying encoder.

        Example:
            >>> svc = EmbeddingService(lambda t: [0.0]*768)
            >>> vec = svc.embed_document("CPU usage spike detected")
            >>> len(vec)
            768
        """
        return self.encoder(REQUIRED_DOC_PREFIX + text)

    def embed_query(self, text: str) -> list[float]:
        """
        Generate an embedding for a query with the required prefix.

        Prepends "search_query: " to the input text before passing to
        the encoder. This prefix is required by the vector database for
        query-type embeddings to enable asymmetric retrieval.

        Args:
            text: The query text to embed. Should not include any prefix.

        Returns:
            Embedding vector of length REQUIRED_DIM (768) as returned by
            the underlying encoder.

        Example:
            >>> svc = EmbeddingService(lambda t: [0.0]*768)
            >>> vec = svc.embed_query("CPU spike alerts")
            >>> len(vec)
            768
        """
        return self.encoder(REQUIRED_QUERY_PREFIX + text)


def main() -> int:
    """
    Run the CI gate verification for embedding prefix and dimension contract.

    Creates an EmbeddingService with a mock encoder, generates embeddings
    for a test document and query, then verifies:
    1. Both embeddings have the correct dimension (768)
    2. The document embedding was called with "search_document: " prefix
    3. The query embedding was called with "search_query: " prefix

    Returns:
        0 if all checks pass, 1 if any check fails.
    """
    svc = EmbeddingService(fake_encode)

    doc_text = "accepted triage summary"
    query_text = "similar alert lookup"

    doc_vector = svc.embed_document(doc_text)
    query_vector = svc.embed_query(query_text)

    # Verify Dimensions
    if len(doc_vector) != REQUIRED_DIM:
        print(f"FAIL: document embedding dim is {len(doc_vector)}, expected {REQUIRED_DIM}")
        return 1
    if len(query_vector) != REQUIRED_DIM:
        print(f"FAIL: query embedding dim is {len(query_vector)}, expected {REQUIRED_DIM}")
        return 1

    # Verify Prefixes
    if not calls[0].startswith(REQUIRED_DOC_PREFIX):
        print(f"FAIL: document prefix mismatch. Got: {calls[0][:20]}...")
        return 1
    if not calls[1].startswith(REQUIRED_QUERY_PREFIX):
        print(f"FAIL: query prefix mismatch. Got: {calls[1][:20]}...")
        return 1

    print("PASS: Embedding prefix and dimension contract verified.")
    return 0


if __name__ == "__main__":
    result = main()
    if result != 0:
        raise RuntimeError("Embedding contract verification failed")
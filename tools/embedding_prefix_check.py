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
    >>> svc = EmbeddingService(lambda t: [0.0]*768)
    >>> doc_vec = svc.embed_document("alert summary")
    >>> len(doc_vec)
    768
    >>> query_vec = svc.embed_query("similar alerts")
    >>> len(query_vec)
    768
"""

import sys
import os
import argparse
import logging
from typing import Callable, Optional, Sequence
from collections.abc import Sequence as ABCSequence

DEFAULT_DOC_PREFIX = "search_document: "
DEFAULT_QUERY_PREFIX = "search_query: "
DEFAULT_DIM = 768

REQUIRED_DOC_PREFIX = os.getenv("EMBEDDING_DOC_PREFIX", DEFAULT_DOC_PREFIX)
REQUIRED_QUERY_PREFIX = os.getenv("EMBEDDING_QUERY_PREFIX", DEFAULT_QUERY_PREFIX)
REQUIRED_DIM = int(os.getenv("EMBEDDING_DIM", str(DEFAULT_DIM)))

calls: list[str] = []

logger = logging.getLogger(__name__)


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
        encoder: Callable that takes a string and returns a sequence of floats
                 representing the embedding vector.
        doc_prefix: Prefix to prepend for document embeddings.
        query_prefix: Prefix to prepend for query embeddings.
        strict: If True, validate that encoder returns vectors of REQUIRED_DIM.

    Example:
        >>> def encoder(text: str) -> list[float]:
        ...     return [0.0] * 768
        >>> svc = EmbeddingService(encoder)
        >>> vec = svc.embed_document("test document")
        >>> len(vec)
        768
    """

    encoder: Callable[[str], list[float]]
    doc_prefix: str
    query_prefix: str
    strict: bool
    expected_dim: int

    def __init__(
        self,
        encoder: Callable[[str], list[float]],
        doc_prefix: Optional[str] = None,
        query_prefix: Optional[str] = None,
        strict: bool = False,
        expected_dim: Optional[int] = None,
    ) -> None:
        """
        Initialize the EmbeddingService with an encoder function.

        Args:
            encoder: Callable that takes a string and returns a sequence of floats
                     representing the embedding vector. The encoder is expected
                     to handle the prefixed text and return a vector of dimension
                     REQUIRED_DIM (768) unless a different expected_dim is provided.
            doc_prefix: Optional prefix for document embeddings. Defaults to
                        REQUIRED_DOC_PREFIX from environment or default.
            query_prefix: Optional prefix for query embeddings. Defaults to
                          REQUIRED_QUERY_PREFIX from environment or default.
            strict: If True, validate that encoder returns vectors of the expected
                    dimension. If False (default), no dimension validation is performed.
            expected_dim: Expected dimension for validation when strict=True.
                          Defaults to REQUIRED_DIM from environment or default.

        Raises:
            TypeError: If encoder is not callable.
        """
        if not callable(encoder):
            raise TypeError("encoder must be callable")
        self.encoder = encoder
        self.doc_prefix = doc_prefix if doc_prefix is not None else REQUIRED_DOC_PREFIX
        self.query_prefix = query_prefix if query_prefix is not None else REQUIRED_QUERY_PREFIX
        self.strict = strict
        self.expected_dim = expected_dim if expected_dim is not None else REQUIRED_DIM

    def _validate_dimension(self, vector: Sequence[float], context: str) -> None:
        """
        Validate that the embedding vector has the expected dimension.

        Args:
            vector: The embedding vector to validate.
            context: Description of the context (e.g., "document", "query").

        Raises:
            ValueError: If strict mode is enabled and vector dimension doesn't match expected_dim.
        """
        if self.strict and len(vector) != self.expected_dim:
            raise ValueError(
                f"{context} embedding dimension is {len(vector)}, expected {self.expected_dim}"
            )

    def embed_document(self, text: str) -> list[float]:
        """
        Generate an embedding for a document with the required prefix.

        Prepends the document prefix to the input text before passing to
        the encoder. This prefix is required by the vector database for
        document-type embeddings.

        Args:
            text: The document text to embed. Should not include any prefix.

        Returns:
            Embedding vector of length REQUIRED_DIM (768) as returned by
            the underlying encoder.

        Raises:
            ValueError: If strict mode is enabled and encoder returns a vector
                        with incorrect dimension.

        Example:
            >>> svc = EmbeddingService(lambda t: [0.0]*768)
            >>> vec = svc.embed_document("CPU usage spike detected")
            >>> len(vec)
            768
        """
        vector = self.encoder(f'{self.doc_prefix}{text}')
        self._validate_dimension(vector, "document")
        return list(vector)

    def embed_query(self, text: str) -> list[float]:
        """
        Generate an embedding for a query with the required prefix.

        Prepends the query prefix to the input text before passing to
        the encoder. This prefix is required by the vector database for
        query-type embeddings to enable asymmetric retrieval.

        Args:
            text: The query text to embed. Should not include any prefix.

        Returns:
            Embedding vector of length REQUIRED_DIM (768) as returned by
            the underlying encoder.

        Raises:
            ValueError: If strict mode is enabled and encoder returns a vector
                        with incorrect dimension.

        Example:
            >>> svc = EmbeddingService(lambda t: [0.0]*768)
            >>> vec = svc.embed_query("CPU spike alerts")
            >>> len(vec)
            768
        """
        vector = self.encoder(f'{self.query_prefix}{text}')
        self._validate_dimension(vector, "query")
        return list(vector)
def run_verification(
    dry_run: bool = False,
    doc_prefix: Optional[str] = None,
    query_prefix: Optional[str] = None,
    dim: Optional[int] = None,
) -> int:
    """
    Run the CI gate verification for embedding prefix and dimension contract.

    Args:
        dry_run: If True, skip actual encoding calls and only verify service
                 instantiation and constants.
        doc_prefix: Override document prefix for verification.
        query_prefix: Override query prefix for verification.
        dim: Override dimension for verification.

    Returns:
        0 if all checks pass, 1 if any check fails.
    """
    effective_doc_prefix = doc_prefix or REQUIRED_DOC_PREFIX
    effective_query_prefix = query_prefix or REQUIRED_QUERY_PREFIX
    effective_dim = dim or REQUIRED_DIM

    svc = EmbeddingService(
        fake_encode,
        doc_prefix=effective_doc_prefix,
        query_prefix=effective_query_prefix,
        strict=True,
        expected_dim=effective_dim,
    )

    if dry_run:
        logger.info("DRY-RUN: EmbeddingService instantiated successfully.")
        logger.info("DRY-RUN: Required document prefix: '%s'", effective_doc_prefix)
        logger.info("DRY-RUN: Required query prefix: '%s'", effective_query_prefix)
        logger.info("DRY-RUN: Required dimension: %d", effective_dim)
        logger.info("PASS: Dry-run verification completed.")
        return 0

    doc_text = "accepted triage summary"
    query_text = "similar alert lookup"

    doc_vector = svc.embed_document(doc_text)
    query_vector = svc.embed_query(query_text)

    # Verify Dimensions
    if len(doc_vector) != effective_dim:
        logger.error("FAIL: document embedding dim is %d, expected %d", len(doc_vector), effective_dim)
        return 1
    if len(query_vector) != effective_dim:
        logger.error("FAIL: query embedding dim is %d, expected %d", len(query_vector), effective_dim)
        return 1

    # Verify Prefixes
    if not calls[0].startswith(effective_doc_prefix):
        logger.error("FAIL: document prefix mismatch. Got: %s...", calls[0][:20])
        return 1
    if not calls[1].startswith(effective_query_prefix):
        logger.error("FAIL: query prefix mismatch. Got: %s...", calls[1][:20])
        return 1

    logger.info("PASS: Embedding prefix and dimension contract verified.")
    return 0


def main() -> int:
    """
    Parse arguments and run the CI gate verification.

    This is the CLI entry point for the embedding contract verification tool.
    Intended for direct script execution and CI/CD pipeline integration.

    Returns:
        0 if all checks pass, 1 if any check fails.
    """
    parser = argparse.ArgumentParser(
        description="Verify embedding prefix and dimension contract"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip actual encoding calls, only verify service instantiation and constants"
    )
    parser.add_argument(
        "--doc-prefix",
        type=str,
        default=None,
        help=f"Document prefix (default: {DEFAULT_DOC_PREFIX!r}, env: EMBEDDING_DOC_PREFIX)"
    )
    parser.add_argument(
        "--query-prefix",
        type=str,
        default=None,
        help=f"Query prefix (default: {DEFAULT_QUERY_PREFIX!r}, env: EMBEDDING_QUERY_PREFIX)"
    )
    parser.add_argument(
        "--dim",
        type=int,
        default=None,
        help=f"Embedding dimension (default: {DEFAULT_DIM}, env: EMBEDDING_DIM)"
    )
    args = parser.parse_args()

    doc_prefix = (
        args.doc_prefix
        if args.doc_prefix is not None
        else os.getenv("EMBEDDING_DOC_PREFIX", DEFAULT_DOC_PREFIX)
    )
    query_prefix = (
        args.query_prefix
        if args.query_prefix is not None
        else os.getenv("EMBEDDING_QUERY_PREFIX", DEFAULT_QUERY_PREFIX)
    )
    dim = (
        args.dim
        if args.dim is not None
        else int(os.getenv("EMBEDDING_DIM", str(DEFAULT_DIM)))
    )

    return run_verification(
        dry_run=args.dry_run,
        doc_prefix=doc_prefix,
        query_prefix=query_prefix,
        dim=dim,
    )
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
        stream=sys.stdout
    )
    result = main()
    if result != 0:
        raise RuntimeError("Embedding contract verification failed")
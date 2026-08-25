"""Memory context stitcher for SOC orchestrator. Retrieves semantically similar cases for SLM injection."""
import psycopg2
import sys
from datetime import datetime, timezone, timedelta
from typing import TypedDict


# Module-level connection cache for connection pooling/reuse
_PG_CONN = None

def _get_pg_conn():
    """Get or create a cached PostgreSQL connection."""
    global _PG_CONN
    if _PG_CONN is None or getattr(_PG_CONN, 'closed', True):
        _PG_CONN = psycopg2.connect(dbname="soc_db", user="orchestrator")
    return _PG_CONN


class DatabaseError(Exception):
    """Custom exception for database-related failures in stitch_memory_context."""
    pass


class StitcherError(Exception):
    """Custom exception for stitching logic failures in stitch_memory_context."""
    pass


class MemoryMetadata(TypedDict):
    """Type definition for memory retrieval metadata."""
    memory_retrieval_timestamp: str
    retrieved_case_ids: list[str]
    top_k_requested: int
    max_age_days: int


def stitch_memory_context(query_embedding: list[float], top_k: int = 5, max_age_days: int = 30) -> tuple[str, MemoryMetadata]:
    """
    Queries case_embeddings for semantic recall and formats for SLM injection.

    Args:
        query_embedding: List of floats representing the query vector for cosine similarity search.
        top_k: Maximum number of similar cases to retrieve. Defaults to 5.
        max_age_days: Maximum age of cases to consider in days. Defaults to 30.

    Returns:
        A tuple containing:
        - formatted_context (str): XML-formatted string with retrieved case summaries and distances.
        - metadata (MemoryMetadata): Dictionary with retrieval metadata including timestamp, case IDs, and parameters.

    Raises:
        DatabaseError: If a psycopg2 database error occurs during query execution or connection.
        StitcherError: If an unexpected error occurs during memory context stitching.
    """
    try:
        conn = _get_pg_conn()
        cur = conn.cursor()

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=max_age_days)

        query = """
            SELECT case_id, summary, cosine_distance(embedding, %s::vector) as dist
            FROM case_embeddings
            WHERE created_at >= %s
            ORDER BY dist ASC
            LIMIT %s;
        """

        cur.execute(query, (query_embedding, cutoff_date, top_k))
        results = cur.fetchall()

        context_blocks = [f"<case_id={r[0]} dist={r[2]:.4f}>{r[1]}</case_id>" for r in results]
        case_refs = [r[0] for r in results]
            
        formatted_context = f"<memory_context>\n{''.join(context_blocks)}\n</memory_context>"
        metadata: MemoryMetadata = {
            "memory_retrieval_timestamp": datetime.now(timezone.utc).isoformat(),
            "retrieved_case_ids": case_refs,
            "top_k_requested": top_k,
            "max_age_days": max_age_days
        }
        
        cur.close()
        # Connection stays open for reuse (module-level cache)
        return formatted_context, metadata

    except psycopg2.Error as e:
        raise DatabaseError(f"Failed to retrieve memory context from database: {e}") from e
    except Exception as e:
        raise StitcherError(f"Unexpected error during memory context stitching: {e}") from e

if __name__ == "__main__":
    # Example usage for orchestrator integration
    # embedding = [0.12, -0.05, ...]
    # context, meta = stitch_memory_context(embedding)
    # print(context)
    pass
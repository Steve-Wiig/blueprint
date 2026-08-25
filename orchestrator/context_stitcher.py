"""Memory context stitcher for SOC orchestrator. Retrieves semantically similar cases for SLM injection."""
import psycopg2
import sys
from datetime import datetime, timezone, timedelta
from typing import TypedDict, Optional
from xml.sax.saxutils import escape


# Module-level connection cache for connection pooling/reuse
_PG_CONN = None
_PG_CONN_PARAMS = None


def configure_connection(dbname: str = "soc_db", user: str = "orchestrator", **kwargs) -> None:
    """Configure database connection parameters. Call before first use or let defaults apply."""
    global _PG_CONN_PARAMS, _PG_CONN
    _PG_CONN_PARAMS = {"dbname": dbname, "user": user, **kwargs}
    # Reset cached connection so new params take effect
    if _PG_CONN is not None:
        try:
            _PG_CONN.close()
        except Exception:
            pass
        _PG_CONN = None


def _get_pg_conn():
    """Get or create a cached PostgreSQL connection."""
    global _PG_CONN, _PG_CONN_PARAMS
    if _PG_CONN is None or getattr(_PG_CONN, 'closed', True):
        if _PG_CONN_PARAMS is None:
            _PG_CONN_PARAMS = {"dbname": "soc_db", "user": "orchestrator"}
        _PG_CONN = psycopg2.connect(**_PG_CONN_PARAMS)
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


def stitch_memory_context(
    query_embedding: list[float],
    top_k: int = 5,
    max_age_days: int = 30,
    conn: Optional[psycopg2.extensions.connection] = None
) -> tuple[str, MemoryMetadata]:
    """
    Queries case_embeddings for semantic recall and formats for SLM injection.

    Args:
        query_embedding: List of floats representing the query vector for cosine similarity search.
        top_k: Maximum number of similar cases to retrieve. Defaults to 5.
        max_age_days: Maximum age of cases to consider in days. Defaults to 30.
        conn: Optional psycopg2 connection to use. If not provided, uses module-level cached connection.

    Returns:
        A tuple containing:
        - formatted_context (str): XML-formatted string with retrieved case summaries and distances.
        - metadata (MemoryMetadata): Dictionary with retrieval metadata including timestamp, case IDs, and parameters.

    Raises:
        DatabaseError: If a psycopg2 database error occurs during query execution or connection.
        StitcherError: If an unexpected error occurs during memory context stitching.
    """
    use_cached = conn is None
    if use_cached:
        conn = _get_pg_conn()
    
    cur = None
    try:
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

        context_blocks = [f"<case_id={r[0]} dist={r[2]:.4f}>{escape(r[1])}</case_id>" for r in results]
        case_refs = [r[0] for r in results]
            
        formatted_context = f"<memory_context>\n{''.join(context_blocks)}\n</memory_context>"
        metadata: MemoryMetadata = {
            "memory_retrieval_timestamp": datetime.now(timezone.utc).isoformat(),
            "retrieved_case_ids": case_refs,
            "top_k_requested": top_k,
            "max_age_days": max_age_days
        }
        
        return formatted_context, metadata

    except psycopg2.Error as e:
        raise DatabaseError(f"Failed to retrieve memory context from database: {e}") from e
    except Exception as e:
        raise StitcherError(f"Unexpected error during memory context stitching: {e}") from e
    finally:
        if cur is not None:
            cur.close()
        # Don't close cached connection; only close if caller provided their own
        if not use_cached and conn is not None:
            try:
                conn.close()
            except Exception:
                pass


if __name__ == "__main__":
    # Example usage for orchestrator integration
    # embedding = [0.12, -0.05, ...]
    # context, meta = stitch_memory_context(embedding)
    # print(context)
    pass
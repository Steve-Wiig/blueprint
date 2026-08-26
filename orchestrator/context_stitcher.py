import psycopg2
import psycopg2.extensions
import psycopg2.pool
import sys
import hashlib
from datetime import datetime, timezone, timedelta
from typing import TypedDict, Optional
from xml.sax.saxutils import escape


# Module-level connection pool for connection pooling/reuse
_PG_POOL: Optional[psycopg2.pool.ThreadedConnectionPool] = None
_PG_POOL_PARAMS: Optional[dict] = None
_PG_POOL_MINCONN = 1
_PG_POOL_MAXCONN = 10


def configure_connection(
    dbname: str = "soc_db",
    user: str = "orchestrator",
    minconn: int = 1,
    maxconn: int = 10,
    **kwargs
) -> None:
    """Configure database connection pool parameters. Call before first use or let defaults apply."""
    global _PG_POOL, _PG_POOL_PARAMS, _PG_POOL_MINCONN, _PG_POOL_MAXCONN
    _PG_POOL_PARAMS = {"dbname": dbname, "user": user, **kwargs}
    _PG_POOL_MINCONN = minconn
    _PG_POOL_MAXCONN = maxconn
    # Reset cached pool so new params take effect
    if _PG_POOL is not None:
        try:
            _PG_POOL.closeall()
        except Exception:
            pass
        _PG_POOL = None


def _get_pg_pool() -> psycopg2.pool.ThreadedConnectionPool:
    """Get or create a cached PostgreSQL connection pool."""
    global _PG_POOL, _PG_POOL_PARAMS, _PG_POOL_MINCONN, _PG_POOL_MAXCONN
    if _PG_POOL is None:
        if _PG_POOL_PARAMS is None:
            _PG_POOL_PARAMS = {"dbname": "soc_db", "user": "orchestrator"}
        _PG_POOL = psycopg2.pool.ThreadedConnectionPool(
            minconn=_PG_POOL_MINCONN,
            maxconn=_PG_POOL_MAXCONN,
            **_PG_POOL_PARAMS
        )
    return _PG_POOL


def _get_pg_conn() -> psycopg2.extensions.connection:
    """Acquire a connection from the pool."""
    pool = _get_pg_pool()
    return pool.getconn()


def _put_pg_conn(conn: psycopg2.extensions.connection) -> None:
    """Return a connection to the pool."""
    global _PG_POOL
    if _PG_POOL is not None:
        try:
            _PG_POOL.putconn(conn)
        except Exception:
            # If pool is closed or error, close the connection directly
            try:
                conn.close()
            except Exception:
                pass


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


def _compute_query_hash(query_embedding: list[float]) -> str:
    """Compute a deterministic SHA256 hash of the query embedding for audit logging."""
    # Use a stable string representation of the embedding
    embedding_str = ",".join(f"{x:.8f}" for x in query_embedding)
    return hashlib.sha256(embedding_str.encode()).hexdigest()


def _log_audit(
    conn: psycopg2.extensions.connection,
    retrieval_timestamp: datetime,
    query_hash: str,
    case_ids: list[str],
    top_k: int,
    max_age_days: int
) -> None:
    """Insert an audit log entry for the memory retrieval operation."""
    cur = None
    try:
        cur = conn.cursor()
        audit_query = """
            INSERT INTO memory_retrieval_audit (retrieval_timestamp, query_hash, case_ids, top_k, max_age_days)
            VALUES (%s, %s, %s, %s, %s);
        """
        cur.execute(audit_query, (retrieval_timestamp, query_hash, case_ids, top_k, max_age_days))
        conn.commit()
    except psycopg2.Error:
        # Audit logging failure should not break the main operation
        # Rollback any partial transaction and ignore
        try:
            conn.rollback()
        except Exception:
            pass
    except Exception:
        # Ignore any other unexpected errors in audit logging
        pass
    finally:
        if cur is not None:
            cur.close()


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
        conn: Optional psycopg2 connection to use. If not provided, acquires from module-level pool.

    Returns:
        A tuple containing:
        - formatted_context (str): XML-formatted string with retrieved case summaries and distances.
        - metadata (MemoryMetadata): Dictionary with retrieval metadata including timestamp, case IDs, and parameters.

    Raises:
        DatabaseError: If a psycopg2 database error occurs during query execution or connection.
        StitcherError: If an unexpected error occurs during memory context stitching.
    """
    use_pool = conn is None
    if use_pool:
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
        retrieval_timestamp = datetime.now(timezone.utc)
        metadata: MemoryMetadata = {
            "memory_retrieval_timestamp": retrieval_timestamp.isoformat(),
            "retrieved_case_ids": case_refs,
            "top_k_requested": top_k,
            "max_age_days": max_age_days
        }

        # Audit logging after successful retrieval
        query_hash = _compute_query_hash(query_embedding)
        _log_audit(conn, retrieval_timestamp, query_hash, case_refs, top_k, max_age_days)
        
        return formatted_context, metadata

    except psycopg2.Error as e:
        raise DatabaseError(f"Failed to retrieve memory context from database: {e}") from e
    except Exception as e:
        raise StitcherError(f"Unexpected error during memory context stitching: {e}") from e
    finally:
        if cur is not None:
            cur.close()
        # Return connection to pool if we acquired it; close if caller provided their own
        if use_pool and conn is not None:
            _put_pg_conn(conn)
        elif not use_pool and conn is not None:
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
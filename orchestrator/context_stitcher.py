"""Context stitcher for SOC orchestrator. Retrieves semantic memory from case_embeddings for SLM injection."""
import psycopg2
import sys
from datetime import datetime, timezone, timedelta


class DatabaseError(Exception):
    """Custom exception for database-related failures in stitch_memory_context."""
    pass


class StitcherError(Exception):
    """Custom exception for stitching logic failures in stitch_memory_context."""
    pass


def stitch_memory_context(query_embedding: list[float], top_k: int = 5, max_age_days: int = 30) -> tuple[str, dict]:
    """
    Queries case_embeddings for semantic recall and formats for SLM injection.
    Returns tuple: (formatted_string, metadata_dict)
    """
    try:
        conn = psycopg2.connect(dbname="soc_db", user="orchestrator")
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

        context_blocks = []
        case_refs = []

        for row in results:
            case_id, summary, dist = row
            context_blocks.append(f"<case_id={case_id} dist={dist:.4f}>{summary}</case_id>")
            case_refs.append(case_id)
            
        formatted_context = f"<memory_context>\n{''.join(context_blocks)}\n</memory_context>"
        metadata = {
            "memory_retrieval_timestamp": datetime.now(timezone.utc).isoformat(),
            "retrieved_case_ids": case_refs,
            "top_k_requested": top_k,
            "max_age_days": max_age_days
        }
        
        cur.close()
        conn.close()
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
import psycopg2
import json
import sys
from datetime import datetime, timezone, timedelta

def stitch_memory_context(query_embedding, top_k=5, max_age_days=30):
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
        
        cur.execute(query, (json.dumps(query_embedding), cutoff_date, top_k))
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
        sys.stderr.write(f"Database error: {e}")
        raise RuntimeError(f"Library code called exit(1)")
    except Exception as e:
        sys.stderr.write(f"Stitcher error: {e}")
        raise RuntimeError(f"Library code called exit(2)")

if __name__ == "__main__":
    # Example usage for orchestrator integration
    # embedding = [0.12, -0.05, ...]
    # context, meta = stitch_memory_context(embedding)
    # print(context)
    sys.exit(0)
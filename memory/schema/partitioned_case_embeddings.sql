-- LOCAL-SOC-SLM Blueprint v11.6.0: Partitioned Vector Memory DDL

-- 1. Base Table Definition
CREATE TABLE case_embeddings (
    id UUID DEFAULT gen_random_uuid(),
    source_id TEXT NOT NULL,
    case_ref TEXT NOT NULL,
    embedding VECTOR(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB,
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

-- 2. Metadata Indexes (Parent table ensures propagation to partitions)
CREATE INDEX idx_case_embeddings_source_id ON case_embeddings (source_id);
CREATE INDEX idx_case_embeddings_case_ref ON case_embeddings (case_ref);
CREATE INDEX idx_case_embeddings_created_at ON case_embeddings (created_at);

-- 3. Partition Lifecycle Management (Example: Current Month)
-- Note: In production, use pg_partman to automate these ranges.
CREATE TABLE case_embeddings_y2025m05 PARTITION OF case_embeddings
    FOR VALUES FROM ('2025-05-01 00:00:00') TO ('2025-06-01 00:00:00');

-- 4. HNSW Index (Active Partition Only per Section 36.2)
-- This index is isolated to the active partition to prevent memory exhaustion.
CREATE INDEX idx_case_embeddings_y2025m05_hnsw ON case_embeddings_y2025m05 
USING hnsw (embedding vector_cosine_ops);

-- 5. Partition Pruning Query Pattern (Section 36.3)
-- To ensure partition pruning and HNSW utilization, the query must target the 
-- specific active partition range. Querying across multiple partitions will 
-- trigger sequential scans on older partitions.

-- Pattern for Active Partition Search:
SELECT source_id, case_ref, embedding <=> $query_embedding AS distance
FROM case_embeddings
WHERE created_at >= date_trunc('month', now())
ORDER BY embedding <=> $query_embedding
LIMIT 5;

-- Pattern for Historical Search (Sequential Scan / Metadata Filter):
SELECT source_id, case_ref, embedding <=> $query_embedding AS distance
FROM case_embeddings
WHERE created_at >= '2025-01-01' AND created_at < '2025-02-01'
ORDER BY embedding <=> $query_embedding
LIMIT 5;

-- 6. Maintenance Note:
-- Older partitions (e.g., y2025m04) should have their HNSW indexes dropped 
-- via: DROP INDEX IF EXISTS idx_case_embeddings_y2025m04_hnsw;
-- to reclaim memory while keeping the data queryable via metadata indexes.
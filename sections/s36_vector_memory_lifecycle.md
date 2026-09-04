SOURCE: soc-autopilot (historical)
BLOCK:  SECTION 36: TIME-PARTITIONED VECTOR MEMORY
SHA256: 28448ce20cadd3df
────────────────────────────────────────────────────────────────────────

36.0 Purpose
As case_embeddings grows, an unpartitioned HNSW index may consume increasing
memory and compete with inference workloads on consumer hardware.
Section 36 defines time-partitioned vector memory management.
36.1 Partitioning policy
case_embeddings may be implemented as a declarative range-partitioned table
by created_at.
Partitioning goals:
Keep active vector search focused on recent operational memory.
Limit HNSW memory pressure on consumer hardware.
Allow older partitions to drop vector indexes while remaining
queryable by sequential scan or metadata indexes.
Align vector retention with the 90-day operational IOC window where
appropriate, while preserving longer-term accepted corrections under
separate retention policy.
36.2 Index lifecycle
Index policy:
For low-volume operation, exact sequential scan is acceptable.
When indexing is required, HNSW is preferred over IVFFlat for dynamic
inserts.
HNSW indexes may be attached only to active partitions.
Older partitions may have their HNSW indexes dropped during retention
maintenance.
Index attachment, detachment, and benchmark results must be recorded
in Appendix N and migration history.
Recommended active-window default:
Last 30 to 90 days.
Older partitions may remain queryable, but top-k operational recall should
normally target the active window.
36.3 Query pattern
Operational top-k queries should filter by created_at so PostgreSQL can prune
partitions.
Example:
SELECT source_id, case_ref, embedding <=> $query_embedding AS distance
FROM case_embeddings
WHERE created_at >= now() - interval '90 days'
ORDER BY embedding <=> $query_embedding
LIMIT 5;
36.4 Retention and archive
Partition retention must follow the archive-first rule:
Archive to CMR HDD before dropping a partition.
Vector partitions containing accepted corrections or long-term training-derived
memory must not be dropped unless explicitly covered by an approved retention
class.
36.5 Acceptance criteria
case_embeddings partitioning is reproducible from migration files.
Active partition index strategy is benchmarked and recorded.
Top-k recall remains within policy on the active window.
Older partitions can be queried without requiring full HNSW indexes.
Index memory usage does not destabilize inference or embedding workers.


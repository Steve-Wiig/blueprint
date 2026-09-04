SOURCE: soc-autopilot (historical)
BLOCK:  SECTION 32: DEPLOYMENT READINESS
SHA256: 96c41a1cb3e91a06
────────────────────────────────────────────────────────────────────────

32.0 Purpose
Section 32 establishes a formal register of what is known, what must be
verified in the lab, and what remains an open research question.
This blueprint does not promote external claims into normative requirements
unless they are directly supported by the supplied lineage or proven in the
lab.
All external integration behavior is treated as LAB-VERIFY until evidence is
recorded in Appendix N.
32.1 Verified internal baseline [VERIFIED-INTERNAL]
The following constraints are verified from the v11.3/v11.4/v11.5 lineage:
- Single NVIDIA GPU with 16GB VRAM is the primary hardware baseline.
- 64GB DDR5 is approved as the v1 starting configuration when operated in
serialized phases.
- 96GB DDR5 is preferred for concurrent operation.
- RAM upgrades use matched-kit replacement only.
- A future second GPU separates development and inference duties.
- A second GPU does not increase autonomy.
- The Enrichment Engine integrates Wazuh, Security Onion, Suricata,
TheHive, and pfSense.
- pfSense-adjacent mutations remain approval-gated.
- The engine never applies pfSense mutations autonomously.
- PostgreSQL stores orchestration state, not raw telemetry.
- SQLite stores ephemeral working state.
- handoffs and corrections are append-only.
- The engine role receives only INSERT and SELECT on append-only tables.
- Retention uses cron + partition drop after CMR HDD archive.
- Semantic recall uses pgvector with 768-dimensional embeddings.
- The embedding model is nomic-embed-text.
- Model adapters must be signed.
- Adapter promotion requires replay-mix evaluation.
- Adapter promotion requires canary evaluation.
- Rollback must be atomic and immediate.
- Autonomous online tuning is prohibited.
- Asynchronous ingestion must decouple intake from inference.
- High-entropy unknown tokens must be redacted or quarantined.
- Hash-chain generation must be serialized.
- Embedding prefix injection must be idempotent.
- Master documentation must pass completeness checks.
- Wiki generation is append-only or draft-only and sanitized before commit.
32.2 External lab-validation dependencies [LAB-VERIFY]
pfSense API surface:
Verify exact pfSense version, API availability, endpoint paths,
authentication model, alias read/draft/apply behavior, and least-privilege
credential options.
Stock pfSense CE/Plus may not provide the required REST API out of the box.
Lab verification may require the community-maintained pfSense-pkg-RESTAPI
package or equivalent. API keys must be strictly scoped to alias read/draft
endpoints where possible.
Wazuh API and RBAC:
Verify read-only role behavior, required alert/rule/agent read permissions,
and denial of manager mutation or restart operations.
Security Onion / OpenSearch access:
Verify whether OpenSearch API access is direct or mediated by Security
Onion, and verify read-only query permissions without destructive rights.
TheHive API:
Verify TheHive major version, API authentication, organization/permission
model, case creation behavior, observable behavior, and safe writeback
boundaries.
Suricata EVE:
Verify EVE JSON schema version, event normalization, file rotation, intake
mechanism, and sanitization requirements.
Embedding model behavior:
Verify exact nomic-embed-text artifact, dimension, normalization, prefix
behavior, and prefix idempotency.
Vector index behavior:
Benchmark sequential scan, HNSW, and IVFFlat against recall, latency,
insert behavior, memory usage, and maintenance cost.
Time-partitioned vector behavior [v11.5]:
Verify partition pruning, active-partition HNSW behavior, index attachment
and detachment, and top-k recall over the active window.
Inference serving behavior:
Verify serving backend, quantization, context limits, parallelism, VRAM
usage, adapter loading, and rollback behavior.
Dynamic VRAM detection [v11.5]:
Verify nvidia-smi/NVML detection, total GPU memory, 90% safety cap, and
workload-based peak measurement.
Sanitization behavior:
Verify regex and entropy redaction coverage, false-negative tolerance,
quarantine behavior, allowlist behavior, field-aware command-line handling,
and audit metadata.
payload_ref storage:
Verify canonical URI behavior, artifact integrity, retrieval, retention,
and access control.
Asynchronous queue behavior [v11.5]:
Verify queue depth thresholds, severity prioritization, shedding behavior,
dead-letter behavior, worker concurrency limits, lease expiration, and
stale-job recovery.
Hash-chain behavior [v11.5, amended by v11.5.1]:
Verify chain calculation, tamper detection, anchoring, recovery behavior,
and concurrency safety.
Documentation completeness [v11.5.2]:
Verify Appendix M subsections, amendment text, Appendix O skeletons,
Appendix P templates, Appendix N register, changelog entries, and
END OF DOCUMENT marker are present.
Wiki generation behavior [v11.6]:
Verify Wiki task queue priority, sanitization, verifier gating, Git commit
recording, and failure handling.
32.3 Research spikes
Spike 1 — Firewall API feasibility:
Prove safe pfSense table read and alias draft behavior in a lab firewall.
Spike 2 — Read-only credential proof:
Prove Wazuh, OpenSearch/Security Onion, and TheHive credentials can read
required data but cannot perform prohibited mutations.
Spike 3 — Embedding correctness:
Prove embedding prefix policy, dimension, normalization, top-k recall, and
prefix idempotency.
Spike 4 — Inference and VRAM budget:
Prove the selected serving stack remains stable under the approved context
length and concurrency limits on 16GB VRAM.
Spike 5 — Append-only memory proof:
Prove Postgres migration reproducibility, append-only grants, and CI drift
detection.
Spike 6 — Sanitization and payload_ref proof:
Prove sensitive payloads are redacted or quarantined and large artifacts
are referenced safely.
Spike 7 — Replay/canary proof:
Prove replay-mix evaluation and canary rollback work end-to-end.
Spike 8 — Async backpressure proof [v11.5]:
Prove queue behavior under alert burst, shedding, dead-letter, severity
prioritization, lease expiration, and stale-job recovery.
Spike 9 — Partitioned vector memory proof [v11.5]:
Prove partition pruning and active-partition HNSW behavior.
Spike 10 — Hash-chain proof [v11.5, amended by v11.5.1]:
Prove hash-chain verification, tamper detection, and serialized sealing
under concurrent inserts.
Spike 11 — Entropy sanitization proof [v11.5, amended by v11.5.1]:
Prove entropy detection does not over-redact approved IOC hashes, UUIDs,
request IDs, or adapter checksums, and proves quarantine-by-reference for
high-value command-line payloads.
Spike 12 — Dynamic VRAM detection proof [v11.5]:
Prove dynamic VRAM cap detection fails closed when GPU metrics are
unavailable.
Spike 13 — Stale queue recovery proof [v11.5.1]:
Prove crashed or timed-out workers do not leave jobs stuck in processing.
Spike 14 — Hash-chain concurrency proof [v11.5.1]:
Prove concurrent inserts do not corrupt chain order or create bottlenecks.
Spike 15 — Embedding prefix idempotency proof [v11.5.1]:
Prove repeated ingestion of already-prefixed text does not double-prefix.
Spike 16 — Documentation completeness proof [v11.5.2]:
Prove the master document contains all required appendices, amendments,
tool skeletons, templates, checklist, manifest, and termination marker.
Spike 17 — Operational Wiki proof [v11.6]:
Prove Wiki generation tasks are sanitized, verifier-gated, low-priority,
auditable, and safely shed under backpressure.
32.4 Go/no-go gates
Implementation must not proceed to production use until:
- All Tier 0 LAB-VERIFY items in Appendix N have passed.
- Credential permission proof has been archived.
- Embedding prefix behavior and idempotency have been validated.
- VRAM budget smoke check has passed.
- Append-only audit check has passed.
- Sanitization redaction, entropy, and field-policy checks have passed.
- payload_ref integrity check has passed.
- Adapter rollback drill has passed.
- Queue backpressure and stale recovery behavior have passed if async
intake is enabled.
- Hash-chain verification and concurrency behavior have passed if hash
chaining is enabled.
- Partitioned vector index behavior has passed if partitioning is enabled.
- Documentation completeness check has passed.
- Wiki sanitization and Git audit proof have passed if Wiki generation is
enabled.


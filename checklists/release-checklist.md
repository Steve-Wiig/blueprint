SOURCE: soc-autopilot
BLOCK:  FULL 2026.09.04 RELEASE CHECKLIST
SHA256: d46a2cbb2ee98f78
────────────────────────────────────────────────────────────────────────

2026.09.04 baseline checklist:
- AMEND-1 through AMEND-52 are applied.
- Executive Summary, How to Read This Document, Glossary, and Blueprint Layers
  are present.
- Section 38 Operational Knowledge Generation & Externalized Memory is present.
- Appendix Q Runbooks & Failure Mode Analysis is present.
- Appendix N includes R-117 Wiki sanitization and Git audit proof.
- Appendix O includes tools/wiki_sanitization_check.py.
- Appendix O includes Gate 16 Wiki Sanitization Check.
- Appendix P includes P.12 Wiki commit reference ledger template.
- All inherited v11.5.2 safety, queue, VRAM, sanitization, and hash-chain
  checks remain intact.
v11.5.2 baseline checklist:
- AMEND-1 through AMEND-46 are applied.
- Full amendment text for AMEND-1 through AMEND-41 is present.
- Section 30 includes v11.4 payload_ref, v11.5 partition/hash-chain
references, and v11.5.1 field-aware sanitization metadata.
- Section 31 includes replay-mix and canary requirements.
- Section 32 includes v11.5, v11.5.1, and v11.5.2 LAB-VERIFY dependencies.
- Section 33 uses dynamic VRAM detection.
- Section 34 uses two-pass sanitization and field-aware command-line
quarantine.
- Section 35 asynchronous ingestion contract is implemented.
- Section 35 stale-job recovery is implemented.
- Section 36 time-partitioned vector memory policy is recorded.
- Section 37 hash-chained audit ledger is implemented or explicitly waived.
- Section 37 hash-chain concurrency policy is implemented.
- Appendix M is full and includes M.0 through M.12.
- Appendix N includes R-001 through R-116.
- Appendix O includes v11.4, v11.5, v11.5.1, and v11.5.2 CI tool
requirements and skeletons.
- Appendix O includes explicit CI pipeline example.
- Appendix P includes production-hardening templates.
- Completeness manifest includes Appendix M subsections, amendment text,
Appendix O skeletons, CI examples, Appendix P templates, and END OF
DOCUMENT marker.
Operational checklist:
- case_embeddings partitioning strategy is recorded and benchmarked.
- HNSW indexes are applied only to approved active partitions.
- Async intake queue is implemented without introducing unauthorized new
services.
- Queue backpressure thresholds are configured and tested.
- Queue lease_expires_at and last_heartbeat_at columns exist.
- Stale job reaper recovers expired processing jobs.
- Jobs exceeding max_attempts move to failed or quarantined.
- Low-severity shedding is tested and audited.
- High-severity alerts are not silently dropped under backpressure.
- VRAM budget check dynamically detects GPU memory.
- VRAM budget check enforces a 90% ceiling unless explicitly overridden.
- Sanitizer performs regex pass and entropy pass.
- Sanitizer records sanitization_action.
- Entropy allowlists preserve known IOC hashes, UUIDs, request IDs, and
adapter checksums where appropriate.
- High-value suspicious command-line payloads are quarantined by reference
where inline redaction would destroy analytical value.
- handoffs and corrections are protected by append-only role restrictions.
- Hash-chain generation is serialized or sealed asynchronously.
- Concurrent inserts do not corrupt hash-chain order.
- audit_chain table or dedicated chain writer role is used.
- Hash-chain verifier passes on clean data.
- Hash-chain verifier detects tampering in test data.
- Latest chain hash is anchored in lab evidence.
- Embedding prefix wrapper is idempotent.
- Embedding prefix tests include double-prefix inputs.
- payload_ref integrity check passes.
- External credential permission proof passes.
- Memory schema migration drift check passes.
- Changelog terminates cleanly before END OF DOCUMENT.
- Documentation completeness check passes.
- Wiki generation tasks are queued at low priority if Wiki generation is
enabled.
- Wiki generation tasks shed safely under backpressure if Wiki generation is
enabled.
- Wiki commits are recorded in the handoff ledger if Wiki generation is
enabled.
Safety checklist:
- No autonomous online tuning path exists.
- No raw telemetry enters PostgreSQL.
- No engine credential has prohibited mutation rights.
- No pfSense mutation occurs without approval.
- No adapter is promoted without CI, replay-mix, canary, and approval.
- No ledger UPDATE/DELETE is permitted for engine role.
- No payload_ref artifact is trusted merely because it is referenced.
- No alert shedding event is silently discarded.
- No stale queue job remains stuck indefinitely.
- No unsanitized high-entropy payload is inserted into orchestration memory.
- No concurrent hash-chain writer corrupts audit sequence.
- No double-prefixed embedding text is passed to the embedding model.
- No required appendix, amendment, or checklist section is silently omitted.
- No SLM process writes directly to Wiki or normative documentation.
- No Wiki page is committed without sanitization and ledger provenance.


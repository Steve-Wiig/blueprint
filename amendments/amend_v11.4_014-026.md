SOURCE: soc-autopilot (historical)
BLOCK:  v11.4 AMENDMENTS TO PRESERVED v11.3 TEXT
SHA256: 8ba332da0edc3b4b
────────────────────────────────────────────────────────────────────────

AMEND-14 — Section 24.4, Orchestration CI checks
ADD the following v11.4 checks:
- External credential permission proof
tools/external_credential_permission_check.py
Verifies that engine credentials for Wazuh, OpenSearch/Security Onion,
TheHive, and pfSense lab endpoints can perform required read/draft actions
and are denied for prohibited mutation actions.
- Embedding prefix contract check
tools/embedding_prefix_check.py
Verifies that the embedding writer and retrieval query path apply the
required model-specific text prefixes, if the selected embedding model uses
instruction prefixes.
- Sanitization redaction check
tools/sanitization_redaction_check.py
Verifies that known secret patterns, PII test patterns, and unsafe payload
samples are blocked, redacted, or quarantined before insertion into
PostgreSQL.
- VRAM budget smoke check
tools/vram_budget_smoke_check.py, later replaced by dynamic VRAM governance
in v11.5.
- payload_ref integrity check
tools/payload_ref_integrity_check.py
Verifies that handoff rows using payload_ref contain canonical URI, sha256,
size_bytes, compression, sanitizer metadata, and that the referenced artifact
is retrievable in the lab environment.
AMEND-15 — Section 26.1, Enrichment Engine components
ADD bullet:
- Deployment Readiness Register client (Section 32): external integrations,
API surfaces, credential permissions, embedding behavior, inference serving,
sanitization, and payload_ref storage must have LAB-VERIFY evidence before
production use.
AMEND-16 — Section 30.2, Postgres schema, vector index
REPLACE fixed ivfflat requirement with benchmark-selected vector index policy.
For <10,000 cases, exact sequential scans are frequently faster and consume
less memory. For scaling, HNSW (for example m=16, ef_construction=64) is
strongly preferred over IVFFlat because it handles dynamic inserts seamlessly
without requiring periodic index rebuilds or maintenance windows.
The selected index type, parameters, benchmark method, and rationale are
recorded in Appendix N and in migration history.
AMEND-17 — Section 30.3, Handoff ledger contract
ADD payload_ref canonical contract:
For payloads larger than 1MB, or any payload not stored inline as JSONB, the
handoff ledger must store payload_ref using a canonical URI scheme.
Approved URI schemes:
opensearch://<index>/doc/<id>
file:///archive/artifacts/<aa>/<bb>/<sha256><.ext>
s3://<bucket>/<key>
The ledger must also record:
payload_sha256
payload_size_bytes
payload_compression
payload_sanitizer_version
payload_sanitization_status
payload_sanitization_action
payload_retention_class
payload_ref artifacts must never contain raw unsanitized telemetry unless the
artifact is stored outside orchestration memory and the ledger stores only the
sanitized reference metadata.
AMEND-18 — Section 30.5, Semantic recall
ADD embedding contract:
The embedding pipeline must pin:
embedding_model
embedding_model_revision_or_hash
embedding_dim
embedding_normalization
embedding_prefix_policy
If the selected embedding model uses task instruction prefixes, the embedding
writer and query path must enforce those prefixes.
For nomic-family embedding models, the lab must validate whether prefixes such
as document-side and query-side instruction strings are required for retrieval
quality.
Prefix injection MUST be implemented as a non-bypassable wrapper inside the
Python embedding service interface:
embed_document(text) prepends "search_document: "
embed_query(text) prepends "search_query: "
If the embedding runtime cannot enforce the required prefix policy, the
embedding adapter must fail closed rather than silently embed unprefixed text.
AMEND-19 — Section 31.5, Replay-mix evaluation
ADD:
Adapter promotion requires replay-mix evaluation.
The replay-mix evaluation set must contain:
1. Held-out test examples derived only from approved corrections or
approved curated training data.
2. A replay sample from the golden evaluation set used for the currently
active adapter.
The evaluation must measure at minimum:
verifier_pass_rate
schema_validity_rate
prohibited_action_rate
hallucinated_tool_call_rate
IOC extraction accuracy
triage summary sanity score
regression delta against active adapter
forgetting delta against golden replay sample
CI must record:
candidate adapter sha256
active adapter sha256
evaluation dataset hashes
replay sample hashes
metric results
pass/fail verdict
evaluator version
A candidate adapter must not be promoted if any safety-critical metric
regresses beyond the approved threshold.
AMEND-20 — Section 31.6, Canary and rollback
ADD:
Canary deployment must support at least one of the following modes:
1. Shadow canary
Candidate adapter receives the same prompt/context as the active
adapter, but its output is not used for operational action.
2. Limited live canary
Candidate adapter handles a small, explicitly routed subset of eligible
task_type traffic.
Canary SLOs must include:
verifier_pass_rate
schema_validity_rate
prohibited_action_rate
hallucinated_tool_call_rate
analyst correction rate
latency percentile
VRAM stability
recurrence of known failure classes
Rollback must be immediate and must not require retraining.
Rollback mechanisms may include:
active adapter pointer swap,
model registry status change,
reverse proxy endpoint swap,
container swap,
serving backend reload,
provided the previous signed adapter remains instantly restorable and the
rollback event is written to the handoff ledger.
AMEND-21 — Add Section 32
ADD Section 32: Deployment Readiness & Verification Register.
AMEND-22 — Add Section 33
ADD Section 33: Inference, Embedding, and VRAM Governance.
AMEND-23 — Add Section 34
ADD Section 34: Sanitization, Quarantine, and Artifact Reference Governance.
AMEND-24 — Appendix M verification note
ADD to Appendix M:
All documentation links, API paths, package names, and endpoint behaviors are
version-dependent and must be pinned, mirrored, and validated in the lab before
implementation.
In particular:
- pfSense API availability may depend on version, package, or plugin.
- Wazuh RBAC behavior must be tested with the deployed Wazuh version.
- Security Onion/OpenSearch access may be mediated by Security Onion.
- TheHive API behavior may differ across major versions.
- Suricata EVE schema may vary by Suricata version and configuration.
- Embedding model prefix requirements must be validated against the exact
model artifact used.
Appendix M is therefore a documentation index, not a substitute for lab proof.
AMEND-25 — Add Appendix N
ADD Appendix N: Pre-Implementation Research & Verification Register.
AMEND-26 — Add Appendix O
ADD Appendix O: CI Verification Tool Contracts & Skeletons.


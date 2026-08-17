SOURCE: LOCAL_SOC_SLM_Blueprint_v11.6.0_master.txt
BLOCK:  APPENDIX N — PRE-IMPLEMENTATION RESEARCH
SHA256: e80284a1a297457e
────────────────────────────────────────────────────────────────────────

Appendix N tracks all LAB-VERIFY and RESEARCH items required before the system
is considered deployment-ready.
Status values:
OPEN
IN PROGRESS
PASSED
FAILED
WAIVED
NOT APPLICABLE
Every completed item must record:
evidence path or hash,
test date,
software versions,
tester,
decision or remediation.
--------------------------------------------------------------------------------
N.1 Tier 0 blocker register
--------------------------------------------------------------------------------
R-001 pfSense API feasibility
Status:
OPEN
Verification method:
Lab firewall test.
Required evidence:
pfSense version, API/package path, auth method, alias read/draft/apply
test, least-privilege credential test.
Expected implementation path:
Install and validate pfSense-pkg-RESTAPI or equivalent.
Security requirement:
API credentials must be scoped to alias read/draft endpoints where
possible. Interface mutation, package mutation, reboot, and service
control endpoints must be denied.
Exit criteria:
Engine can read tables and draft aliases safely; apply remains
approval-gated.
R-002 Wazuh read-only credential proof
Status:
OPEN
Verification method:
Wazuh API permission test.
Required evidence:
Read-only role/user config, successful reads, denied forbidden actions.
Exit criteria:
Engine cannot mutate Wazuh or restart managers.
R-003 OpenSearch / Security Onion read-only proof
Status:
OPEN
Verification method:
Query test and permission test.
Required evidence:
Role mapping, successful queries, denied destructive actions.
Exit criteria:
Engine can read required telemetry but cannot delete or manage indices.
R-004 TheHive API version and permission proof
Status:
OPEN
Verification method:
TheHive API test.
Required evidence:
Version, auth method, permission scope, draft/writeback boundaries.
Exit criteria:
TheHive writes are controlled and approval-gated where required.
R-005 Suricata EVE intake validation
Status:
OPEN
Verification method:
EVE sample ingestion.
Required evidence:
Schema version, normalization rules, sanitization behavior.
Exit criteria:
EVE events can be normalized and sanitized before ledger insertion.
R-006 Embedding prefix and dimension validation
Status:
OPEN
Verification method:
Embedding test harness.
Required evidence:
Model hash, dimension check, prefix policy, top-k recall sample,
idempotency test.
Exit criteria:
Embeddings are 768-dimensional and prefix policy is enforced if
required. Double-prefix inputs are normalized.
--------------------------------------------------------------------------------
N.2 Tier 1 safety/memory register
--------------------------------------------------------------------------------
R-101 pgvector index benchmark
Status:
OPEN
Verification method:
Benchmark on representative case_embeddings sample.
Required evidence:
Index type, parameters, recall, latency, insert behavior, memory usage.
Expected outcome:
Sequential scan may be preferred for early low-volume operation.
HNSW is preferred over IVFFlat for scaling with dynamic inserts.
Exit criteria:
Selected index type is recorded and justified.
R-102 Postgres append-only proof
Status:
OPEN
Verification method:
Role grant audit and mutation attempt test.
Required evidence:
Grants, failed UPDATE/DELETE attempts, CI check output.
Exit criteria:
Engine role cannot mutate handoffs or corrections.
R-103 Schema drift CI proof
Status:
OPEN
Verification method:
Migration rebuild and schema diff.
Required evidence:
Schema hash, migration log, CI result.
Exit criteria:
Schema can be reproduced from migrations and drift fails CI.
R-104 payload_ref artifact governance
Status:
OPEN
Verification method:
Artifact store test.
Required evidence:
Canonical URI, sha256, size, compression, retrieval test.
Exit criteria:
payload_ref artifacts are retrievable and integrity-checked.
R-105 Sanitization redaction proof
Status:
OPEN
Verification method:
Redaction test suite.
Required evidence:
Test payloads, redaction report, quarantine behavior.
Exit criteria:
Known secrets/PII patterns are blocked, redacted, or quarantined.
R-106 SQLite quota ledger durability
Status:
OPEN
Verification method:
Crash/restart test.
Required evidence:
WAL config, transaction behavior, recovered ledger state.
Exit criteria:
Quota ledger remains consistent after simulated crash.
--------------------------------------------------------------------------------
N.3 Tier 2 training/eval register
--------------------------------------------------------------------------------
R-201 QLoRA recipe validation
Status:
OPEN
Verification method:
Training run on approved corrections-derived dataset.
Required evidence:
Training config, VRAM usage, adapter artifact hash.
Exit criteria:
Training completes reproducibly within hardware constraints.
R-202 Adapter signing proof
Status:
OPEN
Verification method:
Signature/checksum verification.
Required evidence:
Signer, cosigner, sha256, verification script output.
Exit criteria:
Only signed adapters can enter model_registry.
R-203 Replay-mix evaluation proof
Status:
OPEN
Verification method:
CI evaluation run.
Required evidence:
Dataset hashes, metrics, pass/fail verdict.
Exit criteria:
Replay-mix gate blocks regressive adapters.
R-204 Canary rollback drill
Status:
OPEN
Verification method:
Canary promotion and rollback exercise.
Required evidence:
Canary metrics, rollback event, ledger rows.
Exit criteria:
Rollback is immediate and auditable.
--------------------------------------------------------------------------------
N.4 Tier 3 operations register
--------------------------------------------------------------------------------
R-301 NVIDIA container/GPU passthrough proof
Status:
OPEN
Verification method:
Container GPU smoke test.
Required evidence:
Driver/toolkit versions, device reservation config, smoke output.
Exit criteria:
GPU workloads run reproducibly in containers or local processes.
R-302 VRAM budget smoke proof
Status:
OPEN
Verification method:
Inference + embedding load test.
Required evidence:
VRAM graph/summary, context limit, parallelism limit.
Stress requirement:
Simulate worst-case KV-cache expansion, for example max context plus a
concurrent embedding batch of 5 incoming IOCs.
Exit criteria:
No OOM under approved operating envelope.
R-303 Backup/restore proof
Status:
OPEN
Verification method:
Postgres backup and restore test.
Required evidence:
Backup hash, restore log, row count verification.
Exit criteria:
Orchestration memory can be restored deterministically.
R-304 Secrets management proof
Status:
OPEN
Verification method:
Credential storage and rotation test.
Required evidence:
Secret storage method, rotation record, access test.
Exit criteria:
No plaintext production secrets are stored in repository.
R-305 Licensing/publishing review
Status:
OPEN
Verification method:
License review.
Required evidence:
Model licenses, dataset licenses, publication policy.
Exit criteria:
Any published adapter/dataset has approved licensing and sanitization.
--------------------------------------------------------------------------------
N.5 Production-hardening register [v11.5]
--------------------------------------------------------------------------------
R-107 Time-partitioned pgvector feasibility
Status:
OPEN
Verification method:
Create partitioned case_embeddings table and attach HNSW indexes to
active partitions only.
Required evidence:
Query latency, recall, insert throughput, index memory usage,
partition pruning behavior.
Exit criteria:
Active partition HNSW search meets top-k latency goals without
destabilizing host memory or GPU inference.
R-108 Async backpressure queue proof
Status:
OPEN
Verification method:
Burst alert simulation using Wazuh/Suricata replay or synthetic queue
injection.
Required evidence:
Queue depth metrics, worker concurrency, shed events, dead-letter
behavior, severity prioritization.
Exit criteria:
High-severity alerts remain processed; low-severity alerts shed safely
under emergency backpressure.
R-109 Dynamic VRAM detection proof
Status:
OPEN
Verification method:
Run dynamic VRAM check on target GPU.
Required evidence:
nvidia-smi/NVML output, total VRAM, 90% cap calculation, workload
peak measurement.
Exit criteria:
CI fails closed when GPU is unavailable or VRAM cap is exceeded.
R-110 Entropy sanitization false-positive evaluation
Status:
OPEN
Verification method:
Run sanitizer against known IOC hashes, UUIDs, request IDs, JWTs,
API keys, SSH keys, and base64 blobs.
Required evidence:
Redaction report, allowlist behavior, quarantine behavior.
Exit criteria:
Secrets are redacted or quarantined; approved IOC hashes and audit
identifiers are preserved when explicitly expected.
R-111 Hash-chain integrity proof
Status:
OPEN
Verification method:
Insert sample rows, verify chain, tamper with one row in a test DB,
re-run verifier.
Required evidence:
Chain verification pass, tamper detection output, anchored chain hash.
Exit criteria:
Tampering breaks the chain and is detected by CI verifier.
--------------------------------------------------------------------------------
N.6 Edge-case hardening register [v11.5.1]
--------------------------------------------------------------------------------
R-112 Stale queue recovery proof
Status:
OPEN
Verification method:
Simulate worker crash, OOM, or timeout while a job is processing.
Required evidence:
lease_expires_at behavior, heartbeat behavior, reaper run, attempts
counter, failed/quarantined terminal state.
Exit criteria:
No job remains stuck in processing after lease expiration.
High-severity jobs are recovered safely.
Jobs exceeding max_attempts are failed or quarantined.
R-113 Field-aware entropy sanitization proof
Status:
OPEN
Verification method:
Run sanitizer against encoded PowerShell, obfuscated shell args,
suspicious script blocks, known IOC hashes, UUIDs, request IDs, and
secrets.
Required evidence:
sanitization_action values, quarantine_ref behavior, preserved hash
behavior, redaction manifest.
Exit criteria:
Secrets are redacted.
Approved IOC hashes and audit identifiers are preserved.
High-value suspicious command-line payloads are quarantined by
reference rather than destroyed inline.
R-114 Hash-chain concurrency proof
Status:
OPEN
Verification method:
Run concurrent insert test against handoffs/corrections or audit_chain
sealer.
Required evidence:
Advisory lock usage, chain_seq ordering, no duplicate previous_hash,
no corrupted chain, sealer throughput.
Exit criteria:
Concurrent inserts do not corrupt hash-chain order.
Chain sealing does not require granting general engine role UPDATE
rights.
R-115 Embedding prefix idempotency proof
Status:
OPEN
Verification method:
Pass unprefixed, single-prefixed, and double-prefixed text through the
embedding wrapper.
Required evidence:
Encoder input strings, prefix counts, embedding dimension checks.
Exit criteria:
Encoder receives exactly one required prefix for all cases.
Retrieval quality is not degraded by double-prefixing.
R-116 Changelog and termination completeness proof
Status:
OPEN
Verification method:
CI text check for required changelog entries and END OF DOCUMENT.
Required evidence:
Changelog hash, termination marker, completeness manifest check output.
Exit criteria:
Document terminates cleanly.
Required changelog entries are present.
Completeness manifest passes.
--------------------------------------------------------------------------------
N.7 Operational knowledge register [v11.6]
--------------------------------------------------------------------------------
R-117 Wiki sanitization and Git audit proof
Status:
OPEN
Verification method:
Generate a mock Wiki page containing fake secrets, high-entropy tokens,
and a mock Git commit.
Required evidence:
Sanitizer redaction report, Git commit SHA, handoff ledger wiki_commit_ref,
tools/wiki_sanitization_check.py output.
Exit criteria:
No secret is committed.
Git commit SHA is recorded in the handoff ledger.
Wiki generation task is queued at low severity and sheds safely under
backpressure.


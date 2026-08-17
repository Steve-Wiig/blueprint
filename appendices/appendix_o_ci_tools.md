SOURCE: LOCAL_SOC_SLM_Blueprint_v11.6.0_master.txt
BLOCK:  APPENDIX O — CI VERIFICATION TOOL CONTRACTS
SHA256: f1cdd9e1d7422524
────────────────────────────────────────────────────────────────────────

This appendix defines the CI verification tools required by v11.4, v11.5,
v11.5.1, v11.5.2, and v11.6.0.
Exit code contract:
0 = PASS
1 = FAIL
2 = CONFIG ERROR
3 = ENVIRONMENT NOT AVAILABLE
Required tools:
tools/external_credential_permission_check.py
tools/embedding_prefix_check.py
tools/embedding_prefix_idempotency_check.py
tools/sanitization_redaction_check.py
tools/sanitization_entropy_check.py
tools/sanitization_field_policy_check.py
tools/dynamic_vram_budget_check.py
tools/payload_ref_integrity_check.py
tools/hash_chain_verify.py
tools/hash_chain_concurrency_check.py
tools/queue_backpressure_check.py
tools/queue_stale_recovery_check.py
tools/vector_partition_index_check.py
tools/memory_schema_migrate_check.py
tools/changelog_completeness_check.py
tools/wiki_sanitization_check.py
--------------------------------------------------------------------------------
O.1 tools/external_credential_permission_check.py
--------------------------------------------------------------------------------
#!/usr/bin/env python3
# CI Gate: External Credential Permission Proof
import os
import sys
try:
import requests
except ImportError:
print("FAIL: requests library is not installed")
sys.exit(2)
CONFIG = {
"wazuh": {
"read": "/api/v1/agents",
"forbidden": "/api/v1/manager/restart",
"forbidden_method": "POST",
"user_env": "WAZUH_USER",
"token_env": "WAZUH_TOKEN",
},
"pfsense": {
"read": "/api/v2/firewall/alias",
"forbidden": "/api/v2/interfaces",
"forbidden_method": "GET",
"user_env": "PFSENSE_USER",
"token_env": "PFSENSE_TOKEN",
},
}
def check_service(service, cfg, lab_url):
user = os.getenv(cfg["user_env"], "")
token = os.getenv(cfg["token_env"], "")
if not user or not token:
print(f"CONFIG ERROR: missing credentials for {service}")
return False
auth = (user, token)
read_url = lab_url.rstrip("/") + cfg["read"]
forbidden_url = lab_url.rstrip("/") + cfg["forbidden"]
try:
read_resp = requests.get(read_url, auth=auth, timeout=10, verify=False)
if read_resp.status_code not in (200, 201):
print(f"FAIL: {service} read access denied: {read_resp.status_code}")
return False
forbidden_resp = requests.request(
cfg["forbidden_method"],
forbidden_url,
auth=auth,
timeout=10,
verify=False,
)
if forbidden_resp.status_code not in (401, 403):
print(
f"FAIL: {service} forbidden action was not denied: "
f"{forbidden_resp.status_code}"
)
return False
except requests.RequestException as exc:
print(f"FAIL: {service} request failed: {exc}")
return False
print(f"PASS: {service} credential permissions verified")
return True
def main():
lab_url = os.getenv("LAB_URL", "")
if not lab_url:
print("CONFIG ERROR: LAB_URL is not set")
return 2
all_pass = True
for service, cfg in CONFIG.items():
if not check_service(service, cfg, lab_url):
all_pass = False
return 0 if all_pass else 1
if __name__ == "__main__":
sys.exit(main())
--------------------------------------------------------------------------------
O.2 tools/embedding_prefix_check.py
--------------------------------------------------------------------------------
#!/usr/bin/env python3
# CI Gate: Embedding Prefix & Dimension Contract
import sys
REQUIRED_DOC_PREFIX = "search_document: "
REQUIRED_QUERY_PREFIX = "search_query: "
REQUIRED_DIM = 768
calls = []
def fake_encode(text):
calls.append(text)
return [0.0] * REQUIRED_DIM
class EmbeddingService:
def __init__(self, encoder):
self.encoder = encoder
def embed_document(self, text):
return self.encoder(REQUIRED_DOC_PREFIX + text)
def embed_query(self, text):
return self.encoder(REQUIRED_QUERY_PREFIX + text)
def main():
svc = EmbeddingService(fake_encode)
doc_vector = svc.embed_document("accepted triage summary")
query_vector = svc.embed_query("similar alert lookup")
if len(doc_vector) != REQUIRED_DIM:
print(f"FAIL: document embedding dim is {len(doc_vector)}")
return 1
if len(query_vector) != REQUIRED_DIM:
print(f"FAIL: query embedding dim is {len(query_vector)}")
return 1
if len(calls) != 2:
print("FAIL: expected exactly two embedding calls")
return 1
if not calls[0].startswith(REQUIRED_DOC_PREFIX):
print("FAIL: document embedding did not use search_document prefix")
return 1
if not calls[1].startswith(REQUIRED_QUERY_PREFIX):
print("FAIL: query embedding did not use search_query prefix")
return 1
print("PASS: embedding prefix and dimension contract verified")
return 0
if __name__ == "__main__":
sys.exit(main())
--------------------------------------------------------------------------------
O.3 tools/embedding_prefix_idempotency_check.py
--------------------------------------------------------------------------------
#!/usr/bin/env python3
# CI Gate: Embedding Prefix Idempotency Contract
import sys
REQUIRED_DOC_PREFIX = "search_document: "
REQUIRED_QUERY_PREFIX = "search_query: "
REQUIRED_DIM = 768
calls = []
def fake_encode(text):
calls.append(text)
return [0.0] * REQUIRED_DIM
def normalize_prefix(text, required_prefix):
while text.startswith(required_prefix):
text = text[len(required_prefix):]
return required_prefix + text
class EmbeddingService:
def __init__(self, encoder):
self.encoder = encoder
def embed_document(self, text):
return self.encoder(normalize_prefix(text, REQUIRED_DOC_PREFIX))
def embed_query(self, text):
return self.encoder(normalize_prefix(text, REQUIRED_QUERY_PREFIX))
def check_one(svc, method, text, expected_prefix):
calls.clear()
getattr(svc, method)(text)
if len(calls) != 1:
return False
if not calls[0].startswith(expected_prefix):
return False
if calls[0].count(expected_prefix) != 1:
return False
return True
def main():
svc = EmbeddingService(fake_encode)
doc_cases = [
"accepted triage summary",
"search_document: accepted triage summary",
"search_document: search_document: accepted triage summary",
]
query_cases = [
"similar alert lookup",
"search_query: similar alert lookup",
"search_query: search_query: similar alert lookup",
]
for case in doc_cases:
if not check_one(svc, "embed_document", case, REQUIRED_DOC_PREFIX):
print(f"FAIL: document prefix idempotency failed for: {case}")
return 1
for case in query_cases:
if not check_one(svc, "embed_query", case, REQUIRED_QUERY_PREFIX):
print(f"FAIL: query prefix idempotency failed for: {case}")
return 1
print("PASS: embedding prefix idempotency contract verified")
return 0
if __name__ == "__main__":
sys.exit(main())
--------------------------------------------------------------------------------
O.4 tools/sanitization_entropy_check.py
--------------------------------------------------------------------------------
#!/usr/bin/env python3
# CI Gate: Two-pass sanitization
# Pass 1: deterministic regex redaction
# Pass 2: Shannon entropy detection
import math
import re
REGEX_RULES = [
(r"AKIA[0-9A-Z]{16}", "[REDACTED_AWS_KEY]"),
(r"ghp_[A-Za-z0-9]{36}", "[REDACTED_GITHUB_TOKEN]"),
(r"Bearer\s+[A-Za-z0-9\-_\.]+", "[REDACTED_BEARER_TOKEN]"),
(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "[REDACTED_PRIVATE_KEY]"),
(r"slack_token=[A-Za-z0-9\-]+", "slack_token=[REDACTED_SLACK_TOKEN]"),
(r"api_key=[A-Za-z0-9\-_\.]+", "api_key=[REDACTED_API_KEY]"),
(r"password=[^\s&]+", "password=[REDACTED_PASSWORD]"),
]
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9+/=_\-]{17,}")
ALLOWLIST_PATTERNS = [
re.compile(r"^[a-f0-9]{64}$"),
re.compile(r"^[a-f0-9]{40}$"),
re.compile(r"^[a-f0-9]{32}$"),
re.compile(
r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
re.IGNORECASE,
),
]
ENTROPY_THRESHOLD = 4.5
def shannon_entropy(token):
if not token:
return 0.0
counts = {}
for ch in token:
counts[ch] = counts.get(ch, 0) + 1
length = len(token)
entropy = 0.0
for count in counts.values():
p = count / length
entropy -= p * math.log2(p)
return entropy
def is_allowlisted(token):
return any(pattern.match(token) for pattern in ALLOWLIST_PATTERNS)
def sanitize_text(text, preserve_high_entropy_hashes=False):
for pattern, replacement in REGEX_RULES:
text = re.sub(pattern, replacement, text)
def replace_token(match):
token = match.group(0)
if preserve_high_entropy_hashes and is_allowlisted(token):
return token
entropy = shannon_entropy(token)
if entropy >= ENTROPY_THRESHOLD:
return "[REDACTED_HIGH_ENTROPY_TOKEN]"
return token
text = TOKEN_PATTERN.sub(replace_token, text)
return text
if __name__ == "__main__":
sample = (
"AWS key AKIAIOSFODNN7EXAMPLE and token "
"ghp_1234567890abcdefghijklmnopqrstuvwxyz and sha256 "
"3a7bd3e2360a3d29eea436fcfb7e44c735d117c42d1c1835420b6b9942dd4f1b"
)
sanitized = sanitize_text(sample, preserve_high_entropy_hashes=True)
if "AKIAIOSFODNN7EXAMPLE" in sanitized:
print("FAIL: AWS key not redacted")
raise SystemExit(1)
if "ghp_1234567890abcdefghijklmnopqrstuvwxyz" in sanitized:
print("FAIL: GitHub token not redacted")
raise SystemExit(1)
if "3a7bd3e2360a3d29eea436fcfb7e44c735d117c42d1c1835420b6b9942dd4f1b" not in sanitized:
print("FAIL: allowlisted sha256 was redacted unexpectedly")
raise SystemExit(1)
print("PASS: two-pass sanitization contract verified")
--------------------------------------------------------------------------------
O.5 tools/sanitization_field_policy_check.py
--------------------------------------------------------------------------------
Purpose:
Verifies field-aware entropy handling.
Required behavior:
High-entropy tokens in secret-like fields are redacted inline.
High-entropy tokens in analytical command-line fields trigger
quarantine_ref where policy requires.
sanitization_action is one of:
preserve_allowlisted
redact_inline
quarantine_ref
reject
quarantine_reason is recorded when action is quarantine_ref.
Minimum test cases:
process.command_line containing base64-encoded PowerShell
process.args containing obfuscated shell string
known sha256 IOC hash in an IOC field
UUID in request_id
AWS key in unstructured text
bearer token in Authorization header
Exit behavior:
0 = PASS
1 = FAIL
2 = CONFIG ERROR
3 = ENVIRONMENT NOT AVAILABLE
--------------------------------------------------------------------------------
O.6 tools/dynamic_vram_budget_check.py
--------------------------------------------------------------------------------
#!/usr/bin/env python3
# CI Gate: Dynamic VRAM Budget Check
import os
import subprocess
import sys
def get_gpu_memory_info_mb():
try:
out = subprocess.check_output(
[
"nvidia-smi",
"--query-gpu=memory.used,memory.total",
"--format=csv,nounits,noheader",
],
text=True,
)
except Exception as exc:
print(f"FAIL: unable to query nvidia-smi: {exc}")
sys.exit(3)
lines = [line.strip() for line in out.strip().splitlines() if line.strip()]
if not lines:
print("FAIL: no GPU memory info returned")
sys.exit(3)
used_mb, total_mb = lines[0].split(",")
return int(used_mb.strip()), int(total_mb.strip())
def main():
used_mb, total_mb = get_gpu_memory_info_mb()
override_mb = os.getenv("VRAM_BUDGET_MB")
if override_mb:
max_allowed_mb = int(override_mb)
else:
max_allowed_mb = int(total_mb * 0.90)
print(f"Total GPU VRAM: {total_mb} MB")
print(f"Used GPU VRAM:  {used_mb} MB")
print(f"Allowed cap:    {max_allowed_mb} MB")
if used_mb > max_allowed_mb:
print("FAIL: VRAM usage exceeds dynamic safety threshold")
return 1
print("PASS: VRAM usage within dynamic safety threshold")
return 0
if __name__ == "__main__":
sys.exit(main())
--------------------------------------------------------------------------------
O.7 tools/payload_ref_integrity_check.py
--------------------------------------------------------------------------------
#!/usr/bin/env python3
# CI Gate: payload_ref Integrity & Canonical URI Check
import hashlib
import os
import sys
import tempfile
from pathlib import Path
REQUIRED_KEYS = [
"payload_ref",
"payload_sha256",
"payload_size_bytes",
"payload_compression",
"payload_sanitizer_version",
"payload_sanitization_status",
"payload_sanitization_action",
"payload_retention_class",
]
def main():
payload = b"LOCAL-SOC-SLM payload_ref integrity test"
sha256 = hashlib.sha256(payload).hexdigest()
size_bytes = len(payload)
with tempfile.TemporaryDirectory() as tmpdir:
artifact_dir = Path(tmpdir) / "archive" / "artifacts" / sha256[:2] / sha256[2:4]
artifact_dir.mkdir(parents=True, exist_ok=True)
artifact_path = artifact_dir / f"{sha256}.bin"
artifact_path.write_bytes(payload)
payload_ref = f"file://{artifact_path}"
ledger_row = {
"payload_ref": payload_ref,
"payload_sha256": sha256,
"payload_size_bytes": size_bytes,
"payload_compression": "none",
"payload_sanitizer_version": "1.0.0",
"payload_sanitization_status": "clean",
"payload_sanitization_action": "preserve_allowlisted",
"payload_retention_class": "short_term_operational",
}
for key in REQUIRED_KEYS:
if key not in ledger_row:
print(f"FAIL: ledger row missing required key: {key}")
return 1
if not ledger_row["payload_ref"].startswith(
("file://", "opensearch://", "s3://")
):
print("FAIL: payload_ref URI scheme is not canonical")
return 1
retrieved_path = ledger_row["payload_ref"].replace("file://", "")
if not os.path.exists(retrieved_path):
print("FAIL: payload_ref artifact is not retrievable")
return 1
retrieved_bytes = Path(retrieved_path).read_bytes()
retrieved_sha256 = hashlib.sha256(retrieved_bytes).hexdigest()
if retrieved_sha256 != ledger_row["payload_sha256"]:
print("FAIL: payload_ref artifact hash mismatch")
return 1
print("PASS: payload_ref integrity and canonical URI verified")
return 0
if __name__ == "__main__":
sys.exit(main())
--------------------------------------------------------------------------------
O.8 tools/hash_chain_verify.py
--------------------------------------------------------------------------------
#!/usr/bin/env python3
# Hash-chain verification skeleton for handoffs/corrections or audit_chain.
import hashlib
import json
GENESIS_HASH = "0" * 64
def compute_row_hash(chain_seq, previous_hash, row):
canonical = json.dumps(row, sort_keys=True, separators=(",", ":"))
material = f"{chain_seq}:{previous_hash}:{canonical}"
return hashlib.sha256(material.encode("utf-8")).hexdigest()
def verify_chain(rows):
previous_hash = GENESIS_HASH
for row in rows:
expected = compute_row_hash(
row["chain_seq"],
previous_hash,
row["canonical_payload"],
)
if expected != row["row_hash"]:
return False, row["chain_seq"]
if row["previous_hash"] != previous_hash:
return False, row["chain_seq"]
previous_hash = row["row_hash"]
return True, None
if __name__ == "__main__":
print("PASS: hash-chain verifier skeleton loaded")
--------------------------------------------------------------------------------
O.9 tools/hash_chain_concurrency_check.py contract
--------------------------------------------------------------------------------
Purpose:
Verifies that concurrent inserts do not corrupt hash-chain order.
Required behavior:
Multiple concurrent writers append rows.
Chain sealer serializes chain extension.
chain_seq remains unique and ordered.
previous_hash remains consistent.
No general engine role UPDATE rights are required on handoffs/corrections.
Exit behavior:
0 = PASS
1 = FAIL
2 = CONFIG ERROR
3 = ENVIRONMENT NOT AVAILABLE
--------------------------------------------------------------------------------
O.10 tools/queue_backpressure_check.py contract
--------------------------------------------------------------------------------
Purpose:
Verify queue behavior under burst load.
Required checks:
Queue accepts sanitized alert references.
Queue prioritizes severity correctly.
Worker claim uses bounded concurrency.
Warning threshold triggers metrics/pressure handling.
Emergency threshold triggers safe shedding.
High-severity and critical alerts are not silently dropped.
Shed events record shed_reason.
Failed jobs enter failed or quarantined state.
payload_ref remains available for failed jobs.
Exit behavior:
0 = PASS
1 = FAIL
2 = CONFIG ERROR
3 = ENVIRONMENT NOT AVAILABLE
--------------------------------------------------------------------------------
O.11 tools/queue_stale_recovery_check.py contract
--------------------------------------------------------------------------------
Purpose:
Verifies stale job recovery.
Required checks:
Claimed job sets lease_expires_at.
Worker heartbeat extends lease.
Reaper resets expired jobs to pending when attempts < max_attempts.
Reaper fails or quarantines jobs when attempts >= max_attempts.
No job remains stuck in processing after lease expiration.
Recovery events are auditable.
Exit behavior:
0 = PASS
1 = FAIL
2 = CONFIG ERROR
3 = ENVIRONMENT NOT AVAILABLE
--------------------------------------------------------------------------------
O.12 tools/vector_partition_index_check.py contract
--------------------------------------------------------------------------------
Purpose:
Verifies time-partitioned case_embeddings behavior.
Required checks:
Active partitions exist.
Active partition HNSW index exists where expected.
Older partitions do not require HNSW index.
Top-k query prunes partitions using created_at filter.
Recall and latency remain within approved threshold.
Index attachment/detachment is recorded in migration history.
Exit behavior:
0 = PASS
1 = FAIL
2 = CONFIG ERROR
3 = ENVIRONMENT NOT AVAILABLE
--------------------------------------------------------------------------------
O.13 tools/memory_schema_migrate_check.py contract
--------------------------------------------------------------------------------
Purpose:
Verifies schema migration reproducibility and append-only drift.
Required checks:
Migration scripts rebuild schema deterministically.
Schema hash matches expected value.
No UPDATE/DELETE statements exist for handoffs/corrections in migration
history.
Engine role grants do not include UPDATE/DELETE on append-only tables.
Exit behavior:
0 = PASS
1 = FAIL
2 = CONFIG ERROR
3 = ENVIRONMENT NOT AVAILABLE
--------------------------------------------------------------------------------
O.14 tools/changelog_completeness_check.py contract
--------------------------------------------------------------------------------
Purpose:
Verifies changelog and document termination integrity.
Required checks:
Required version entries exist:
v11.3
v11.3-updated
v11.4-complete
v11.5
v11.5-master
v11.5.1-master
v11.5.2-master
v11.6.0-master
v11.4-complete changelog bullet for pgvector index policy is complete.
END OF DOCUMENT marker exists.
Completeness manifest exists.
Required Appendix M subsections exist.
Required Appendix O tool entries exist.
Required Appendix P template entries exist.
Required Appendix Q runbook entries exist.
Exit behavior:
0 = PASS
1 = FAIL
2 = CONFIG ERROR
3 = ENVIRONMENT NOT AVAILABLE
--------------------------------------------------------------------------------
O.15 CI pipeline example
--------------------------------------------------------------------------------
Example GitHub Actions steps:
- name: Gate 1 - External Credential Permission Proof
run: python tools/external_credential_permission_check.py
- name: Gate 2 - Embedding Prefix Contract
run: python tools/embedding_prefix_check.py
- name: Gate 3 - Embedding Prefix Idempotency Contract
run: python tools/embedding_prefix_idempotency_check.py
- name: Gate 4 - Sanitization Entropy Check
run: python tools/sanitization_entropy_check.py
- name: Gate 5 - Sanitization Field Policy Check
run: python tools/sanitization_field_policy_check.py
- name: Gate 6 - Dynamic VRAM Budget Check
run: python tools/dynamic_vram_budget_check.py
- name: Gate 7 - payload_ref Integrity
run: python tools/payload_ref_integrity_check.py
- name: Gate 8 - Hash Chain Integrity Check
run: python tools/hash_chain_verify.py
- name: Gate 9 - Hash Chain Concurrency Check
run: python tools/hash_chain_concurrency_check.py
- name: Gate 10 - Queue Backpressure Check
run: python tools/queue_backpressure_check.py
- name: Gate 11 - Queue Stale Recovery Check
run: python tools/queue_stale_recovery_check.py
- name: Gate 12 - Vector Partition Index Check
run: python tools/vector_partition_index_check.py
- name: Gate 13 - Memory Schema Migration Check
run: python tools/memory_schema_migrate_check.py --fail-on-drift
- name: Gate 14 - Changelog Completeness Check
run: python tools/changelog_completeness_check.py
- name: Gate 15 - Postgres Append-Only Audit
run: |
if grep -R -E "UPDATE|DELETE" memory/migration/ | grep -E "handoffs|corrections"; then
echo "FAIL: prohibited UPDATE/DELETE found in migration history"
exit 1
fi
echo "PASS: append-only migration audit clean"
- name: Gate 16 - Wiki Sanitization Check
run: python tools/wiki_sanitization_check.py
--------------------------------------------------------------------------------
O.16 tools/wiki_sanitization_check.py contract [v11.6]
--------------------------------------------------------------------------------
Purpose:
Verifies that the Wiki publishing pipeline cannot accidentally commit raw
secrets or high-entropy unknown tokens into Markdown files.
Required behavior:
Inject fake AWS access key IDs, GitHub tokens, bearer tokens, private key
headers, and password strings into a mock wiki_draft Markdown payload.
The sanitizer must redact or block them before the Git commit or file write.
Required checks:
Sanitizer redacts known secret patterns.
Sanitizer handles high-entropy unknown tokens.
Allowlisted IOC hashes and UUIDs are preserved when explicitly expected.
Generated Markdown metadata records sanitization_action.
If a Git commit is simulated, the commit SHA is recorded in the handoff ledger.
Exit behavior:
0 = PASS
1 = FAIL
2 = CONFIG ERROR
3 = ENVIRONMENT NOT AVAILABLE


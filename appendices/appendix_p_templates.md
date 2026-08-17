SOURCE: LOCAL_SOC_SLM_Blueprint_v11.6.0_master.txt
BLOCK:  APPENDIX P — PRODUCTION-HARDENING SQL
SHA256: 675063beafd4ac6a
────────────────────────────────────────────────────────────────────────

--------------------------------------------------------------------------------
P.1 SQL: triage_queue table with lease recovery
--------------------------------------------------------------------------------
CREATE TABLE triage_queue (
id UUID PRIMARY KEY,
enqueued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
severity TEXT NOT NULL,
source_platform TEXT NOT NULL,
payload_ref TEXT,
payload_sha256 TEXT,
status TEXT NOT NULL DEFAULT 'pending',
attempts INTEGER NOT NULL DEFAULT 0,
started_at TIMESTAMPTZ,
finished_at TIMESTAMPTZ,
last_heartbeat_at TIMESTAMPTZ,
lease_expires_at TIMESTAMPTZ,
shed_reason TEXT,
failure_reason TEXT
);
CREATE INDEX idx_triage_queue_pending
ON triage_queue (severity, enqueued_at)
WHERE status = 'pending';
CREATE INDEX idx_triage_queue_stale
ON triage_queue (lease_expires_at)
WHERE status = 'processing';
--------------------------------------------------------------------------------
P.2 SQL: worker claim pattern with lease
--------------------------------------------------------------------------------
UPDATE triage_queue
SET status = 'processing',
started_at = now(),
attempts = attempts + 1,
last_heartbeat_at = now(),
lease_expires_at = now() + interval '15 minutes'
WHERE id = (
SELECT id
FROM triage_queue
WHERE status = 'pending'
ORDER BY
CASE severity
WHEN 'critical' THEN 0
WHEN 'high' THEN 1
WHEN 'medium' THEN 2
WHEN 'low' THEN 3
ELSE 4
END,
enqueued_at ASC
LIMIT 1
FOR UPDATE SKIP LOCKED
)
RETURNING *;
--------------------------------------------------------------------------------
P.3 SQL: worker heartbeat
--------------------------------------------------------------------------------
UPDATE triage_queue
SET last_heartbeat_at = now(),
lease_expires_at = now() + interval '15 minutes'
WHERE id = :job_id
AND status = 'processing';
--------------------------------------------------------------------------------
P.4 SQL: stale job reaper
--------------------------------------------------------------------------------
UPDATE triage_queue
SET status = 'pending',
started_at = NULL,
lease_expires_at = NULL
WHERE status = 'processing'
AND lease_expires_at < now()
AND attempts < :max_attempts;
UPDATE triage_queue
SET status = 'failed',
finished_at = now(),
failure_reason = 'max_attempts_exceeded_after_stale_recovery'
WHERE status = 'processing'
AND lease_expires_at < now()
AND attempts >= :max_attempts;
--------------------------------------------------------------------------------
P.5 SQL: partitioned case_embeddings
--------------------------------------------------------------------------------
CREATE TABLE case_embeddings (
id UUID NOT NULL,
created_at TIMESTAMPTZ NOT NULL,
source_type TEXT NOT NULL,
source_id TEXT NOT NULL,
case_ref TEXT,
embedding vector(768),
metadata JSONB,
PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);
CREATE TABLE case_embeddings_y2026m08
PARTITION OF case_embeddings
FOR VALUES FROM ('2026-08-01 00:00:00+00') TO ('2026-09-01 00:00:00+00');
CREATE INDEX idx_case_embeddings_y2026m08_hnsw
ON case_embeddings_y2026m08
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
--------------------------------------------------------------------------------
P.6 SQL: recommended audit_chain table
--------------------------------------------------------------------------------
CREATE TABLE audit_chain (
chain_seq BIGINT PRIMARY KEY,
table_name TEXT NOT NULL,
row_id UUID NOT NULL,
row_ts TIMESTAMPTZ NOT NULL,
canonical_payload_sha256 TEXT NOT NULL,
previous_hash CHAR(64) NOT NULL,
row_hash CHAR(64) NOT NULL,
sealed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_chain_table_row
ON audit_chain (table_name, row_id);
--------------------------------------------------------------------------------
P.7 SQL: optional embedded hash-chain columns
--------------------------------------------------------------------------------
If embedded columns are used instead of audit_chain:
ALTER TABLE handoffs
ADD COLUMN chain_seq BIGINT,
ADD COLUMN previous_hash CHAR(64),
ADD COLUMN row_hash CHAR(64);
CREATE UNIQUE INDEX idx_handoffs_chain_seq
ON handoffs (chain_seq);
CREATE INDEX idx_handoffs_row_hash
ON handoffs (row_hash);
ALTER TABLE corrections
ADD COLUMN chain_seq BIGINT,
ADD COLUMN previous_hash CHAR(64),
ADD COLUMN row_hash CHAR(64);
CREATE UNIQUE INDEX idx_corrections_chain_seq
ON corrections (chain_seq);
CREATE INDEX idx_corrections_row_hash
ON corrections (row_hash);
If embedded columns are used, only a dedicated chain writer role may update
chain columns. The general engine role must not receive these rights.
--------------------------------------------------------------------------------
P.8 Python: idempotent embedding prefix wrapper
--------------------------------------------------------------------------------
REQUIRED_DOC_PREFIX = "search_document: "
REQUIRED_QUERY_PREFIX = "search_query: "
def _normalize_prefix(text, required_prefix):
while text.startswith(required_prefix):
text = text[len(required_prefix):]
return required_prefix + text
class EmbeddingService:
def __init__(self, encoder):
self.encoder = encoder
def embed_document(self, text):
return self.encoder(_normalize_prefix(text, REQUIRED_DOC_PREFIX))
def embed_query(self, text):
return self.encoder(_normalize_prefix(text, REQUIRED_QUERY_PREFIX))
--------------------------------------------------------------------------------
P.9 Python: field-aware entropy sanitization policy
--------------------------------------------------------------------------------
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
ANALYTICAL_HIGH_ENTROPY_FIELDS = {
"process.args",
"process.command_line",
"powershell.encoded_command",
"script.block",
"bash.command",
"shell.args",
}
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
def sanitize_field(field_name, text):
action = "preserve_allowlisted"
quarantine_reason = None
for pattern, replacement in REGEX_RULES:
if re.search(pattern, text):
text = re.sub(pattern, replacement, text)
action = "redact_inline"
def replace_token(match):
nonlocal action, quarantine_reason
token = match.group(0)
if is_allowlisted(token):
return token
entropy = shannon_entropy(token)
if entropy >= ENTROPY_THRESHOLD:
if field_name in ANALYTICAL_HIGH_ENTROPY_FIELDS:
action = "quarantine_ref"
quarantine_reason = "high_entropy_analytical_payload"
return "[QUARANTINED_HIGH_ENTROPY_PAYLOAD_REF]"
action = "redact_inline"
return "[REDACTED_HIGH_ENTROPY_TOKEN]"
return token
text = TOKEN_PATTERN.sub(replace_token, text)
return {
"text": text,
"sanitization_action": action,
"quarantine_reason": quarantine_reason,
}
--------------------------------------------------------------------------------
P.10 Python: hash-chain verification
--------------------------------------------------------------------------------
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
--------------------------------------------------------------------------------
P.11 CI additions
--------------------------------------------------------------------------------
Add to CI:
- External credential permission check
- Embedding prefix contract check
- Embedding prefix idempotency check
- Sanitization regex check
- Sanitization entropy check
- Sanitization field policy check
- Dynamic VRAM budget check
- payload_ref integrity check
- Hash-chain integrity check
- Hash-chain concurrency check
- Queue backpressure simulation check
- Queue stale recovery check
- Partitioned vector index check
- Memory schema migration drift check
- Changelog completeness check
- Wiki sanitization check [v11.6]
These tools are defined in Appendix O.
--------------------------------------------------------------------------------
P.12 Ledger metadata for Wiki commit reference [v11.6]
--------------------------------------------------------------------------------
When Section 38 Wiki generation commits a sanitized Markdown page to a local
Git repository, record in the handoff ledger:
direction = 'to_platform'
from_component = 'orchestrator.wiki_writer'
to_component = 'local_wiki_git'
payload_sha256 = sha256 of sanitized Markdown bytes
metadata.wiki_path = repository-relative Markdown path
metadata.wiki_action = 'append_page' | 'draft_normative_change'
metadata.wiki_commit_ref = Git commit SHA
The Git commit is an externalized audit artifact. The ledger row remains the
orchestration-memory proof of provenance.


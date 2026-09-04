SOURCE: soc-autopilot (historical)
BLOCK:  SECTION 37: HASH-CHAINED AUDIT LEDGER
SHA256: f0eb9aea4e67f81b
────────────────────────────────────────────────────────────────────────

37.0 Purpose
The append-only handoff ledger and corrections table are protected by
role-level restrictions. Hash chaining adds tamper evidence as defense-in-depth.
Hash chaining does not replace PostgreSQL privilege restrictions. It strengthens
detection of unauthorized modification.
37.1 Hash-chain contract
The following columns are recommended for hash-chained audit tables if embedded
columns are used:
chain_seq BIGINT
previous_hash CHAR(64)
row_hash CHAR(64)
Hash calculation:
row_hash = SHA256(
chain_seq ||
previous_hash ||
canonical_row_payload
)
canonical_row_payload must include only immutable audit fields, such as:
request_id
ts
direction
from_component
to_component
model_name
adapter_sha256
verifier_version
verdict
payload_sha256
The hash chain must not depend on mutable fields.
37.2 Genesis hash
The first row uses a fixed genesis hash:
0000000000000000000000000000000000000000000000000000000000000000
37.3 Verification
A CI or maintenance job must recompute the chain and fail if any row hash or
previous hash mismatch is detected.
Verification must be tested against:
clean data,
a tampered row,
a reordered row,
a deleted row,
an inserted unauthorized row.
37.4 Anchoring
Periodically anchor the latest chain hash to an external append-only location,
such as:
a signed git tag,
an immutable file archive,
a lab evidence record in Appendix N,
a hardware-protected keystore where available.
Anchoring must be recorded in the release checklist.
37.5 Hash-chain concurrency policy [v11.5.1]
Concurrent inserts must not compute previous_hash directly at insert time if
multiple writers can append simultaneously.
Hash-chain generation must be serialized.
Approved patterns:
Pattern A — Single chain writer:
Application inserts append-only rows without chain fields.
A dedicated chain writer process reads newly inserted rows in deterministic
order and computes chain_seq, previous_hash, and row_hash.
Pattern B — Asynchronous chain sealer:
Rows are inserted with chain_status = 'pending'.
A background sealer process periodically computes the chain under an
advisory lock.
Pattern C — Separate audit_chain table:
handoffs and corrections remain strictly append-only.
A separate audit_chain table stores the sealed hash chain.
Recommended default:
Pattern C, separate audit_chain table.
Reason:
It avoids granting UPDATE rights to handoffs or corrections, preserving the
append-only security model.
Example audit_chain table:
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
The chain sealer must acquire a serialized advisory lock before extending the
chain:
SELECT pg_advisory_xact_lock(37001);
The sealer must process rows in deterministic order:
ORDER BY row_ts ASC, row_id ASC
The hash chain must be verifiable independently of the writer that produced the
original row.
If chain columns remain embedded in handoffs or corrections, only a dedicated
chain writer role may update chain_seq, previous_hash, and row_hash. That role
must not be the general engine role.
37.6 Acceptance criteria
handoffs and corrections include hash-chain columns where enabled, or
audit_chain is used.
chain_seq is unique and ordered.
hash_chain_verify.py passes on clean data.
hash_chain_verify.py detects tampering in test data.
latest chain hash is anchored and recorded.
Concurrent inserts do not corrupt chain order.
Chain sealing does not require granting UPDATE rights to the general engine
role.


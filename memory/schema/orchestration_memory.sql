CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE iocs (
    ioc_id UUID PRIMARY KEY,
    ioc_type TEXT NOT NULL,
    ioc_value TEXT NOT NULL,
    first_seen TIMESTAMP WITH TIME ZONE NOT NULL,
    last_seen TIMESTAMP WITH TIME ZONE,
    threat_score FLOAT,
    sanitizer_version TEXT,
    sanitization_status TEXT,
    redaction_manifest_sha256 TEXT
) PARTITION BY RANGE (first_seen);

CREATE TABLE handoffs (
    handoff_id UUID PRIMARY KEY,
    source_component TEXT NOT NULL,
    target_component TEXT NOT NULL,
    payload_ref TEXT NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    prev_hash TEXT,
    current_hash TEXT NOT NULL
);

CREATE TABLE investigations (
    investigation_id UUID PRIMARY KEY,
    status TEXT NOT NULL,
    autonomy_level INT,
    budget_remaining FLOAT,
    context_json JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE corrections (
    correction_id UUID PRIMARY KEY,
    investigation_id UUID REFERENCES investigations(investigation_id),
    human_decision TEXT NOT NULL,
    correction_data JSONB,
    sanitizer_version TEXT,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE case_embeddings (
    embedding_id UUID PRIMARY KEY,
    case_ref UUID,
    embedding VECTOR(1536),
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE model_registry (
    model_id UUID PRIMARY KEY,
    role TEXT NOT NULL,
    hardware_profile TEXT,
    status TEXT,
    signer TEXT,
    cosigner TEXT,
    checksum TEXT NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE triage_queue (
    queue_id UUID PRIMARY KEY,
    severity INT,
    payload_ref TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    attempts INT DEFAULT 0,
    lease_expires_at TIMESTAMP WITH TIME ZONE,
    last_heartbeat_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE audit_chain (
    chain_id BIGSERIAL PRIMARY KEY,
    record_type TEXT NOT NULL,
    record_id UUID NOT NULL,
    hash_value TEXT NOT NULL,
    prev_hash TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_iocs_first_seen ON iocs (first_seen);
CREATE INDEX idx_handoffs_timestamp ON handoffs (timestamp);
CREATE INDEX idx_investigations_status ON investigations (status);
CREATE INDEX idx_case_embeddings_vector ON case_embeddings USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX idx_triage_queue_status ON triage_queue (status, lease_expires_at);
CREATE INDEX idx_audit_chain_hash ON audit_chain (hash_value);

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
CREATE ROLE slm_append_only;
GRANT INSERT ON iocs, handoffs, investigations, corrections, case_embeddings, model_registry, triage_queue, audit_chain TO slm_append_only;
GRANT SELECT ON iocs, handoffs, investigations, corrections, case_embeddings, model_registry, triage_queue, audit_chain TO slm_append_only;
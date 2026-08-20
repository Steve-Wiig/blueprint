CREATE DATABASE soc_memory;

\c soc_memory;

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE iocs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ioc_value TEXT NOT NULL,
    ioc_type TEXT NOT NULL CHECK (ioc_type IN ('ip', 'domain', 'hash', 'url')),
    severity INT DEFAULT 0,
    source TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB
) PARTITION BY RANGE (created_at);

CREATE TABLE iocs_2024_05_20 PARTITION OF iocs
    FOR VALUES FROM ('2024-05-20 00:00:00') TO ('2024-05-21 00:00:00');

CREATE INDEX idx_iocs_value ON iocs (ioc_value);
CREATE INDEX idx_iocs_type ON iocs (ioc_type);
CREATE INDEX idx_iocs_created_at ON iocs (created_at);

CREATE TABLE case_summaries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_id TEXT UNIQUE NOT NULL,
    summary_text TEXT,
    embedding VECTOR(768),
    tags TEXT[],
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_case_summaries_embedding ON case_summaries USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX idx_case_summaries_tags ON case_summaries USING GIN (tags);

CREATE TABLE audit_chain (
    id SERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    previous_hash TEXT,
    current_hash TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_chain_hash ON audit_chain (current_hash);

CREATE TABLE quota_ledger (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    module_name TEXT NOT NULL,
    tokens_consumed INT NOT NULL DEFAULT 0,
    request_id TEXT UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_quota_module ON quota_ledger (module_name);

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_case_summaries_modtime
    BEFORE UPDATE ON case_summaries
    FOR EACH ROW
    EXECUTE PROCEDURE update_updated_at_column();

INSERT INTO quota_ledger (module_name, tokens_consumed, request_id) 
VALUES ('engine.intake', 150, 'req_abc123');

INSERT INTO case_summaries (case_id, summary_text, embedding) 
VALUES ('CASE-001', 'Initial detection of beaconing activity', '[0.1, 0.2, ... 768 dims]');

CREATE OR REPLACE FUNCTION create_daily_partition()
RETURNS TRIGGER AS $$
DECLARE
    partition_name TEXT;
    start_date TEXT;
    end_date TEXT;
BEGIN
    partition_name := 'iocs_' || to_char(NEW.created_at, 'YYYY_MM_DD');
    start_date := to_char(NEW.created_at, 'YYYY-MM-DD 00:00:00');
    end_date := to_char(NEW.created_at + INTERVAL '1 day', 'YYYY-MM-DD 00:00:00');
    
    IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = partition_name) THEN
        EXECUTE format('CREATE TABLE IF NOT EXISTS %I PARTITION OF iocs FOR VALUES FROM (%L) TO (%L)', partition_name, start_date, end_date);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_auto_partition_iocs
    BEFORE INSERT ON iocs
    FOR EACH ROW
    EXECUTE PROCEDURE create_daily_partition();

COMMENT ON TABLE iocs IS 'Core IOC storage with daily partitioning for retention management';
COMMENT ON TABLE case_summaries IS 'Vector-enabled storage for RAG-based case retrieval';
COMMENT ON TABLE audit_chain IS 'Immutable log for SOC compliance and forensic integrity';
COMMENT ON TABLE quota_ledger IS 'Tracking token usage for orchestrator model routing';

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO soc_admin;
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO soc_engine;
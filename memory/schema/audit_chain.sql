CREATE TABLE audit_chain (
    chain_seq BIGINT PRIMARY KEY,
    table_name TEXT NOT NULL,
    row_id UUID NOT NULL,
    row_ts TIMESTAMPTZ NOT NULL,
    canonical_payload_sha256 CHAR(64) NOT NULL,
    previous_hash CHAR(64) NOT NULL,
    row_hash CHAR(64) NOT NULL UNIQUE,
    sealed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_chain_deterministic_order ON audit_chain (row_ts ASC, row_id ASC);

COMMENT ON TABLE audit_chain IS 'Pattern C: Separate audit_chain table for hash-chained ledger. Sealer must acquire pg_advisory_xact_lock(37001) before processing. Enforced append-only via RLS.';

ALTER TABLE audit_chain ENABLE ROW LEVEL SECURITY;

CREATE POLICY audit_chain_append_only_policy ON audit_chain
    FOR ALL
    TO PUBLIC
    USING (false)
    WITH CHECK (false);

CREATE POLICY audit_chain_sealer_policy ON audit_chain
    FOR INSERT
    TO audit_sealer_role
    WITH CHECK (true);

CREATE POLICY audit_chain_verifier_policy ON audit_chain
    FOR SELECT
    TO audit_verifier_role
    USING (true);

CREATE OR REPLACE FUNCTION fn_audit_chain_immutable()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Audit chain is immutable. UPDATE/DELETE operations are prohibited.';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_audit_chain_no_mod
BEFORE UPDATE OR DELETE ON audit_chain
FOR EACH STATEMENT EXECUTE FUNCTION fn_audit_chain_immutable();

REVOKE ALL ON audit_chain FROM PUBLIC;
GRANT SELECT ON audit_chain TO audit_verifier_role;
GRANT SELECT, INSERT ON audit_chain TO audit_sealer_role;

-- Usage Note: Sealer process must execute:
-- SELECT pg_advisory_xact_lock(37001);
-- INSERT INTO audit_chain ... SELECT ... ORDER BY row_ts ASC, row_id ASC;
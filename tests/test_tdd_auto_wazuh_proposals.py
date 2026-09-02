import sqlite3
from wazuh_proposals import validate_approval_token

def test_approval_token_expires_at_index():
    conn = sqlite3.connect(":memory:")
    indexes = conn.execute("PRAGMA index_list(approval_tokens)").fetchall()
    index_names = [row[1] for row in indexes]
    assert "expires_at" in index_names, "Missing index on approval_tokens.expires_at"
    validate_approval_token("test_hash", expires_at="2025-01-01")
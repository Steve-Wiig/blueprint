import pytest
import sqlite3
from slm_triage_worker import claim_job

def test_claim_job_runtime_error_on_third_claim():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE jobs (id INTEGER PRIMARY KEY, status TEXT)")
    claim_job(conn, 1)
    claim_job(conn, 2)
    with pytest.raises(RuntimeError):
        claim_job(conn, 3)
import sqlite3
from intake_wazuh import _init_triage_table

def test_init_triage_table_does_not_crash_on_existing_index():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE triages (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE INDEX idx_id ON triages(id)")
    _init_triage_table(conn)
    conn.close()
import sqlite3
from context_stitcher import stitch_context

def test_stitch_context_does_not_break_transaction_atomicity():
    conn = sqlite3.connect(":memory:")
    conn.execute("BEGIN")
    stitch_context(conn)
    assert conn.in_transaction
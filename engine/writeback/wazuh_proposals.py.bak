import argparse
import sqlite3
import sys
import json
import os
from datetime import datetime

# LOCAL-SOC-SLM Blueprint v11.6.0 - Wazuh Proposal Adapter
# Appendix Q.3: Writeback Isolation Layer

DB_PATH = "/var/lib/wazuh-slm/proposals.db"

def init_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS proposals 
                          (id INTEGER PRIMARY KEY, key TEXT, value TEXT, 
                           status TEXT, created_at TIMESTAMP)''')
        conn.commit()
        conn.close()
    except Exception:
        sys.exit(2)

def check_approval_gate(key):
    # Gate check: Ensure no direct injection into production CDBs
    # Returns True if key is permitted for proposal
    return not key.startswith("wazuh-internal-")

def main():
    parser = argparse.ArgumentParser(description="Wazuh CDB Proposal Adapter")
    parser.add_argument("--key", required=True, help="CDB Key")
    parser.add_argument("--value", required=True, help="CDB Value")
    args = parser.parse_args()

    if not os.path.exists(os.path.dirname(DB_PATH)):
        sys.exit(3)

    if not check_approval_gate(args.key):
        sys.exit(1)

    try:
        init_db()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO proposals (key, value, status, created_at) VALUES (?, ?, ?, ?)",
                       (args.key, args.value, 'PENDING', datetime.now()))
        conn.commit()
        conn.close()
        sys.exit(0)
    except Exception:
        sys.exit(1)

if __name__ == "__main__":
    main()
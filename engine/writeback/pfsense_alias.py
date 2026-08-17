import argparse
import sys
import json
import sqlite3
from datetime import datetime

# LOCAL-SOC-SLM Blueprint v11.6.0 - Appendix Q.5
# Alias-Table Writeback Adapter (Proposal-Only Mode)

DB_PATH = "soc_proposals.db"

def init_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS alias_proposals
                          (id INTEGER PRIMARY KEY, alias_name TEXT, ip_address TEXT, 
                           status TEXT, created_at TIMESTAMP)''')
        conn.commit()
        conn.close()
    except Exception:
        sys.exit(2)

def store_proposal(name, ip):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO alias_proposals (alias_name, ip_address, status, created_at) VALUES (?, ?, ?, ?)",
                       (name, ip, 'PENDING', datetime.now()))
        conn.commit()
        conn.close()
        print(f"PROPOSAL_STORED: {name} -> {ip}")
    except Exception:
        sys.exit(1)

def rollback_plan():
    print("ROLLBACK_REFERENCE: To revert, execute 'DELETE FROM alias_proposals WHERE status = \"PENDING\"' in sqlite3.")

def main():
    parser = argparse.ArgumentParser(description="pfSense Alias Writeback Adapter")
    parser.add_argument("--name", required=True, help="Alias name")
    parser.add_argument("--ip", required=True, help="IP address to add")
    parser.add_argument("--mode", choices=['proposal'], default='proposal', help="Operation mode")
    
    args = parser.parse_args()
    
    init_db()
    
    if args.mode == 'proposal':
        store_proposal(args.name, args.ip)
        rollback_plan()
        sys.exit(0)
    else:
        sys.exit(2)

if __name__ == "__main__":
    main()
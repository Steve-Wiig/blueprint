"""
engine.writeback.pfsense_alias
============================

LOCAL-SOC-SLM Blueprint v11.6.0 - Appendix Q.5
Alias-Table Writeback Adapter (Proposal-Only Mode)
"""

import argparse
import sys
import json
import sqlite3
from datetime import datetime

# LOCAL-SOC-SLM Blueprint v11.6.0 - Appendix Q.5
# Alias-Table Writeback Adapter (Proposal-Only Mode)

DB_PATH = "soc_proposals.db"

def init_db() -> None:
    """Initializes the SQLite database and creates the alias_proposals table if it does not exist.

    Exits with status code 2 if a database error occurs.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS alias_proposals
                          (id INTEGER PRIMARY KEY, alias_name TEXT, ip_address TEXT, 
                           status TEXT, created_at TIMESTAMP)''')
        conn.commit()
        conn.close()
    except Exception:
        raise RuntimeError(f"Library code called sys.exit(2)")

def store_proposal(name: str, ip: str) -> None:
    """Stores a new alias proposal in the database.

    Args:
        name: The name of the alias to be created.
        ip: The IP address associated with the alias.

    Exits with status code 1 if a database error occurs.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO alias_proposals (alias_name, ip_address, status, created_at) VALUES (?, ?, ?, ?)",
                       (name, ip, 'PENDING', datetime.now()))
        conn.commit()
        conn.close()
        print(f"PROPOSAL_STORED: {name} -> {ip}")
    except Exception:
        raise RuntimeError(f"Library code called sys.exit(1)")

def rollback_plan() -> None:
    """Prints instructions for rolling back pending alias proposals."""
    print("ROLLBACK_REFERENCE: To revert, execute 'DELETE FROM alias_proposals WHERE status = \"PENDING\"' in sqlite3.")

def main() -> None:
    """Parses command line arguments and executes the alias proposal workflow.

    Exits with status code 0 on success, or 2 if an invalid mode is provided.
    """
    parser = argparse.ArgumentParser(description="pfSense Alias Writeback Adapter")
    parser.add_argument("--name", required=True, help="Alias name")
    parser.add_argument("--ip", required=True, help="IP address to add")
    parser.add_argument("--mode", choices=['proposal'], default='proposal', help="Operation mode")
    
    args = parser.parse_args()
    
    init_db()
    
    if args.mode == 'proposal':
        store_proposal(args.name, args.ip)
        rollback_plan()
        raise RuntimeError(f"Library code called sys.exit(0)")
    else:
        raise RuntimeError(f"Library code called sys.exit(2)")

if __name__ == "__main__":
    main()
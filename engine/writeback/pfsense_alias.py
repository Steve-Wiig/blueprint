import argparse
import logging
import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.getenv("SOC_PROPOSALS_DB", "soc_proposals.db")

PROPOSAL_STATUS_PENDING = 'PENDING'
MSG_PROPOSAL_STORED = 'PROPOSAL_STORED'
MSG_ROLLBACK_REFERENCE = 'ROLLBACK_REFERENCE'
MSG_ROLLBACK_DRYRUN = 'ROLLBACK_DRYRUN'
MSG_ROLLBACK_EXECUTED = 'ROLLBACK_EXECUTED'
AUDIT_ACTOR = 'pfsense_alias_adapter'
TABLE_ALIAS_PROPOSALS = 'alias_proposals'
TABLE_AUDIT_LOG = 'audit_log'


DDL_SCRIPT = f'''
CREATE TABLE IF NOT EXISTS {TABLE_ALIAS_PROPOSALS}
(id INTEGER PRIMARY KEY, alias_name TEXT, ip_address TEXT, 
 status TEXT, created_at TIMESTAMP);

CREATE TABLE IF NOT EXISTS {TABLE_AUDIT_LOG}
(id INTEGER PRIMARY KEY, operation_type TEXT, old_values TEXT, 
 new_values TEXT, actor TEXT, timestamp TIMESTAMP);

CREATE INDEX IF NOT EXISTS idx_{TABLE_ALIAS_PROPOSALS}_alias_name 
ON {TABLE_ALIAS_PROPOSALS}(alias_name);

CREATE INDEX IF NOT EXISTS idx_{TABLE_ALIAS_PROPOSALS}_ip_address 
ON {TABLE_ALIAS_PROPOSALS}(ip_address);

CREATE INDEX IF NOT EXISTS idx_{TABLE_ALIAS_PROPOSALS}_status 
ON {TABLE_ALIAS_PROPOSALS}(status);

CREATE INDEX IF NOT EXISTS idx_{TABLE_AUDIT_LOG}_operation_type 
ON {TABLE_AUDIT_LOG}(operation_type);

CREATE INDEX IF NOT EXISTS idx_{TABLE_AUDIT_LOG}_timestamp 
ON {TABLE_AUDIT_LOG}(timestamp);

CREATE TRIGGER IF NOT EXISTS audit_{TABLE_ALIAS_PROPOSALS}_insert
AFTER INSERT ON {TABLE_ALIAS_PROPOSALS}
BEGIN
    INSERT INTO {TABLE_AUDIT_LOG} (operation_type, old_values, new_values, actor, timestamp)
    VALUES ('INSERT', NULL, 
            json_object('id', NEW.id, 'alias_name', NEW.alias_name, 'ip_address', NEW.ip_address, 'status', NEW.status, 'created_at', NEW.created_at),
            '{AUDIT_ACTOR}', datetime('now'));
END;

CREATE TRIGGER IF NOT EXISTS audit_{TABLE_ALIAS_PROPOSALS}_update
AFTER UPDATE ON {TABLE_ALIAS_PROPOSALS}
BEGIN
    INSERT INTO {TABLE_AUDIT_LOG} (operation_type, old_values, new_values, actor, timestamp)
    VALUES ('UPDATE',
            json_object('id', OLD.id, 'alias_name', OLD.alias_name, 'ip_address', OLD.ip_address, 'status', OLD.status, 'created_at', OLD.created_at),
            json_object('id', NEW.id, 'alias_name', NEW.alias_name, 'ip_address', NEW.ip_address, 'status', NEW.status, 'created_at', NEW.created_at),
            '{AUDIT_ACTOR}', datetime('now'));
END;

CREATE TRIGGER IF NOT EXISTS audit_{TABLE_ALIAS_PROPOSALS}_delete
AFTER DELETE ON {TABLE_ALIAS_PROPOSALS}
BEGIN
    INSERT INTO {TABLE_AUDIT_LOG} (operation_type, old_values, new_values, actor, timestamp)
    VALUES ('DELETE',
            json_object('id', OLD.id, 'alias_name', OLD.alias_name, 'ip_address', OLD.ip_address, 'status', OLD.status, 'created_at', OLD.created_at),
            NULL,
            '{AUDIT_ACTOR}', datetime('now'));
END;
'''


def init_db() -> None:
    """Initializes the SQLite database and creates tables, indexes, and triggers.

    Raises RuntimeError if a database error occurs.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.executescript(DDL_SCRIPT)
        conn.commit()
        conn.close()
    except Exception:
        raise RuntimeError("Database initialization failed")


def store_proposal(name: str, ip: str) -> None:
    """Stores a new alias proposal in the database.

    Args:
        name: The name of the alias to be created.
        ip: The IP address associated with the alias.

    Raises RuntimeError if a database error occurs.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(f"INSERT INTO {TABLE_ALIAS_PROPOSALS} (alias_name, ip_address, status, created_at) VALUES (?, ?, ?, ?)",
                       (name, ip, PROPOSAL_STATUS_PENDING, datetime.now(timezone.utc)))
        conn.commit()
        conn.close()
        print(f"{MSG_PROPOSAL_STORED}: {name} -> {ip}")
    except Exception:
        raise RuntimeError("Failed to store proposal")


def rollback_plan() -> None:
    """Prints instructions for rolling back pending alias proposals."""
    print(f"{MSG_ROLLBACK_REFERENCE}: To revert, execute 'DELETE FROM {TABLE_ALIAS_PROPOSALS} WHERE status = \"{PROPOSAL_STATUS_PENDING}\"' in sqlite3.")


def rollback_execute(approved: bool = False) -> int:
    """Executes rollback of pending alias proposals.

    Args:
        approved: Must be True to confirm execution. If False, performs dry-run only.

    Returns:
        Number of rows that would be deleted (dry-run) or were deleted (executed).

    Raises RuntimeError if a database error occurs or if not approved.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute(f"SELECT COUNT(*) FROM {TABLE_ALIAS_PROPOSALS} WHERE status = ?", (PROPOSAL_STATUS_PENDING,))
        count = cursor.fetchone()[0]
        
        if not approved:
            conn.close()
            logging.info(f"{MSG_ROLLBACK_DRYRUN}: Would delete {count} pending proposal(s)")
            return count
        
        cursor.execute(f"DELETE FROM {TABLE_ALIAS_PROPOSALS} WHERE status = ?", (PROPOSAL_STATUS_PENDING,))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        logging.info(f"{MSG_ROLLBACK_EXECUTED}: Deleted {deleted} pending proposal(s)")
        return deleted
    except Exception:
        raise RuntimeError("Rollback execution failed")


def main() -> None:
    """Parses command line arguments and executes the alias proposal workflow.

    Raises RuntimeError on success or if an invalid mode is provided.
    """
    parser = argparse.ArgumentParser(description="pfSense Alias Writeback Adapter")
    parser.add_argument("--name", required=True, help="Alias name")
    parser.add_argument("--ip", required=True, help="IP address to add")
    parser.add_argument("--mode", choices=['proposal', 'rollback'], default='proposal', help="Operation mode")
    parser.add_argument("--approved", action="store_true", help="Confirm rollback execution (required for rollback mode)")
    
    args = parser.parse_args()
    
    init_db()
    
    if args.mode == 'proposal':
        store_proposal(args.name, args.ip)
        rollback_plan()
        raise RuntimeError("Operation completed successfully")
    elif args.mode == 'rollback':
        if not args.approved:
            raise RuntimeError("Rollback requires --approved flag for confirmation")
        rollback_execute(approved=True)
        raise RuntimeError("Rollback completed successfully")
    else:
        raise RuntimeError("Invalid operation mode")


if __name__ == "__main__":
    main()
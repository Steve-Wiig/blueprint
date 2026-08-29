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

INSERT_PROPOSAL_SQL = (
    "INSERT INTO alias_proposals (alias_name, ip_address, status, created_at) "
    "VALUES (?, ?, ?, ?)"
)
SELECT_PENDING_COUNT_SQL = (
    "SELECT COUNT(*) FROM alias_proposals WHERE status = ?"
)
DELETE_PENDING_SQL = (
    "DELETE FROM alias_proposals WHERE status = ?"
)
ROLLBACK_REFERENCE_MSG = (
    "ROLLBACK_REFERENCE: To revert, execute 'DELETE FROM alias_proposals "
    "WHERE status = \"PENDING\"' in sqlite3."
)


DDL_SCRIPT = '''
CREATE TABLE IF NOT EXISTS alias_proposals
(id INTEGER PRIMARY KEY, alias_name TEXT, ip_address TEXT, 
 status TEXT, created_at TIMESTAMP);

CREATE TABLE IF NOT EXISTS audit_log
(id INTEGER PRIMARY KEY, operation_type TEXT, old_values TEXT, 
 new_values TEXT, actor TEXT, timestamp TIMESTAMP);

CREATE INDEX IF NOT EXISTS idx_alias_proposals_alias_name 
ON alias_proposals(alias_name);

CREATE INDEX IF NOT EXISTS idx_alias_proposals_ip_address 
ON alias_proposals(ip_address);

CREATE INDEX IF NOT EXISTS idx_alias_proposals_status 
ON alias_proposals(status);

CREATE INDEX IF NOT EXISTS idx_audit_log_operation_type 
ON audit_log(operation_type);

CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp 
ON audit_log(timestamp);

CREATE TRIGGER IF NOT EXISTS audit_alias_proposals_insert
AFTER INSERT ON alias_proposals
BEGIN
    INSERT INTO audit_log (operation_type, old_values, new_values, actor, timestamp)
    VALUES ('INSERT', NULL, 
            json_object('id', NEW.id, 'alias_name', NEW.alias_name, 'ip_address', NEW.ip_address, 'status', NEW.status, 'created_at', NEW.created_at),
            'pfsense_alias_adapter', datetime('now'));
END;

CREATE TRIGGER IF NOT EXISTS audit_alias_proposals_update
AFTER UPDATE ON alias_proposals
BEGIN
    INSERT INTO audit_log (operation_type, old_values, new_values, actor, timestamp)
    VALUES ('UPDATE',
            json_object('id', OLD.id, 'alias_name', OLD.alias_name, 'ip_address', OLD.ip_address, 'status', OLD.status, 'created_at', OLD.created_at),
            json_object('id', NEW.id, 'alias_name', NEW.alias_name, 'ip_address', NEW.ip_address, 'status', NEW.status, 'created_at', NEW.created_at),
            'pfsense_alias_adapter', datetime('now'));
END;

CREATE TRIGGER IF NOT EXISTS audit_alias_proposals_delete
AFTER DELETE ON alias_proposals
BEGIN
    INSERT INTO audit_log (operation_type, old_values, new_values, actor, timestamp)
    VALUES ('DELETE',
            json_object('id', OLD.id, 'alias_name', OLD.alias_name, 'ip_address', OLD.ip_address, 'status', OLD.status, 'created_at', OLD.created_at),
            NULL,
            'pfsense_alias_adapter', datetime('now'));
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
        cursor.execute(INSERT_PROPOSAL_SQL,
                       (name, ip, PROPOSAL_STATUS_PENDING, datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
        print(f"{MSG_PROPOSAL_STORED}: {name} -> {ip}")
    except Exception:
        raise RuntimeError("Failed to store proposal")


def rollback_plan() -> None:
    """Prints instructions for rolling back pending alias proposals."""
    print(ROLLBACK_REFERENCE_MSG)

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
        
        cursor.execute(SELECT_PENDING_COUNT_SQL, (PROPOSAL_STATUS_PENDING,))
        count = cursor.fetchone()[0]
        
        if not approved:
            conn.close()
            logging.info(MSG_ROLLBACK_DRYRUN + ": Would delete " + str(count) + " pending proposal(s)")
            return count
        
        cursor.execute(DELETE_PENDING_SQL, (PROPOSAL_STATUS_PENDING,))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        logging.info(MSG_ROLLBACK_EXECUTED + ": Deleted " + str(deleted) + " pending proposal(s)")
        return deleted
    except Exception:
        raise RuntimeError("Rollback execution failed")


def main() -> None:
    """Parses command line arguments and executes the alias proposal workflow.

    Raises RuntimeError if an invalid mode is provided.
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
    elif args.mode == 'rollback':
        if not args.approved:
            raise RuntimeError("Rollback requires --approved flag for confirmation")
        rollback_execute(approved=True)
    else:
        raise RuntimeError("Invalid operation mode")

if __name__ == "__main__":
    main()
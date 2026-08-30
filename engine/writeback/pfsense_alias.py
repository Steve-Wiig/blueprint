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
    f"INSERT INTO {TABLE_ALIAS_PROPOSALS} (alias_name, ip_address, status, created_at) "
    "VALUES (?, ?, ?, ?)"
)
SELECT_PENDING_COUNT_SQL = (
    f"SELECT COUNT(*) FROM {TABLE_ALIAS_PROPOSALS} WHERE status = ?"
)
DELETE_PENDING_SQL = (
    f"DELETE FROM {TABLE_ALIAS_PROPOSALS} WHERE status = ?"
)
ROLLBACK_REFERENCE_MSG = (
    f"ROLLBACK_REFERENCE: To revert, execute 'DELETE FROM {TABLE_ALIAS_PROPOSALS} "
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


def init_db(conn: sqlite3.Connection | None = None) -> None:
    """Initializes the SQLite database and creates tables, indexes, and triggers.

    Args:
        conn: Optional existing connection to use. If not provided, creates a new one.

    Raises RuntimeError if a database error occurs.
    """
    own_conn = False
    try:
        if conn is None:
            conn = sqlite3.connect(DB_PATH)
            own_conn = True
        conn.executescript(DDL_SCRIPT)
        conn.commit()
    except Exception:
        raise RuntimeError("Database initialization failed")
    finally:
        if own_conn and conn:
            conn.close()


def store_proposal(name: str, ip: str, conn: sqlite3.Connection | None = None) -> None:
    """Stores a new alias proposal in the database.

    Args:
        name: The name of the alias to be created.
        ip: The IP address associated with the alias.
        conn: Optional existing connection to use. If not provided, creates a new one.

    Raises RuntimeError if a database error occurs.
    """
    own_conn = False
    try:
        if conn is None:
            conn = sqlite3.connect(DB_PATH)
            own_conn = True
        cursor = conn.cursor()
        cursor.execute(INSERT_PROPOSAL_SQL,
                       (name, ip, PROPOSAL_STATUS_PENDING, datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        print(f"{MSG_PROPOSAL_STORED}: {name} -> {ip}")
    except Exception:
        raise RuntimeError("Failed to store proposal")
    finally:
        if own_conn and conn:
            conn.close()


def rollback_plan() -> None:
    """Prints instructions for rolling back pending alias proposals."""
    print(ROLLBACK_REFERENCE_MSG)

def rollback_execute(approved: bool = False, conn: sqlite3.Connection | None = None) -> int:
    """Executes rollback of pending alias proposals.

    Args:
        approved: Must be True to confirm execution. If False, performs dry-run only.
        conn: Optional existing connection to use. If not provided, creates a new one.

    Returns:
        Number of rows that would be deleted (dry-run) or were deleted (executed).

    Raises RuntimeError if a database error occurs or if not approved.
    """
    own_conn = False
    try:
        if conn is None:
            conn = sqlite3.connect(DB_PATH)
            own_conn = True
        cursor = conn.cursor()
        
        cursor.execute(SELECT_PENDING_COUNT_SQL, (PROPOSAL_STATUS_PENDING,))
        count = cursor.fetchone()[0]
        
        if not approved:
            print(f"{MSG_ROLLBACK_DRYRUN}: Would delete {count} pending proposal(s)")
            return count
        
        cursor.execute(DELETE_PENDING_SQL, (PROPOSAL_STATUS_PENDING,))
        deleted = cursor.rowcount
        conn.commit()
        print(f"{MSG_ROLLBACK_EXECUTED}: Deleted {deleted} pending proposal(s)")
        return deleted
    except Exception:
        raise RuntimeError("Rollback execution failed")
    finally:
        if own_conn and conn:
            conn.close()


def main() -> None:
    """Parses command line arguments and executes the alias proposal workflow.

    Raises RuntimeError if an invalid mode is provided.
    """
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    parser = argparse.ArgumentParser(description="pfSense Alias Writeback Adapter")
    parser.add_argument("--name", required=True, help="Alias name")
    parser.add_argument("--ip", required=True, help="IP address to add")
    parser.add_argument("--mode", choices=['proposal', 'rollback'], default='proposal', help="Operation mode")
    parser.add_argument("--approved", action="store_true", help="Confirm rollback execution (required for rollback mode)")
    
    args = parser.parse_args()
    
    conn = sqlite3.connect(DB_PATH)
    try:
        init_db(conn)
        
        if args.mode == 'proposal':
            store_proposal(args.name, args.ip, conn)
            rollback_plan()
        elif args.mode == 'rollback':
            if not args.approved:
                raise RuntimeError("Rollback requires --approved flag for confirmation")
            rollback_execute(approved=True, conn=conn)
        else:
            raise RuntimeError("Invalid operation mode")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
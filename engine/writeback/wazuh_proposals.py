import argparse
import sqlite3
import sys
import json
import os
import atexit
import functools
import threading
import time
from datetime import datetime, timezone
from typing import NoReturn, Optional, List, Tuple
import hashlib

# LOCAL-SOC-SLM Blueprint v11.6.0 - Wazuh Proposal Adapter
# Appendix Q.3: Writeback Isolation Layer

DB_PATH: str = os.environ.get("WAZUH_PROPOSALS_DB", "/var/lib/wazuh-slm/proposals.db")

_db_initialized: bool = False
_db_connection: Optional[sqlite3.Connection] = None

# Batch audit logging for high-throughput scenarios
_audit_batch: List[Tuple] = []
_audit_batch_lock = threading.Lock()
_AUDIT_BATCH_SIZE = 100
_AUDIT_FLUSH_INTERVAL = 5.0
_AUDIT_MAX_RETRIES = 3
_audit_flush_timer: Optional[threading.Timer] = None
_batch_mode_enabled = False

# Dead-letter queue for entries that exceed max retries
_dead_letter_queue: List[Tuple] = []
_dead_letter_lock = threading.Lock()


class ProposalError(Exception):
    """Base exception for proposal adapter errors."""
    exit_code: int = 1
    default_message: str = "Proposal error"

    def __init__(self, message: Optional[str] = None, exit_code: Optional[int] = None):
        msg = message if message is not None else self.default_message
        super().__init__(msg)
        self.exit_code = exit_code if exit_code is not None else self.exit_code


class ProposalRejectedError(ProposalError):
    """Raised when a proposal is rejected (denylist, validation)."""
    exit_code = 1
    default_message = "Proposal rejected"


class ProposalStorageError(ProposalError):
    """Raised when database/storage operations fail."""
    exit_code = 2
    default_message = "Storage operation failed"


class ProposalDirectoryError(ProposalError):
    """Raised when required directory is missing."""
    exit_code = 3
    default_message = "Required directory missing"


class ProposalApprovalError(ProposalError):
    """Raised when approval validation fails."""
    exit_code = 4
    default_message = "Approval validation failed"


class ProposalSuccess(ProposalError):
    """Raised on successful proposal submission."""
    exit_code = 0
    default_message = "Proposal stored successfully"


def _load_config() -> None:
    """Load and validate configuration from environment variables."""
    global _AUDIT_BATCH_SIZE, _AUDIT_FLUSH_INTERVAL, _AUDIT_MAX_RETRIES, _batch_mode_enabled
    
    # Validate WAZUH_AUDIT_BATCH_SIZE
    batch_size_str = os.environ.get("WAZUH_AUDIT_BATCH_SIZE", "100")
    try:
        batch_size = int(batch_size_str)
        if batch_size <= 0:
            print(f"WARNING: WAZUH_AUDIT_BATCH_SIZE must be > 0, got {batch_size}. Using default 100.", file=sys.stderr)
            _AUDIT_BATCH_SIZE = 100
        else:
            _AUDIT_BATCH_SIZE = batch_size
    except ValueError:
        print(f"WARNING: Invalid WAZUH_AUDIT_BATCH_SIZE '{batch_size_str}'. Using default 100.", file=sys.stderr)
        _AUDIT_BATCH_SIZE = 100
    
    # Validate WAZUH_AUDIT_FLUSH_INTERVAL
    flush_interval_str = os.environ.get("WAZUH_AUDIT_FLUSH_INTERVAL", "5.0")
    try:
        flush_interval = float(flush_interval_str)
        if flush_interval <= 0:
            print(f"WARNING: WAZUH_AUDIT_FLUSH_INTERVAL must be > 0, got {flush_interval}. Using default 5.0.", file=sys.stderr)
            _AUDIT_FLUSH_INTERVAL = 5.0
        else:
            _AUDIT_FLUSH_INTERVAL = flush_interval
    except ValueError:
        print(f"WARNING: Invalid WAZUH_AUDIT_FLUSH_INTERVAL '{flush_interval_str}'. Using default 5.0.", file=sys.stderr)
        _AUDIT_FLUSH_INTERVAL = 5.0
    
    # Validate WAZUH_AUDIT_MAX_RETRIES
    max_retries_str = os.environ.get("WAZUH_AUDIT_MAX_RETRIES", "3")
    try:
        max_retries = int(max_retries_str)
        if max_retries < 0:
            print(f"WARNING: WAZUH_AUDIT_MAX_RETRIES must be >= 0, got {max_retries}. Using default 3.", file=sys.stderr)
            _AUDIT_MAX_RETRIES = 3
        else:
            _AUDIT_MAX_RETRIES = max_retries
    except ValueError:
        print(f"WARNING: Invalid WAZUH_AUDIT_MAX_RETRIES '{max_retries_str}'. Using default 3.", file=sys.stderr)
        _AUDIT_MAX_RETRIES = 3
    
    # Validate WAZUH_AUDIT_BATCH_MODE
    batch_mode_str = os.environ.get("WAZUH_AUDIT_BATCH_MODE", "false").lower()
    _batch_mode_enabled = batch_mode_str == "true"


def _get_connection() -> sqlite3.Connection:
    """Get or create a persistent database connection with WAL mode enabled."""
    global _db_connection
    if _db_connection is None:
        _db_connection = sqlite3.connect(DB_PATH)
        _db_connection.execute("PRAGMA journal_mode=WAL")
        _db_connection.execute("PRAGMA synchronous=NORMAL")
        _db_connection.execute("PRAGMA busy_timeout=5000")
        atexit.register(_close_connection)
    return _db_connection


def _close_connection() -> None:
    """Close the persistent database connection."""
    global _db_connection, _audit_flush_timer
    if _audit_flush_timer is not None:
        _audit_flush_timer.cancel()
        _audit_flush_timer = None
    _flush_audit_batch()
    if _db_connection is not None:
        _db_connection.close()
        _db_connection = None


def _flush_audit_batch() -> None:
    """Flush accumulated audit log entries to database."""
    global _audit_batch, _audit_flush_timer, _dead_letter_queue
    with _audit_batch_lock:
        if not _audit_batch:
            return
        batch = _audit_batch[:]
        _audit_batch.clear()
    
    if not batch:
        return
    
    # Generate single timestamp for this flush cycle
    flush_timestamp = datetime.now(timezone.utc)
    
    # Prepare batch for insertion with unified timestamp
    insert_batch = []
    for entry in batch:
        # entry: (proposal_id, action, old_status, new_status, changed_by, changed_at, retry_count)
        # Replace timestamp with flush_timestamp for batch efficiency
        insert_entry = entry[:5] + (flush_timestamp,)
        insert_batch.append(insert_entry)
    
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.executemany(
            "INSERT INTO audit_log (proposal_id, action, old_status, new_status, changed_by, changed_at) VALUES (?, ?, ?, ?, ?, ?)",
            insert_batch
        )
        conn.commit()
    except sqlite3.Error:
        # On failure, increment retry count and re-queue entries that haven't exceeded max retries
        # Move entries that exceeded max retries to dead-letter queue
        retry_batch = []
        dead_letter_entries = []
        for entry in batch:
            # entry format: (proposal_id, action, old_status, new_status, changed_by, changed_at, retry_count)
            retry_count = entry[6] if len(entry) > 6 else 0
            if retry_count < _AUDIT_MAX_RETRIES:
                # Re-queue with incremented retry count, using flush_timestamp
                retry_entry = entry[:5] + (flush_timestamp, retry_count + 1)
                retry_batch.append(retry_entry)
            else:
                dead_letter_entries.append(entry)
        
        with _audit_batch_lock:
            # Prepend retry batch so they're tried first, but with backoff via timer
            _audit_batch = retry_batch + _audit_batch
        
        if dead_letter_entries:
            with _dead_letter_lock:
                _dead_letter_queue.extend(dead_letter_entries)
            # Log dead-letter entries to stderr for visibility
            for entry in dead_letter_entries:
                print(f"DEAD-LETTER: Audit entry failed after {_AUDIT_MAX_RETRIES} retries: {entry}", file=sys.stderr)
    finally:
        if _batch_mode_enabled:
            _schedule_audit_flush()

def _schedule_audit_flush() -> None:
    """Schedule the next audit batch flush."""
    global _audit_flush_timer
    if _audit_flush_timer is not None:
        _audit_flush_timer.cancel()
    _audit_flush_timer = threading.Timer(_AUDIT_FLUSH_INTERVAL, _flush_audit_batch)
    _audit_flush_timer.daemon = True
    _audit_flush_timer.start()


def _queue_audit_entry(proposal_id: int, action: str, old_status: Optional[str], 
                       new_status: str, changed_by: str) -> None:
    """Queue an audit entry for batch writing."""
    if not _batch_mode_enabled:
        return
    # Entry format: (proposal_id, action, old_status, new_status, changed_by, changed_at, retry_count)
    entry = (proposal_id, action, old_status, new_status, changed_by, datetime.now(timezone.utc), 0)
    with _audit_batch_lock:
        _audit_batch.append(entry)
        if len(_audit_batch) >= _AUDIT_BATCH_SIZE:
            _flush_audit_batch()
        else:
            _schedule_audit_flush()

def init_db() -> None:
    """Initializes the SQLite database and creates the proposals table if it does not exist.

    Raises:
        ProposalStorageError: If database initialization fails.
    """
    global _db_initialized, _audit_flush_timer
    if _db_initialized:
        return
    try:
        # Determine cross-platform data directory (platformdirs preferred, fallback to ./data)
        try:
            import platformdirs
            data_dir = platformdirs.user_data_dir("wazuh-slm", "wazuh")
        except ImportError:
            data_dir = os.path.join(os.path.dirname(__file__), "data")
        os.makedirs(data_dir, exist_ok=True)
        db_path = os.path.join(data_dir, "proposals.db")
        os.environ["WAZUH_DB_PATH"] = db_path

        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS proposals 
                          (id INTEGER PRIMARY KEY, key TEXT, value TEXT, 
                           status TEXT, created_at TIMESTAMP, changed_by TEXT)''')
        cursor.execute('''CREATE INDEX IF NOT EXISTS idx_proposals_key 
                          ON proposals(key)''')
        cursor.execute('''CREATE INDEX IF NOT EXISTS idx_proposals_status 
                          ON proposals(status)''')
        
        # Audit log table for append-only trail (Section 30 compliance)
        cursor.execute('''CREATE TABLE IF NOT EXISTS audit_log
                          (id INTEGER PRIMARY KEY, proposal_id INTEGER, action TEXT,
                           old_status TEXT, new_status TEXT, changed_by TEXT,
                           changed_at TIMESTAMP,
                           FOREIGN KEY(proposal_id) REFERENCES proposals(id))''')
        cursor.execute('''CREATE INDEX IF NOT EXISTS idx_audit_log_proposal_id
                          ON audit_log(proposal_id)''')
        cursor.execute('''CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp
                          ON audit_log(changed_at)''')
        
        # Approval tokens table for approval-gated mutations (Section 24 compliance)
        cursor.execute('''CREATE TABLE IF NOT EXISTS approval_tokens
                          (id INTEGER PRIMARY KEY, token_hash TEXT UNIQUE,
                           description TEXT, created_at TIMESTAMP,
                           expires_at TIMESTAMP, is_active INTEGER DEFAULT 1)''')
        cursor.execute('''CREATE INDEX IF NOT EXISTS idx_approval_tokens_hash
                          ON approval_tokens(token_hash)''')
        
        # Trigger on INSERT to proposals (kept for compliance)
        # SQLite provides NEW.* for all columns in AFTER INSERT triggers.
        # Ensure changed_by is captured from the INSERT statement; default to 'system' if NULL.
        cursor.execute('''CREATE TRIGGER IF NOT EXISTS audit_proposals_insert
                          AFTER INSERT ON proposals
                          BEGIN
                              INSERT INTO audit_log (proposal_id, action, old_status, new_status, changed_by, changed_at)
                              VALUES (NEW.id, 'INSERT', NULL, NEW.status, COALESCE(NEW.changed_by, 'system'), datetime('now', 'utc'));
                          END;''')
        
        # Trigger on UPDATE of status column in proposals (kept for compliance)
        cursor.execute('''CREATE TRIGGER IF NOT EXISTS audit_proposals_status_change
                          AFTER UPDATE OF status ON proposals
                          WHEN OLD.status != NEW.status
                          BEGIN
                              INSERT INTO audit_log (proposal_id, action, old_status, new_status, changed_by, changed_at)
                              VALUES (NEW.id, 'STATUS_CHANGE', OLD.status, NEW.status, COALESCE(NEW.changed_by, 'system'), datetime('now', 'utc'));
                          END;''')
        
        conn.commit()
        _db_initialized = True
        
        if _batch_mode_enabled:
            _schedule_audit_flush()
    except sqlite3.Error as e:
        raise ProposalStorageError(f"Database initialization failed: {e}")

def check_approval_gate(key: str) -> bool:
    """Validates if a key is permitted for a proposal.

    Uses a denylist approach: keys starting with "wazuh-internal-" are reserved
    for internal Wazuh use and cannot be proposed via this adapter.

    Args:
        key: The CDB key to validate.

    Returns:
        True if the key is permitted for proposal, False if blocked by denylist.
    """
    # Denylist: block internal Wazuh keys to prevent direct injection into production CDBs
    return not key.startswith("wazuh-internal-")


def validate_approval_token(token: str) -> bool:
    """Validates an approval token against the approval_tokens table.

    Args:
        token: The approval token to validate.

    Returns:
        True if token is valid and active, False otherwise.
    """
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM approval_tokens WHERE token_hash = ? AND is_active = 1 AND (expires_at IS NULL OR expires_at > datetime('now'))",
            (token_hash,)
        )
        result = cursor.fetchone()
        return result is not None
    except sqlite3.Error:
        return False


def submit_proposal(key: str, value: str, changed_by: str = "cli") -> int:
    """Submit a new proposal for a CDB key/value pair.

    Args:
        key: The CDB key to propose.
        value: The proposed value.
        changed_by: Identifier of the submitter (default: "cli").

    Returns:
        The proposal ID.

    Raises:
        ProposalRejectedError: If key is blocked by denylist.
        ProposalStorageError: If database operation fails.
    """
    if not check_approval_gate(key):
        raise ProposalRejectedError(f"Key '{key}' is reserved for internal use (denylist)")
    
    init_db()
    
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO proposals (key, value, status, created_at, changed_by) VALUES (?, ?, 'pending', datetime('now', 'utc'), ?)",
            (key, value, changed_by)
        )
        conn.commit()
        proposal_id = cursor.lastrowid
        _queue_audit_entry(proposal_id, "SUBMIT", None, "pending", changed_by)
        return proposal_id
    except sqlite3.Error as e:
        raise ProposalStorageError(f"Failed to submit proposal: {e}")


def approve_proposal(proposal_id: int, approval_token: str, changed_by: str = "cli") -> None:
    """Approve a pending proposal using an approval token.

    Args:
        proposal_id: The ID of the proposal to approve.
        approval_token: The approval token for authorization.
        changed_by: Identifier of the approver (default: "cli").

    Raises:
        ProposalApprovalError: If token is invalid or proposal not found/pending.
        ProposalStorageError: If database operation fails.
    """
    if not validate_approval_token(approval_token):
        raise ProposalApprovalError("Invalid or expired approval token")
    
    init_db()
    
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT status FROM proposals WHERE id = ?",
            (proposal_id,)
        )
        row = cursor.fetchone()
        if row is None:
            raise ProposalApprovalError(f"Proposal {proposal_id} not found")
        if row[0] != "pending":
            raise ProposalApprovalError(f"Proposal {proposal_id} is not pending (status: {row[0]})")
        
        cursor.execute(
            "UPDATE proposals SET status = 'approved', changed_by = ? WHERE id = ?",
            (changed_by, proposal_id)
        )
        conn.commit()
        _queue_audit_entry(proposal_id, "APPROVE", "pending", "approved", changed_by)
    except sqlite3.Error as e:
        raise ProposalStorageError(f"Failed to approve proposal: {e}")


def reject_proposal(proposal_id: int, changed_by: str = "cli") -> None:
    """Reject a pending proposal.

    Args:
        proposal_id: The ID of the proposal to reject.
        changed_by: Identifier of the rejector (default: "cli").

    Raises:
        ProposalApprovalError: If proposal not found or not pending.
        ProposalStorageError: If database operation fails.
    """
    init_db()
    
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT status FROM proposals WHERE id = ?",
            (proposal_id,)
        )
        row = cursor.fetchone()
        if row is None:
            raise ProposalApprovalError(f"Proposal {proposal_id} not found")
        if row[0] != "pending":
            raise ProposalApprovalError(f"Proposal {proposal_id} is not pending (status: {row[0]})")
        
        cursor.execute(
            "UPDATE proposals SET status = 'rejected', changed_by = ? WHERE id = ?",
            (changed_by, proposal_id)
        )
        conn.commit()
        _queue_audit_entry(proposal_id, "REJECT", "pending", "rejected", changed_by)
    except sqlite3.Error as e:
        raise ProposalStorageError(f"Failed to reject proposal: {e}")


def get_proposal(proposal_id: int) -> Optional[dict]:
    """Retrieve a proposal by ID.

    Args:
        proposal_id: The ID of the proposal to retrieve.

    Returns:
        Dictionary with proposal data, or None if not found.
    """
    init_db()
    
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, key, value, status, created_at, changed_by FROM proposals WHERE id = ?",
            (proposal_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "key": row[1],
            "value": row[2],
            "status": row[3],
            "created_at": row[4],
            "changed_by": row[5]
        }
    except sqlite3.Error:
        return None


def list_proposals(status: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[dict]:
    """List proposals with optional status filter.

    Args:
        status: Optional status filter (pending, approved, rejected).
        limit: Maximum number of results (default: 100).
        offset: Pagination offset (default: 0).

    Returns:
        List of proposal dictionaries.
    """
    init_db()
    
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        if status:
            cursor.execute(
                "SELECT id, key, value, status, created_at, changed_by FROM proposals WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (status, limit, offset)
            )
        else:
            cursor.execute(
                "SELECT id, key, value, status, created_at, changed_by FROM proposals ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset)
            )
        rows = cursor.fetchall()
        return [
            {
                "id": row[0],
                "key": row[1],
                "value": row[2],
                "status": row[3],
                "created_at": row[4],
                "changed_by": row[5]
            }
            for row in rows
        ]
    except sqlite3.Error:
        return []


def get_audit_log(proposal_id: Optional[int] = None, limit: int = 100, offset: int = 0) -> List[dict]:
    """Retrieve audit log entries.

    Args:
        proposal_id: Optional proposal ID filter.
        limit: Maximum number of results (default: 100).
        offset: Pagination offset (default: 0).

    Returns:
        List of audit log entry dictionaries.
    """
    init_db()
    
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        if proposal_id is not None:
            cursor.execute(
                "SELECT id, proposal_id, action, old_status, new_status, changed_by, changed_at FROM audit_log WHERE proposal_id = ? ORDER BY changed_at DESC LIMIT ? OFFSET ?",
                (proposal_id, limit, offset)
            )
        else:
            cursor.execute(
                "SELECT id, proposal_id, action, old_status, new_status, changed_by, changed_at FROM audit_log ORDER BY changed_at DESC LIMIT ? OFFSET ?",
                (limit, offset)
            )
        rows = cursor.fetchall()
        return [
            {
                "id": row[0],
                "proposal_id": row[1],
                "action": row[2],
                "old_status": row[3],
                "new_status": row[4],
                "changed_by": row[5],
                "changed_at": row[6]
            }
            for row in rows
        ]
    except sqlite3.Error:
        return []


def create_approval_token(description: str, expires_at: Optional[str] = None) -> str:
    """Create a new approval token.

    Args:
        description: Human-readable description of the token purpose.
        expires_at: Optional ISO format expiration timestamp.

    Returns:
        The generated token (only shown once).

    Raises:
        ProposalStorageError: If database operation fails.
    """
    import secrets
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    init_db()
    
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO approval_tokens (token_hash, description, created_at, expires_at) VALUES (?, ?, datetime('now', 'utc'), ?)",
            (token_hash, description, expires_at)
        )
        conn.commit()
        return token
    except sqlite3.Error as e:
        raise ProposalStorageError(f"Failed to create approval token: {e}")


def revoke_approval_token(token: str) -> bool:
    """Revoke an approval token.

    Args:
        token: The token to revoke.

    Returns:
        True if token was found and revoked, False otherwise.
    """
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    init_db()
    
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE approval_tokens SET is_active = 0 WHERE token_hash = ?",
            (token_hash,)
        )
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error:
        return False


def list_approval_tokens(active_only: bool = True) -> List[dict]:
    """List approval tokens.

    Args:
        active_only: If True, only return active tokens (default: True).

    Returns:
        List of token dictionaries (hash not included for security).
    """
    init_db()
    
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        if active_only:
            cursor.execute(
                "SELECT id, description, created_at, expires_at, is_active FROM approval_tokens WHERE is_active = 1 ORDER BY created_at DESC"
            )
        else:
            cursor.execute(
                "SELECT id, description, created_at, expires_at, is_active FROM approval_tokens ORDER BY created_at DESC"
            )
        rows = cursor.fetchall()
        return [
            {
                "id": row[0],
                "description": row[1],
                "created_at": row[2],
                "expires_at": row[3],
                "is_active": bool(row[4])
            }
            for row in rows
        ]
    except sqlite3.Error:
        return []


def get_dead_letter_queue() -> List[dict]:
    """Retrieve dead-letter queue entries.

    Returns:
        List of dead-letter entry dictionaries.
    """
    with _dead_letter_lock:
        return [
            {
                "proposal_id": entry[0],
                "action": entry[1],
                "old_status": entry[2],
                "new_status": entry[3],
                "changed_by": entry[4],
                "changed_at": entry[5],
                "retry_count": entry[6] if len(entry) > 6 else 0
            }
            for entry in _dead_letter_queue
        ]


def clear_dead_letter_queue() -> int:
    """Clear the dead-letter queue.

    Returns:
        Number of entries cleared.
    """
    with _dead_letter_lock:
        count = len(_dead_letter_queue)
        _dead_letter_queue.clear()
        return count


def main() -> NoReturn:
    """CLI entry point for wazuh-proposal-adapter."""
    _load_config()
    
    parser = argparse.ArgumentParser(description="Wazuh Proposal Adapter - Submit and manage CDB proposals")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # submit
    submit_parser = subparsers.add_parser("submit", help="Submit a new proposal")
    submit_parser.add_argument("key", help="CDB key")
    submit_parser.add_argument("value", help="Proposed value")
    submit_parser.add_argument("--by", default="cli", help="Submitter identifier")
    
    # approve
    approve_parser = subparsers.add_parser("approve", help="Approve a proposal")
    approve_parser.add_argument("proposal_id", type=int, help="Proposal ID")
    approve_parser.add_argument("token", help="Approval token")
    approve_parser.add_argument("--by", default="cli", help="Approver identifier")
    
    # reject
    reject_parser = subparsers.add_parser("reject", help="Reject a proposal")
    reject_parser.add_argument("proposal_id", type=int, help="Proposal ID")
    reject_parser.add_argument("--by", default="cli", help="Rejector identifier")
    
    # get
    get_parser = subparsers.add_parser("get", help="Get a proposal by ID")
    get_parser.add_argument("proposal_id", type=int, help="Proposal ID")
    
    # list
    list_parser = subparsers.add_parser("list", help="List proposals")
    list_parser.add_argument("--status", choices=["pending", "approved", "rejected"], help="Filter by status")
    list_parser.add_argument("--limit", type=int, default=100, help="Max results")
    list_parser.add_argument("--offset", type=int, default=0, help="Pagination offset")
    
    # audit
    audit_parser = subparsers.add_parser("audit", help="View audit log")
    audit_parser.add_argument("--proposal-id", type=int, help="Filter by proposal ID")
    audit_parser.add_argument("--limit", type=int, default=100, help="Max results")
    audit_parser.add_argument("--offset", type=int, default=0, help="Pagination offset")
    
    # token-create
    token_create_parser = subparsers.add_parser("token-create", help="Create approval token")
    token_create_parser.add_argument("description", help="Token description")
    token_create_parser.add_argument("--expires", help="Expiration timestamp (ISO format)")
    
    # token-revoke
    token_revoke_parser = subparsers.add_parser("token-revoke", help="Revoke approval token")
    token_revoke_parser.add_argument("token", help="Token to revoke")
    
    # token-list
    token_list_parser = subparsers.add_parser("token-list", help="List approval tokens")
    token_list_parser.add_argument("--all", action="store_true", help="Include inactive tokens")
    
    # dead-letter
    dlq_parser = subparsers.add_parser("dead-letter", help="View dead-letter queue")
    dlq_clear_parser = subparsers.add_parser("dead-letter-clear", help="Clear dead-letter queue")
    
    args = parser.parse_args()
    
    try:
        if args.command == "submit":
            proposal_id = submit_proposal(args.key, args.value, args.by)
            print(f"Proposal submitted with ID: {proposal_id}")
            raise ProposalSuccess()
        
        elif args.command == "approve":
            approve_proposal(args.proposal_id, args.token, args.by)
            print(f"Proposal {args.proposal_id} approved")
            raise ProposalSuccess()
        
        elif args.command == "reject":
            reject_proposal(args.proposal_id, args.by)
            print(f"Proposal {args.proposal_id} rejected")
            raise ProposalSuccess()
        
        elif args.command == "get":
            proposal = get_proposal(args.proposal_id)
            if proposal:
                print(json.dumps(proposal, indent=2))
            else:
                print(f"Proposal {args.proposal_id} not found", file=sys.stderr)
                sys.exit(1)
        
        elif args.command == "list":
            proposals = list_proposals(args.status, args.limit, args.offset)
            print(json.dumps(proposals, indent=2))
        
        elif args.command == "audit":
            audit = get_audit_log(args.proposal_id, args.limit, args.offset)
            print(json.dumps(audit, indent=2))
        
        elif args.command == "token-create":
            token = create_approval_token(args.description, args.expires)
            print(f"Token created (save this - it won't be shown again): {token}")
        
        elif args.command == "token-revoke":
            if revoke_approval_token(args.token):
                print("Token revoked")
            else:
                print("Token not found", file=sys.stderr)
                sys.exit(1)
        
        elif args.command == "token-list":
            tokens = list_approval_tokens(active_only=not args.all)
            print(json.dumps(tokens, indent=2))
        
        elif args.command == "dead-letter":
            dlq = get_dead_letter_queue()
            print(json.dumps(dlq, indent=2))
        
        elif args.command == "dead-letter-clear":
            count = clear_dead_letter_queue()
            print(f"Cleared {count} dead-letter entries")
        
    except ProposalError as e:
        print(str(e), file=sys.stderr)
        sys.exit(e.exit_code)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
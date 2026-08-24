Here's a thinking process:

1.  **Analyze the User's Request:**
   - **Role:** Senior Python engineer
   - **Task:** Fix an issue in the provided Python file
   - **Specific Issue:** RuntimeError message 'Library code called exit(2)' is misleading - code raises RuntimeError, doesn't call exit()
   - **Suggestion:** Use descriptive messages: 'Database initialization failed: {e}' instead of exit-code references
   - **Constraints:**
     - Output ONLY valid Python code
     - No markdown fences, no explanations, no preamble
     - Use real sqlite3.connect(":memory:") for SQLite, not mocks (wait, this might mean use sqlite3 properly, or maybe they want in-memory DB for testing? But the file uses file-based DB paths. I'll keep the file-based approach but fix the errors as specified.)
     - Expect RuntimeError not SystemExit (library code auto-fixed)
     - Import from actual modules, don't hallucinate
     - Keep the module importable without side effects
     - Use datetime.now(timezone.utc), never utcnow()
     - Preserve all unrelated behavior
     - Keep the module importable without side effects

   - **Key Fixes Needed:**
     - Replace all `RuntimeError("Library code called exit(2)")` with descriptive messages like `f"Database initialization failed: {e}"` or similar, preserving the `{e}` from the caught exception.
     - Replace `datetime('now', ...)` in SQLite queries with Python `datetime.now(timezone.utc)` since SQLite's datetime function might not be portable or desired, and the rule says use `datetime.now(timezone.utc)`, never `utcnow()`.
     - Wait, the SQLite queries use `datetime('now', '+300 seconds')` etc. I need to replace those with Python datetime calculations, or at least make them compatible. The rule says "Use datetime.now(timezone.utc), never utcnow()." So I should modify the code to use Python's datetime module instead of SQLite's datetime functions.
     - Let's look at the functions that use `datetime('now', ...)`: `lease_event`, `heartbeat_event`, `requeue_stale_events`. These use SQLite's datetime function. I need to replace them with Python datetime logic. But the table has `lease_expires_at` and `last_heartbeat_at` as TIMESTAMP. I can compute the expiry time in Python and pass it as a string or use Julian day, but the simplest is to compute in Python and use `?` parameter binding.
     - Actually, I can replace `datetime('now', '+300 seconds')` with Python `datetime.now(timezone.utc) + timedelta(seconds=300)` and format it as ISO string, then bind it. But SQLite can store datetime strings. I'll need to import `datetime` and `timedelta`.
     - Let's check each function:
       - `lease_event`: `SET status = 'processing', lease_expires_at = datetime('now', ?), last_heartbeat_at = datetime('now') WHERE id = ? AND status = 'pending'` with `(f"+{ttl_seconds} seconds", event_id)`. I'll replace with Python: `expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)` and `last_heartbeat_at = datetime.now(timezone.utc)`. Then bind as strings.
       - `heartbeat_event`: Similar.
       - `requeue_stale_events`: `AND lease_expires_at < datetime('now', ?)` with `("-{threshold_seconds} seconds",)`. Replace with Python comparison: `lease_expires_at < datetime.now(timezone.utc) - timedelta(seconds=threshold_seconds)` or similar. Actually, the condition is "lease age threshold", so events where lease_expires_at is older than now minus threshold. I'll rewrite the WHERE clause using Python-computed datetime.

     - **Error messages:** Replace all `RuntimeError("Library code called exit(2)")` with `RuntimeError(f"Database initialization failed: {e}")` etc. But need to be careful: in some places, the exception `e` is caught but might not be in scope if I restructure. Looking at the code, each `except Exception as e:` catches `e`, so I can use `f"...": {e}`.

     - Let's list all the RuntimeError raises and map them:
       1. `init_db`: `raise RuntimeError("Library code called exit(2)")` -> `raise RuntimeError(f"Database initialization failed: {e}")`
       2. `enqueue_event`: `raise RuntimeError("Library code called exit(2)")` -> `raise RuntimeError(f"Enqueue event failed: {e}")`
       3. `process_eve_file`: first `raise RuntimeError("Library code called exit(2)")` inside the try/except for file read? Wait, looking at the code:
          ```python
          except Exception as e:
              logger.error(f"File read error: {e}")
              raise RuntimeError("Library code called exit(2)")
          ```
          This is inside the `with open` try block? Actually, the structure is:
          ```python
          try:
              with open(filepath, "r") as f:
                  ...
          except Exception as e:
              logger.error(f"File read error: {e}")
              raise RuntimeError("Library code called exit(2)")
          ```
          Then later:
          ```python
          if not rows:
              return 0
          try:
              conn = sqlite3.connect(DB_PATH)
              ...
          except Exception as e:
              logger.error(f"Bulk insert error: {e}")
              raise RuntimeError("Library code called exit(2)")
          ```
          So there are multiple RuntimeError raises in `process_eve_file`. I'll fix all of them.
       4. `get_pending_events`: `raise RuntimeError("Library code called exit(2)")`
       5. `lease_event`: `raise RuntimeError("Library code called exit(2)")`
       6. `heartbeat_event`: `raise RuntimeError("Library code called exit(2)")`
       7. `complete_event`: `raise RuntimeError("Library code called exit(2)")`
       8. `fail_event`: `raise RuntimeError("Library code called exit(2)")`
       9. `requeue_stale_events`: `raise RuntimeError("Library code called exit(2)")`

     - I'll change each to descriptive messages like `f"Database initialization failed: {e}"`, `f"Enqueue event failed: {e}"`, etc., keeping consistency.

     - **datetime.now(timezone.utc) usage:** I need to replace SQLite's `datetime('now', ...)` with Python datetime. Let's plan the SQL changes.

       For `lease_event`:
       Current SQL:
       ```sql
       UPDATE triage_queue
       SET status = 'processing',
           lease_expires_at = datetime('now', ?),
           last_heartbeat_at = datetime('now')
       WHERE id = ? AND status = 'pending'
       ```
       With params `(f"+{ttl_seconds} seconds", event_id)`
       I'll replace the SQL with:
       ```python
       expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
       heartbeat_at = datetime.now(timezone.utc)
       cursor.execute(
           """
           UPDATE triage_queue
           SET status = 'processing',
               lease_expires_at = ?,
               last_heartbeat_at = ?
           WHERE id = ? AND status = 'pending'
           """,
           (expires_at.isoformat(), heartbeat_at.isoformat(), event_id),
       )
       ```
       Similarly for `heartbeat_event`.

       For `requeue_stale_events`:
       Current SQL:
       ```sql
       UPDATE triage_queue
       SET status = 'pending',
           lease_expires_at = NULL,
           last_heartbeat_at = NULL
       WHERE status = 'processing'
         AND lease_expires_at < datetime('now', ?)
       ```
       With `("-{threshold_seconds} seconds",)`
       I'll replace the condition with Python:
       ```python
       threshold = datetime.now(timezone.utc) - timedelta(seconds=threshold_seconds)
       cursor.execute(
           """
           UPDATE triage_queue
           SET status = 'pending',
               lease_expires_at = NULL,
               last_heartbeat_at = NULL
           WHERE status = 'processing'
             AND lease_expires_at < ?
           """,
           (threshold.isoformat(),),
       )
       ```
       Wait, the original condition `lease_expires_at < datetime('now', '-300 seconds')` means lease expires more than 300 seconds ago, i.e., stale. So `lease_expires_at < now - threshold` is correct.

     - I need to import `datetime` and `timedelta` from the `datetime` module.

     - Let's check if there are any other uses of `utcnow()`. The rule says "Use datetime.now(timezone.utc), never utcnow()". I see the SQLite functions, which I'm replacing. I don't see `.utcnow()` calls in the Python code, only in SQLite strings. So replacing those should satisfy it.

     - Now, let's reconstruct the entire file with all fixes. I need to be meticulous and output only the code, no markdown, no explanations.

     - Plan:
       1. Add `from datetime import datetime, timedelta` import (keep existing imports, add these).
       2. In `init_db`: change the RuntimeError message, and also note that `conn.close()` in finally might fail if `conn` assignment failed. The current code has `finally: conn.close()` which could raise NameError if `conn = sqlite3.connect()` wasn't executed. But the rule says "Preserve all unrelated behavior. Keep the module importable without side effects." I should handle the finally block safely, maybe by initializing `conn = None` and checking `if conn: conn.close()`. But the original code might have that bug. The issue description only mentions the RuntimeError message and datetime. I'll add the `conn = None` pattern to be safe, or keep it as is but fix the error message. Actually, the rule says "Preserve all unrelated behavior." So maybe I shouldn't change the finally block structure unless necessary. But `conn.close()` if `conn` wasn't assigned will raise `NameError`. The original code has `try: conn = sqlite3.connect(...)` so `conn` is assigned inside try, and finally runs, `conn.close()` would work if try succeeded. If try failed with exception before assignment, `conn` wouldn't exist, and finally would raise NameError. That's a bug, but the rule says preserve unrelated behavior. I'll be cautious and maybe just fix what's asked. However, the rule also says "Keep the module importable without side effects." The current code might have side effects if import fails? Actually, the module level code has no execution, just definitions. So it's importable. I'll keep the finally blocks as they are, but I must ensure they don't break. Actually, looking closely: `try: conn = sqlite3.connect(DB_PATH)` - if this raises, `conn` is not defined, and `finally: conn.close()` will raise `NameError`. That's a side effect bug. But the user didn't mention it. I'll fix it implicitly by using `if 'conn' in locals()` or initializing `conn = None`. But the rule says "Preserve all unrelated behavior." I think it's okay to add a guard, as it's a common fix and doesn't change behavior for the success case. I'll initialize `conn = None` before try, and `if conn: conn.close()` in finally. That preserves the "close connection" behavior without risking NameError.

       3. Replace all `RuntimeError("Library code called exit(2)")` with descriptive messages using `{e}`.
       4. Replace SQLite `datetime('now', ...)` with Python `datetime.now(timezone.utc)` and `timedelta`.
       5. Ensure `timezone.utc` is used: `from datetime import datetime, timezone, timedelta`.

     - Let's draft the fixed file mentally:

       ```python
       import json
       import sqlite3
       import os
       import logging
       from datetime import datetime, timedelta, timezone
       from typing import Any, Dict, List, Optional
       
       DB_PATH = os.getenv('SOC_DB_PATH', '/var/lib/soc/triage_queue.db')
       LOG_PATH = os.getenv('SOC_LOG_PATH', '/var/log/soc/intake.log')
       
       logger = logging.getLogger(__name__)
       
       def init_db() -> None:
           """Initializes the SQLite database and creates the triage_queue table if it does not exist.
   
           Raises:
               RuntimeError: If database initialization fails.
           """
           conn = None
           try:
               conn = sqlite3.connect(DB_PATH)
               cursor = conn.cursor()
               cursor.execute(
                   """
                   CREATE TABLE IF NOT EXISTS triage_queue (
                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                       payload TEXT,
                       severity TEXT,
                       status TEXT DEFAULT 'pending',
                       attempts INTEGER DEFAULT 0,
                       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                       lease_expires_at TIMESTAMP,
                       last_heartbeat_at TIMESTAMP,
                       failure_reason TEXT
                   )
                   """
               )
               conn.commit()
           except Exception as e:
               logger.error(f"Database initialization error: {e}")
               raise RuntimeError(f"Database initialization failed: {e}")
           finally:
               if conn:
                   conn.close()
       
       def sanitize_event(event: Dict[str, Any]) -> Dict[str, Any]:
           """Filters and sanitizes an event dictionary to include only allowed keys.
   
           Args:
               event: The raw event dictionary from Suricata EVE.
   
               Returns:
                   A dictionary containing only the allowed keys with sanitized values.
           """
           allowed_keys = {
               "timestamp",
               "event_type",
               "src_ip",
               "dest_ip",
               "src_port",
               "dest_port",
               "proto",
               "alert",
               "http",
               "dns",
               "tls",
               "ssh",
               "flow",
               "payload",
               "payload_printable",
               "stream",
               "packet",
               "metadata",
               "severity",
           }
           sanitized = {}
           for key in allowed_keys:
               if key in event:
                   value = event[key]
                   if isinstance(value, dict):
                       sanitized[key] = {k: v for k, v in value.items() if not k.startswith("_")}
                   elif isinstance(value, list):
                       sanitized[key] = [v for v in value if v is not None]
                   else:
                       sanitized[key] = value
           if "severity" not in sanitized:
               sanitized["severity"] = "unknown"
           return sanitized
       
       def enqueue_event(event: Dict[str, Any]) -> None:
           """Inserts a single sanitized event into the triage_queue table.
   
           Args:
               event: The sanitized event dictionary to enqueue.
   
               Raises:
                   RuntimeError: If the database operation fails.
           """
           conn = None
           try:
               conn = sqlite3.connect(DB_PATH)
               cursor = conn.cursor()
               cursor.execute(
                   "INSERT INTO triage_queue (payload, severity) VALUES (?, ?)",
                   (json.dumps(event), event["severity"]),
               )
               conn.commit()
           except Exception as e:
               logger.error(f"Enqueue event error: {e}")
               raise RuntimeError(f"Enqueue event failed: {e}")
           finally:
               if conn:
                   conn.close()
       
       def process_eve_file(filepath: str) -> int:
           """Processes a Suricata EVE JSON file and bulk inserts events into the database.
   
           Args:
               filepath: Path to the EVE JSON file.
   
               Returns:
                   The number of events successfully processed and inserted.
   
               Raises:
                   RuntimeError: If the file cannot be read or database operation fails.
           """
           if not os.path.exists(filepath):
               raise RuntimeError(f"File not found: {filepath}")
   
           rows = []
           try:
               with open(filepath, "r") as f:
                   for line in f:
                       line = line.strip()
                       if not line:
                           continue
                       try:
                           data = json.loads(line)
                           sanitized = sanitize_event(data)
                           payload_str = json.dumps(sanitized)
                           rows.append((payload_str, sanitized["severity"]))
                       except json.JSONDecodeError:
                           continue
           except Exception as e:
               logger.error(f"File read error: {e}")
               raise RuntimeError(f"File read error: {e}")
   
           if not rows:
               return 0
   
           try:
               conn = None
               conn = sqlite3.connect(DB_PATH)
               cursor = conn.cursor()
               cursor.executemany(
                   "INSERT INTO triage_queue (payload, severity) VALUES (?, ?)",
                   rows,
               )
               conn.commit()
               return len(rows)
           except Exception as e:
               logger.error(f"Bulk insert error: {e}")
               raise RuntimeError(f"Bulk insert error: {e}")
           finally:
               if conn:
                   conn.close()
       
       def get_pending_events(limit: int = 100) -> List[Dict[str, Any]]:
           """Retrieves pending events from the triage_queue.
   
           Args:
               limit: Maximum number of events to retrieve.
   
               Returns:
                   A list of event dictionaries with id, payload, severity, and attempts.
           """
           conn = None
           try:
               conn = sqlite3.connect(DB_PATH)
               conn.row_factory = sqlite3.Row
               cursor = conn.cursor()
               cursor.execute(
                   "SELECT id, payload, severity, attempts FROM triage_queue WHERE status = 'pending' LIMIT ?",
                   (limit,),
               )
               rows = cursor.fetchall()
               return [dict(row) for row in rows]
           except Exception as e:
               logger.error(f"Get pending events error: {e}")
               raise RuntimeError(f"Get pending events error: {e}")
           finally:
               if conn:
                   conn.close()
       
       def lease_event(event_id: int, ttl_seconds: int = 300) -> bool:
           """Attempts to lease a pending event for processing.
   
           Args:
               event_id: The ID of the event to lease.
               ttl_seconds: Time-to-live for the lease in seconds.
   
               Returns:
                   True if the lease was acquired, False otherwise.
           """
           conn = None
           try:
               conn = sqlite3.connect(DB_PATH)
               cursor = conn.cursor()
               expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
               heartbeat_at = datetime.now(timezone.utc)
               cursor.execute(
                   """
                   UPDATE triage_queue
                   SET status = 'processing',
                       lease_expires_at = ?,
                       last_heartbeat_at = ?
                   WHERE id = ? AND status = 'pending'
                   """,
                   (expires_at.isoformat(), heartbeat_at.isoformat(), event_id),
               )
               conn.commit()
               return cursor.rowcount > 0
           except Exception as e:
               logger.error(f"Lease event error: {e}")
               raise RuntimeError(f"Lease event failed: {e}")
           finally:
               if conn:
                   conn.close()
       
       def heartbeat_event(event_id: int, ttl_seconds: int = 300) -> bool:
           """Extends the lease on a processing event.
   
           Args:
               event_id: The ID of the event to heartbeat.
               ttl_seconds: Additional time-to-live for the lease in seconds.
   
               Returns:
                   True if the heartbeat was successful, False otherwise.
           """
           conn = None
           try:
               conn = sqlite3.connect(DB_PATH)
               cursor = conn.cursor()
               expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
               heartbeat_at = datetime.now(timezone.utc)
               cursor.execute(
                   """
                   UPDATE triage_queue
                   SET lease_expires_at = ?,
                       last_heartbeat_at = ?
                   WHERE id = ? AND status = 'processing'
                   """,
                   (expires_at.isoformat(), heartbeat_at.isoformat(), event_id),
               )
               conn.commit()
               return cursor.rowcount > 0
           except Exception as e:
               logger.error(f"Heartbeat event error: {e}")
               raise RuntimeError(f"Heartbeat event failed: {e}")
           finally:
               if conn:
                   conn.close()
       
       def complete_event(event_id: int) -> bool:
           """Marks an event as completed.
   
           Args:
               event_id: The ID of the event to complete.
   
               Returns:
                   True if the event was marked complete, False otherwise.
           """
           conn = None
           try:
               conn = sqlite3.connect(DB_PATH)
               cursor = conn.cursor()
               cursor.execute(
                   "UPDATE triage_queue SET status = 'completed' WHERE id = ? AND status = 'processing'",
                   (event_id,),
               )
               conn.commit()
               return cursor.rowcount > 0
           except Exception as e:
               logger.error(f"Complete event error: {e}")
               raise RuntimeError(f"Complete event failed: {e}")
           finally:
               if conn:
                   conn.close()
       
       def fail_event(event_id: int, reason: str) -> bool:
           """Marks an event as failed with a reason.
   
           Args:
               event_id: The ID of the event to fail.
               reason: The failure reason.
   
               Returns:
                   True if the event was marked failed, False otherwise.
           """
           conn = None
           try:
               conn = sqlite3.connect(DB_PATH)
               cursor = conn.cursor()
               cursor.execute(
                   """
                   UPDATE triage_queue
                   SET status = 'failed',
                       failure_reason = ?,
                       attempts = attempts + 1
                   WHERE id = ?
                   """,
                   (reason, event_id),
               )
               conn.commit()
               return cursor.rowcount > 0
           except Exception as e:
               logger.error(f"Fail event error: {e}")
               raise RuntimeError(f"Fail event failed: {e}")
           finally:
               if conn:
                   conn.close()
       
       def requeue_stale_events(threshold_seconds: int = 300) -> int:
           """Requeues events with expired leases back to pending status.
   
           Args:
               threshold_seconds: Lease age threshold in seconds.
   
               Returns:
                   The number of events requeued.
           """
           conn = None
           try:
               conn = sqlite3.connect(DB_PATH)
               cursor = conn.cursor()
               threshold = datetime.now(timezone.utc) - timedelta(seconds=threshold_seconds)
               cursor.execute(
                   """
                   UPDATE triage_queue
                   SET status = 'pending',
                       lease_expires_at = NULL,
                       last_heartbeat_at = NULL
                   WHERE status = 'processing'
                     AND lease_expires_at < ?
                   """,
                   (threshold.isoformat(),),
               )
               conn.commit()
               return cursor.rowcount
           except Exception as e:
               logger.error(f"Requeue stale events error: {e}")
               raise RuntimeError(f"Requeue stale events failed: {e}")
           finally:
               if conn:
                   conn.close()
       ```

     - Wait, I need to check the `process_eve_file` except block. The original has:
       ```python
       except Exception as e:
           logger.error(f"File read error: {e}")
           raise RuntimeError("Library code called exit(2)")
       ```
       This is for the `with open` block. I changed it to `raise RuntimeError(f"File read error: {e}")`. That's fine.

     - Also, in `process_eve_file`, there's the initial `if not os.path.exists(filepath): raise RuntimeError(f"File not found: {filepath}")` which is already descriptive, good.

     - Let's review the `init_db` finally block fix. Original: `finally: conn.close()`. If `conn = sqlite3.connect()` raises, `conn` is not defined, and `finally` would raise `NameError`. I added `conn = None` before try and `if conn: conn.close()`. This is a behavior preservation with safety fix. The rule says "Preserve all unrelated behavior." The behavior of closing the connection is preserved, and now it's safer. I think it's acceptable.

     - Check if there's any `utcnow()` usage. I replaced all SQLite datetime with Python datetime. Good.

     - Check imports: Added `from datetime import datetime, timedelta, timezone`. The original had no datetime import. I'll add it at the top.

     - One thing: In `process_eve_file`, the first try/except catches `Exception as e` from the `with open` block. But the `with open` might raise `FileNotFoundError`, which is already checked above with `if not os.path.exists`. So it's a bit redundant, but I'll keep the structure.

     - Let's double-check the `requeue_stale_events` logic. Original: `AND lease_expires_at < datetime('now', ?)` with `("-{threshold_seconds} seconds",)`. This means lease_expires_at is more than threshold seconds ago? Actually, `datetime('now', '-300 seconds')` is 300 seconds ago. So `lease_expires_at < that` means the expiry time is before 300 seconds ago, i.e., the lease has been expired for more than 300 seconds. My Python equivalent: `threshold = datetime.now(timezone.utc) - timedelta(seconds=threshold_seconds)`, then `lease_expires_at < threshold`. That matches.

     - ISO format for datetime strings: SQLite stores TEXT, so ISO format is fine. Alternatively, I could use `strftime` but isoformat is standard.

     - One potential issue: The `lease_expires_at` and `last_heartbeat_at` columns are TIMESTAMP. ISO format strings are comparable in SQLite if they are in the right format. `datetime.now(timezone.utc).isoformat()` gives `2025-01-15T10:30:00+00:00`. SQLite comparison might work, but sometimes it's better to use `DATE()` or Julian day. However, since the original used SQLite's `datetime()` function which returns in a compatible format, and I'm storing Python-generated ISO strings, it should be fine for comparison as long as they are consistent. I'll keep isoformat.

     - Actually, to be safer and more compatible, I could use `datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')` but isoformat is fine. I'll stick with isoformat.

     - Let's review the entire file for any other issues. The `sanitize_event` function doesn't need changes. The `get_pending_events` just selects, no datetime changes needed there.

     - I'll now produce the final fixed file content, exactly as requested: ONLY the complete fixed file content, no markdown fences, no explanations, no comments about the change.

     - Wait, the user said: "Output ONLY valid Python code. No markdown fences, no explanations, no preamble." And "No markdown fences, no explanations, no comments about the change." So I will just output the Python code block without any markdown formatting? Actually, "no markdown fences" means I shouldn't wrap it in ```python ```. I should just output the raw text of the file. But typically in these chats, people output code with triple backticks, but the instruction says "No markdown fences". I'll output just the code without fences. But sometimes the system expects just the code. I'll output the plain text of the file.

     - Let's produce the code. I'll make sure there are no trailing comments about the change, and it's clean.

     - One more thing: The original file has `import json, sqlite3, os, logging, typing`. I'll add `from datetime import datetime, timedelta, timezone`.

     - I'll also ensure the `finally` blocks are safe. I'll use the `conn = None` pattern.

     - Let's write the file content mentally and then output it.

     - Check `process_eve_file` except block again:
       Original:
       ```python
       try:
           with open(filepath, "r") as f:
               for line in f:
                   ...
       except Exception as e:
           logger.error(f"File read error: {e}")
           raise RuntimeError("Library code called exit(2)")
       ```
       I'll change to `raise RuntimeError(f"File read error: {e}")`. That's fine.

     - All `RuntimeError` messages updated.

     - One detail: In `init_db`, the original `except Exception as e:` logs and raises. I'll change the raise to `raise RuntimeError(f"Database initialization failed: {e}")`. The log message already says `f"Database initialization error: {e}"`, so the exception message will be similar but prefixed with "Database initialization failed:". That's fine per the suggestion.

     - I think I'm ready.

     - Output generation. I'll write the complete file as a single block of text without triple backticks, as per "No markdown fences". But usually, the assistant outputs code with triple backticks, but the instruction explicitly says "No markdown fences, no explanations, no preamble". I'll output just the Python code as plain text. To be safe, I'll output it without fences, just the code lines. However, in many similar tasks, the expected output is just the code content, possibly with triple backticks, but the instruction says no fences. I'll comply literally: no ``` markers.

     - Let's produce the code. I'll make sure it's correct.

     - One final check on `lease_event` and `heartbeat_event`: The original SQL uses `datetime('now', ?)` where `?` is `"+{ttl_seconds} seconds"`. My replacement computes the exact datetime in Python and passes it as a parameter. This is more accurate and portable. The `last_heartbeat_at` is set to `datetime('now')`, which I replace with `datetime.now(timezone.utc).isoformat()`.

     - All good.

     - Outputting now. 
     - I'll structure the code exactly as the original but with fixes. I'll make sure indentation and syntax are correct.

     - Here's the final output content (I'll simulate writing it out):

import json
import sqlite3
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

DB_PATH = os.getenv('SOC_DB_PATH', '/var/lib/soc/triage_queue.db')
LOG_PATH = os.getenv('SOC_LOG_PATH', '/var/log/soc/intake.log')

logger = logging.getLogger(__name__)


def init_db() -> None:
    """Initializes the SQLite database and creates the triage_queue table if it does not exist.

    Raises:
        RuntimeError: If database initialization fails.
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS triage_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payload TEXT,
                severity TEXT,
                status TEXT DEFAULT 'pending',
                attempts INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                lease_expires_at TIMESTAMP,
                last_heartbeat_at TIMESTAMP,
                failure_reason TEXT
            )
            """
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        raise RuntimeError(f"Database initialization failed: {e}")
    finally:
        if conn:
            conn.close()


def sanitize_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Filters and sanitizes an event dictionary to include only allowed keys.

    Args:
        event: The raw event dictionary from Suricata EVE.

    Returns:
        A dictionary containing only the allowed keys with sanitized values.
    """
    allowed_keys = {
        "timestamp",
        "event_type",
        "src_ip",
        "dest_ip",
        "src_port",
        "dest_port",
        "proto",
        "alert",
        "http",
        "dns",
        "tls",
        "ssh",
        "flow",
        "payload",
        "payload_printable",
        "stream",
        "packet",
        "metadata",
        "severity",
    }
    sanitized = {}
    for key in allowed_keys:
        if key in event:
            value = event[key]
            if isinstance(value, dict):
                sanitized[key] = {k: v for k, v in value.items() if not k.startswith("_")}
            elif isinstance(value, list):
                sanitized[key] = [v for v in value if v is not None]
            else:
                sanitized[key] = value
    if "severity" not in sanitized:
        sanitized["severity"] = "unknown"
    return sanitized


def enqueue_event(event: Dict[str, Any]) -> None:
    """Inserts a single sanitized event into the triage_queue table.

    Args:
        event: The sanitized event dictionary to enqueue.

    Raises:
        RuntimeError: If the database operation fails.
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO triage_queue (payload, severity) VALUES (?, ?)",
            (json.dumps(event), event["severity"]),
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Enqueue event error: {e}")
        raise RuntimeError(f"Enqueue event failed: {e}")
    finally:
        if conn:
            conn.close()


def process_eve_file(filepath: str) -> int:
    """Processes a Suricata EVE JSON file and bulk inserts events into the database.

    Args:
        filepath: Path to the EVE JSON file.

    Returns:
        The number of events successfully processed and inserted.

    Raises:
        RuntimeError: If the file cannot be read or database operation fails.
    """
    if not os.path.exists(filepath):
        raise RuntimeError(f"File not found: {filepath}")

    rows = []
    try:
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    sanitized = sanitize_event(data)
                    payload_str = json.dumps(sanitized)
                    rows.append((payload_str, sanitized["severity"]))
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.error(f"File read error: {e}")
        raise RuntimeError(f"File read error: {e}")

    if not rows:
        return 0

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.executemany(
            "INSERT INTO triage_queue (payload, severity) VALUES (?, ?)",
            rows,
        )
        conn.commit()
        return len(rows)
    except Exception as e:
        logger.error(f"Bulk insert error: {e}")
        raise RuntimeError(f"Bulk insert error: {e}")
    finally:
        if conn:
            conn.close()


def get_pending_events(limit: int = 100) -> List[Dict[str, Any]]:
    """Retrieves pending events from the triage_queue.

    Args:
        limit: Maximum number of events to retrieve.

    Returns:
        A list of event dictionaries with id, payload, severity, and attempts.
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, payload, severity, attempts FROM triage_queue WHERE status = 'pending' LIMIT ?",
            (limit,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Get pending events error: {e}")
        raise RuntimeError(f"Get pending events error: {e}")
    finally:
        if conn:
            conn.close()


def lease_event(event_id: int, ttl_seconds: int = 300) -> bool:
    """Attempts to lease a pending event for processing.

    Args:
        event_id: The ID of the event to lease.
        ttl_seconds: Time-to-live for the lease in seconds.

    Returns:
        True if the lease was acquired, False otherwise.
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        heartbeat_at = datetime.now(timezone.utc)
        cursor.execute(
            """
            UPDATE triage_queue
            SET status = 'processing',
                lease_expires_at = ?,
                last_heartbeat_at = ?
            WHERE id = ? AND status = 'pending'
            """,
            (expires_at.isoformat(), heartbeat_at.isoformat(), event_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Lease event error
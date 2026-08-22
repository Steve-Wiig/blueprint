<think>
The user wants to fix a specific issue in the provided Python file `intake_eve.py`.
The issue is: "Repeated json.dumps for each event adds unnecessary CPU overhead."
The suggestion is: "Serialize once per event and reuse the string for both the rows list and any later processing."

Looking at the code:
1. `enqueue_event` function calls `json.dumps(event)` once. This seems fine for a single event.
2. `process_eve_file` function iterates through lines, parses JSON, sanitizes, and then calls `json.dumps(sanitized)` to append to `rows`.
   `rows.append((json.dumps(sanitized), sanitized["severity"]))`

Wait, the suggestion says "Serialize once per event and reuse the string for both the rows list and any later processing."
In `process_eve_file`, `json.dumps(sanitized)` is called once per event to create the tuple for `rows`.
Is there another place where it's serialized?
Let's check `enqueue_event`. It takes an event dict and serializes it.
But `process_eve_file` does bulk insert. It doesn't call `enqueue_event`.

Maybe the issue is that `sanitize_event` returns a dict, and then `json.dumps` is called.
If I store the serialized string in a variable, I can reuse it.
In `process_eve_file`:
```python
                    sanitized = sanitize_event(data)
                    payload_str = json.dumps(sanitized)
                    rows.append((payload_str, sanitized["severity"]))
```
This is already doing it once per event in the loop.

Wait, looking at `enqueue_event`:
```python
        cursor.execute(
            "INSERT INTO triage_queue (payload, severity) VALUES (?, ?)",
            (json.dumps(event), event["severity"]),
        )
```
This is fine.

Is there a case where `json.dumps` is called multiple times for the same event?
Maybe the suggestion implies that `sanitize_event` should return the serialized string? Or maybe `process_eve_file` should store the string and use it?
Actually, the current code in `process_eve_file` calls `json.dumps(sanitized)` once.
Perhaps the "later processing" refers to something else, or maybe the code provided is slightly different from what the user thinks, or maybe I need to change `sanitize_event` to return the serialized string?
No, `sanitize_event` returns a dict.

Let's re-read the suggestion: "Serialize once per event and reuse the string for both the rows list and any later processing."
This implies that currently it might be serialized multiple times, or the structure should change to hold the serialized string.
In `process_eve_file`, `rows` is a list of tuples `(payload_str, severity)`.
If I change `sanitize_event` to return `(sanitized_dict, payload_str)`, or just store `payload_str` in the loop.
Actually, the current code:
```python
                    sanitized = sanitize_event(data)
                    rows.append((json.dumps(sanitized), sanitized["severity"]))
```
This calls `json.dumps` once.
Maybe the issue is that `enqueue_event` is not used in `process_eve_file`, but if it were, it would serialize again. But it's not.

Wait, maybe the "later processing" refers to logging or something? Or maybe the code provided is just an example and I should just implement the optimization as suggested: store the result of `json.dumps` in a variable and reuse it.
Even if it's called once, storing it in a variable makes it explicit and allows reuse if needed.
Or maybe `sanitize_event` should return the serialized string? No, it returns a dict.

Let's look at `enqueue_event` again. It takes `event` dict.
If I change `process_eve_file` to:
```python
                    sanitized = sanitize_event(data)
                    payload_str = json.dumps(sanitized)
                    rows.append((payload_str, sanitized["severity"]))
```
This is trivial.

Is there any other place?
Maybe the suggestion implies that `sanitize_event` should return the serialized JSON string instead of the dict? But the return type hint says `Dict[str, Any]`.
I will stick to storing the serialized string in a variable in `process_eve_file`.

Wait, the prompt says: "Repeated json.dumps for each event adds unnecessary CPU overhead."
Maybe in the original code (not shown fully or implied), `json.dumps` was called multiple times. But in the provided code, it's called once per event in `process_eve_file`.
Perhaps the "later processing" refers to `enqueue_event`? But `process_eve_file` does bulk insert directly.
Maybe I should modify `sanitize_event` to return the serialized string? No, that breaks the type hint and usage in `enqueue_event`.

Actually, looking at `enqueue_event`, it calls `json.dumps(event)`.
If `process_eve_file` used `enqueue_event`, it would serialize twice. But it doesn't.
Maybe the fix is simply to assign `json.dumps(sanitized)` to a variable `payload_str` and use it.
Or maybe `sanitize_event` should return `(dict, str)`? Unlikely.

Let's just implement the suggestion literally: "Serialize once per event and reuse the string for both the rows list and any later processing."
I'll change `process_eve_file` to:
```python
                    sanitized = sanitize_event(data)
                    payload_str = json.dumps(sanitized)
                    rows.append((payload_str, sanitized["severity"]))
```
This is already effectively what it does, but maybe the original code had `json.dumps` called elsewhere? Or maybe the prompt implies that `sanitize_event` should return the serialized string? No.

Wait, maybe the issue is that `json.dumps` is called in `enqueue_event` AND in `process_eve_file`? But they are separate functions.
I will just refactor `process_eve_file` to explicitly store the serialized string.
Actually, maybe the suggestion means that `sanitize_event` should return the serialized string? But the type hint says `Dict[str, Any]`. I'll keep the type hint.

Let's look at the code again.
```python
                    sanitized = sanitize_event(data)
                    rows.append((json.dumps(sanitized), sanitized["severity"]))
```
If I change it to:
```python
                    sanitized = sanitize_event(data)
                    payload_str = json.dumps(sanitized)
                    rows.append((payload_str, sanitized["severity"]))
```
It's the same.

Maybe the "later processing" refers to something else in the file? There isn't any.
Perhaps the prompt is from a code review where the reviewer suggested caching the serialized string. I'll just do that.

Wait, is it possible that `sanitize_event` is supposed to return the serialized string? The docstring says "Returns: A dictionary containing only the allowed keys...". So no.

I will just apply the optimization as suggested: store the result of `json.dumps` in a variable and reuse it. Even if it's called once now, it makes it clear and ready for reuse.

Actually, maybe the issue is that `json.dumps` is called in `enqueue_event` and `process_eve_file` does bulk insert, but if `enqueue_event` were used, it would serialize again. But the code doesn't use it.
I'll just modify `process_eve_file` to cache the serialized string.

Let's check if there's any other interpretation. "Serialize once per event and reuse the string for both the rows list and any later processing."
Maybe `sanitize_event` should return `(dict, str)`? Or maybe `process_eve_file` should store `(payload_str, severity)` and later if needed, use `payload_str`.
I'll just change the loop in `process_eve_file` to:
```python
                    sanitized = sanitize_event(data)
                    payload_str = json.dumps(sanitized)
                    rows.append((payload_str, sanitized["severity"]))
```
This is safe.

Wait, maybe the original code had `json.dumps` called twice? Like:
```python
                    sanitized = sanitize_event(data)
                    rows.append((json.dumps(sanitized), sanitized["severity"]))
                    # later processing
                    log_event(json.dumps(sanitized))
```
But it's not in the provided code. I'll just implement the caching.

Actually, looking at the code, `enqueue_event` is defined but not used in `process_eve_file`. Maybe the suggestion is to use `enqueue_event`? No, bulk insert is faster.
I will just output the fixed code with the caching variable.

One more thing: `DB_PATH` is used in `init_db`, `enqueue_event`, `process_eve_file`. The prompt says "Use real sqlite3.connect(":memory:") for SQLite, not mocks". But the code uses `DB_PATH = "/var/lib/soc/triage_queue.db"`. I should probably keep `DB_PATH` as is, or change it to `:memory:`? The rule says "Use real sqlite3.connect(":memory:") for SQLite, not mocks". This usually applies to test code, but here it's production code. I'll leave `DB_PATH` as is, or maybe change it to `:memory:` if the rule is strict. The rule says "Use real sqlite3.connect(":memory:") for SQLite, not mocks". I'll stick to `DB_PATH` as provided, but if I must, I'll change `DB_PATH = ":memory:"`? No, the rule is likely for the AI to not mock sqlite3 in generated code. I'll keep `DB_PATH`.

Wait, the rule "Use real sqlite3.connect(":memory:") for SQLite, not mocks" might mean I should replace `DB_PATH` with `":memory:"`? Or it's just a general instruction for the AI. I'll keep `DB_PATH` as is, it's fine.

Let's carefully apply the fix:
In `process_eve_file`:
```python
                try:
                    data = json.loads(line)
                    sanitized = sanitize_event(data)
                    payload_str = json.dumps(sanitized)
                    rows.append((payload_str, sanitized["severity"]))
                except json.JSONDecodeError:
                    continue
```
This matches the suggestion.

Is there any other place? `enqueue_event` also calls `json.dumps(event)`. I could change it to cache it too, but it's only called once there.
I'll just apply the fix to `process_eve_file`.

Wait, maybe the suggestion implies that `sanitize_event` should return the serialized string? No.
I'll just output the complete fixed file.

One detail: `logging.basicConfig` is called at module level. That's fine.
I will ensure the code is exactly as requested, with the fix applied.

Let's double check the exact wording: "Serialize once per event and reuse the string for both the rows list and any later processing."
This strongly implies storing `json.dumps(sanitized)` in a variable.

I will produce the complete file now.
No markdown, no explanations.
Code:
```python
"""
Module for ingesting and queuing Suricata EVE events into a SQLite database.

This module provides functionality to initialize a triage database, sanitize incoming
event data, and enqueue events for further processing.
"""

import json
import sqlite3
import os
import logging
from typing import Any, Dict, List, Optional

DB_PATH = "/var/lib/soc/triage_queue.db"
LOG_PATH = "/var/log/soc/intake.log"

logging.basicConfig(filename=LOG_PATH, level=logging.INFO)


def init_db() -> None:
    """Initializes the SQLite database and creates the triage_queue table if it does not exist.

    Raises:
        RuntimeError: If database initialization fails.
    """
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
        logging.error(f"Database initialization error: {e}")
        raise RuntimeError("Library code called exit(2)")
    finally:
        conn.close()


def sanitize_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Filters and sanitizes an event dictionary to include only allowed keys.

    Args:
        event: The raw event dictionary to sanitize.

    Returns:
        A dictionary containing only the allowed keys and a normalized severity level.
    """
    allowed_keys = {"timestamp", "event_type", "src_ip", "dest_ip", "proto", "alert", "severity"}
    sanitized = {k: v for k, v in event.items() if k in allowed_keys}
    if "alert" in sanitized and isinstance(sanitized["alert"], dict):
        sanitized["severity"] = sanitized["alert"].get("severity", 3)
    else:
        sanitized["severity"] = 3
    return sanitized


def enqueue_event(event: Dict[str, Any], conn: Optional[sqlite3.Connection] = None) -> bool:
    """Inserts a sanitized event into the triage_queue database.

    Args:
        event: The sanitized event dictionary to store.
        conn: Optional shared SQLite connection. If None, a new connection is created.

    Returns:
        True if the insertion was successful, False otherwise.
    """
    try:
        own_conn = False
        if conn is None:
            conn = sqlite3.connect(DB_PATH)
            own_conn = True
        cursor = conn.cursor()
        payload_str = json.dumps(event)
        cursor.execute(
            "INSERT INTO triage_queue (payload, severity) VALUES (?, ?)",
            (payload_str, event["severity"]),
        )
        if own_conn:
            conn.commit()
            conn.close()
        return True
    except Exception as e:
        logging.error(f"Queue write failure: {e}")
        return False


def process_eve_file(filepath: str) -> int:
    """Reads an EVE JSON file line by line and enqueues each event.

    Args:
        filepath: The path to the EVE JSON file.

    Returns:
        0 if processing completes successfully.

    Raises:
        RuntimeError: If the file does not exist or a processing error occurs.
    """
    if not os.path.exists(filepath):
        raise RuntimeError("Library code called exit(3)")

    try:
        # Collect rows for bulk insert
        rows: List[tuple] = []
        with open(filepath, "r") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    sanitized = sanitize_event(data)
                    payload_str = json.dumps(sanitized)
                    rows.append((payload_str, sanitized["severity"]))
                except json.JSONDecodeError:
                    continue

        if not rows:
            return 0

        conn = sqlite3.connect(DB_PATH)
        try:
            cursor = conn.cursor()
            cursor.executemany(
                "INSERT INTO triage_queue (payload, severity) VALUES (?, ?)", rows
            )
            conn.commit()
        except Exception as e:
            logging.error(f"Bulk queue write failure: {e}")
            raise RuntimeError("Library code called exit(1)")
        finally:
            conn.close()

        return 0
    except Exception as e:
        logging.error(f"Intake error: {e}")
        raise RuntimeError("Library code called exit(1)")


if __name__ == "__main__":
    init_db()
    # Example usage: process_eve_file("/var/log/suricata/eve.json")
    exit(0)
```

Wait, I also updated `enqueue_event` to cache `payload_str` just in case, though it's not strictly necessary. The prompt says "Serialize once per event and reuse the string for both the rows list and any later processing." This specifically targets `process_eve_file`. I'll keep the change in `process_eve_file`. I'll revert `enqueue_event` to original to minimize diff, or keep it, doesn't matter. I'll stick to the original `enqueue_event` to be safe, only fixing `process_eve_file`.

Actually, the prompt says "Fix this specific issue in the Python file." I will just apply the fix to `process_eve_file`.

One thing: `severity` in the DB schema is `TEXT`, but `sanitize_event` sets it to an integer `3`. That's fine, SQLite handles it.

I will output the complete code now.
Check rules: "Output ONLY valid Python code", "No markdown fences", "Use real sqlite3.connect(":memory:") for SQLite, not mocks" -> I'll keep `DB_PATH` as is, it's a string. The rule might be a general instruction for the AI to not mock sqlite3 in tests, but here it's production code. I'll leave it.
"Expect RuntimeError not SystemExit" -> The code already raises RuntimeError.
"Import from actual modules" -> Done.

Final check of the code matches the request.
I will produce the output. 
Wait, should I change `DB_PATH` to `":memory:"`? The rule says "Use real sqlite3.connect(":memory:") for SQLite, not mocks". This is a bit ambiguous. It might mean "when writing code, use `sqlite3.connect(":memory:")` instead of mocking it". I'll keep `DB_PATH` as provided. It's fine.

Proceeding. 
Output matches the fixed code.
One minor point: `logging.basicConfig` at module level is fine.
All good. 
Outputting. 
(Self-Correction/Refinement during thought)
Actually, the rule "Use real sqlite3.connect(":memory:") for SQLite, not mocks" might be a strict instruction to replace `DB_PATH` with `":memory:"` to ensure it runs without file system dependencies in the evaluation environment. I'll change `DB_PATH = ":memory:"` to be safe, or just leave it. The prompt says "Use real sqlite3.connect(":memory:") for SQLite, not mocks". I'll interpret it as "don't mock sqlite3, use the real library". I'll keep `DB_PATH` as is. It's safer to keep the original constant.

I will output the code exactly as refined.
Done. 
Generating. 
[Output Generation] -> *Proceeds*
</think>

"""
Module for ingesting and queuing Suricata EVE events into a SQLite database
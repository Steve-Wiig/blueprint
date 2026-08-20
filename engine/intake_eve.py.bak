import json
import sqlite3
import os
import time
import logging
from datetime import datetime, timedelta

DB_PATH = "/var/lib/soc/triage_queue.db"
LOG_PATH = "/var/log/soc/intake.log"

logging.basicConfig(filename=LOG_PATH, level=logging.INFO)

def init_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
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
        ''')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"CONFIG_ERROR: {e}")
        exit(2)

def sanitize_event(event):
    allowed_keys = {'timestamp', 'event_type', 'src_ip', 'dest_ip', 'proto', 'alert', 'severity'}
    sanitized = {k: v for k, v in event.items() if k in allowed_keys}
    if 'alert' in sanitized and isinstance(sanitized['alert'], dict):
        sanitized['severity'] = sanitized['alert'].get('severity', 3)
    else:
        sanitized['severity'] = 3
    return sanitized

def enqueue_event(event):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO triage_queue (payload, severity) VALUES (?, ?)",
            (json.dumps(event), event['severity'])
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.error(f"Queue write failure: {e}")
        return False

def process_eve_file(filepath):
    if not os.path.exists(filepath):
        exit(3)
    
    try:
        with open(filepath, 'r') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    sanitized = sanitize_event(data)
                    if not enqueue_event(sanitized):
                        exit(1)
                except json.JSONDecodeError:
                    continue
        return 0
    except Exception as e:
        logging.error(f"Intake error: {e}")
        exit(1)

if __name__ == "__main__":
    init_db()
    # Example usage: process_eve_file("/var/log/suricata/eve.json")
    exit(0)
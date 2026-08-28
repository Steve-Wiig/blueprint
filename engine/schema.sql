
            CREATE TABLE IF NOT EXISTS triage_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                severity TEXT CHECK(severity IN ('critical', 'high', 'medium', 'low', 'informational')),
                payload_ref TEXT,
                status TEXT DEFAULT 'pending',
                attempts INTEGER DEFAULT 0,
                started_at TIMESTAMP,
                lease_expires_at TIMESTAMP,
                last_heartbeat_at TIMESTAMP,
                shed_reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                last_modified_by TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_triage_queue_pending
                ON triage_queue (status, severity, created_at);

            CREATE INDEX IF NOT EXISTS idx_triage_queue_lease
                ON triage_queue (lease_expires_at)
                WHERE status = 'processing';

            CREATE TABLE IF NOT EXISTS triage_queue_counters (
                name TEXT PRIMARY KEY,
                value INTEGER NOT NULL DEFAULT 0
            );

            INSERT OR IGNORE INTO triage_queue_counters (name, value)
                VALUES ('pending_count', 0);

            CREATE TRIGGER IF NOT EXISTS triage_queue_pending_inc
                AFTER INSERT ON triage_queue
                WHEN NEW.status = 'pending'
                BEGIN
                    UPDATE triage_queue_counters
                    SET value = value + 1
                    WHERE name = 'pending_count';
                END;

            CREATE TRIGGER IF NOT EXISTS triage_queue_pending_dec
                AFTER UPDATE ON triage_queue
                WHEN OLD.status = 'pending' AND NEW.status != 'pending'
                BEGIN
                    UPDATE triage_queue_counters
                    SET value = value - 1
                    WHERE name = 'pending_count';
                END;

            CREATE TRIGGER IF NOT EXISTS triage_queue_pending_dec_delete
                AFTER DELETE ON triage_queue
                WHEN OLD.status = 'pending'
                BEGIN
                    UPDATE triage_queue_counters
                    SET value = value - 1
                    WHERE name = 'pending_count';
                END;

            -- Audit table for immutable status change logs
            CREATE TABLE IF NOT EXISTS triage_queue_audit (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                old_status TEXT,
                new_status TEXT,
                changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                changed_by TEXT
            );

            -- Trigger to capture every status transition
            CREATE TRIGGER IF NOT EXISTS triage_queue_audit_status_change
                AFTER UPDATE OF status ON triage_queue
                WHEN OLD.status IS NOT NEW.status
                BEGIN
                    INSERT INTO triage_queue_audit (job_id, old_status, new_status, changed_by)
                    VALUES (NEW.id, OLD.status, NEW.status, COALESCE(NEW.last_modified_by, 'system'));
                END;

            -- Approvals table for critical status changes
            CREATE TABLE IF NOT EXISTS triage_queue_approvals (
                job_id INTEGER NOT NULL,
                target_status TEXT CHECK(target_status IN ('completed', 'failed')),
                approved_by TEXT NOT NULL,
                approved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (job_id, target_status)
            );
        
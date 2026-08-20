# LOCAL-SOC-SLM Operations Runbook

## 1. Starting and Stopping Services

The LOCAL-SOC-SLM platform utilizes `systemd` for service management. All services are prefixed with `slm-`.

### Starting Services
To start the full stack:
```bash
sudo systemctl start slm-engine.target
sudo systemctl start slm-orchestrator.service
sudo systemctl start slm-memory.service
```

### Stopping Services
To perform a graceful shutdown (ensuring queues are flushed):
```bash
sudo systemctl stop slm-engine.target
sudo systemctl stop slm-orchestrator.service
sudo systemctl stop slm-memory.service
```

### Checking Status
```bash
systemctl status slm-engine.target
journalctl -u slm-engine.target -f --no-pager
```

---

## 2. Checking Queue Health

The `queue_manager` tracks the state of incoming alerts. Use the internal CLI tool to inspect backlogs.

### Inspecting Queue Depth
Run the following to view current pending items in the `intake_wazuh` and `intake_eve` pipelines:
```bash
python3 -m engine.queue_manager --status --verbose
```

### Clearing Stale Queues
If the queue is blocked by malformed alerts, purge the specific partition:
```bash
# WARNING: This deletes data in the queue
python3 -m engine.queue_manager --purge --partition intake_wazuh
```

---

## 3. Monitoring Hash Chain Integrity

The `hash_chain_sealer` ensures the immutability of the triage logs. Integrity checks should be run daily.

### Manual Verification
Run the sealer verification script to check for tampering or corruption:
```bash
python3 -m engine.hash_chain_sealer --verify --path /var/lib/slm/chains/current.chain
```

### Repairing Broken Links
If the verification fails, attempt a re-index of the chain:
```bash
python3 -m engine.hash_chain_sealer --repair --force --input /var/lib/slm/chains/current.chain
```

---

## 4. Handling Quarantine Overflow

When `sanitization_pipeline` rejects alerts, they are moved to the quarantine directory. If this directory exceeds 10GB, the system will trigger a `CRITICAL` alert.

### Inspecting Quarantine
```bash
ls -lh /var/lib/slm/quarantine/
```

### Purging Old Quarantine Data
To remove items older than 30 days:
```bash
find /var/lib/slm/quarantine/ -type f -mtime +30 -name "*.json" -delete
```

### Re-processing Quarantined Alerts
If an alert was quarantined due to a transient `enrichment_scheduler` failure, move it back to the intake:
```bash
mv /var/lib/slm/quarantine/alert_12345.json /var/lib/slm/intake/
```

---

## 5. Recovering from Worker Crashes

The `slm_triage_worker` may crash if the `model_registry` returns unexpected schemas.

### Identifying Crash Causes
Check the last 50 lines of the worker log:
```bash
tail -n 50 /var/log/slm/triage_worker.log
```

### Restarting the Worker
If the worker is in a `FAILED` state:
```bash
sudo systemctl restart slm-triage-worker.service
```

### Clearing Stuck Locks
If the worker refuses to start due to a stale lock file:
```bash
rm /var/run/slm/triage_worker.lock
sudo systemctl start slm-triage-worker.service
```

---

## 6. Rotating API Keys

API keys for the `model_registry` and `enrichment_scheduler` are stored in the encrypted vault.

### Updating Registry Keys
1. Generate a new key via your provider.
2. Update the local vault:
```bash
python3 -m orchestrator.model_registry --update-key --provider openai --key-file ./new_key.txt
```

### Refreshing Enrichment Tokens
If the `enrichment_scheduler` is using an expired API token for threat intel feeds:
```bash
# Edit the configuration file
nano /etc/slm/enrichment.conf

# Reload the service to pick up new credentials
sudo systemctl reload slm-enrichment-scheduler.service
```

---

## 7. Maintenance Procedures

### Memory Retention Cleanup
The `memory.retention` module handles the pruning of old embeddings. Trigger a manual cleanup:
```bash
python3 -m memory.retention --cleanup --days 90
```

### Context Stitcher Health Check
Verify the `context_stitcher` is correctly mapping Wazuh alerts to EVE logs:
```bash
python3 -m orchestrator.context_stitcher --test-mapping --alert-id WAZUH-999
```

### Quota Ledger Audit
Check if any tenant or service is exceeding its triage quota:
```bash
python3 -m engine.quota_ledger --report --format table
```

### Log Rotation
Ensure logs are not filling the disk:
```bash
sudo logrotate -f /etc/logrotate.d/slm
```

### Emergency Stop
In the event of a runaway triage loop (e.g., infinite model calls), execute the emergency kill:
```bash
sudo pkill -f "slm_triage_worker"
sudo systemctl stop slm-engine.target
```

### System Health Summary
Run this command to get a quick overview of all sub-modules:
```bash
python3 -m engine.health_check --all --json
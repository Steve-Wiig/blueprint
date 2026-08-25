# LOCAL-SOC-SLM Operations Runbook

## Version: 11.9
## Last Updated: 2025-01-15

---

## 1. Starting/Stopping Services

### 1.1 Start All Core Services

```bash
# Activate virtual environment first
source /opt/local-soc-slm/venv/bin/activate

# Start the intake layer (Wazuh + Eve)
cd /opt/local-soc-slm
python -m engine.intake_wazuh --config config/intake_wazuh.yaml --daemon
python -m engine.intake_eve --config config/intake_eve.yaml --daemon

# Start sanitization pipeline
python -m engine.sanitization_pipeline --workers 4 --config config/sanitization.yaml --daemon

# Start queue manager
python -m engine.queue_manager --config config/queue.yaml --daemon

# Start SLM triage workers (adjust count based on GPU/CPU)
python -m engine.slm_triage_worker --workers 8 --model-config config/models.yaml --daemon

# Start enrichment scheduler
python -m engine.enrichment_scheduler --interval 300 --config config/enrichment.yaml --daemon

# Start IOC extractor
python -m engine.ioc_extractor --workers 4 --daemon

# Start hash chain sealer (runs every 60s by default)
python -m engine.hash_chain_sealer --interval 60 --daemon

# Start orchestrator services
python -m orchestrator.context_stitcher --daemon
python -m orchestrator.model_registry --config config/model_registry.yaml --daemon

# Start memory layer
python -m memory.embeddings --daemon
python -m memory.retention --config config/retention.yaml --daemon

# Start quota ledger
python -m engine.quota_ledger --daemon
```

### 1.2 Stop All Services Gracefully

```bash
# Send SIGTERM to all daemon processes using exact module paths
pkill -f "python -m engine.intake_wazuh"
pkill -f "python -m engine.intake_eve"
pkill -f "python -m engine.sanitization_pipeline"
pkill -f "python -m engine.queue_manager"
pkill -f "python -m engine.slm_triage_worker"
pkill -f "python -m engine.enrichment_scheduler"
pkill -f "python -m engine.ioc_extractor"
pkill -f "python -m engine.hash_chain_sealer"
pkill -f "python -m orchestrator.context_stitcher"
pkill -f "python -m orchestrator.model_registry"
pkill -f "python -m memory.embeddings"
pkill -f "python -m memory.retention"
pkill -f "python -m engine.quota_ledger"

# Wait for graceful shutdown (max 30s)
sleep 30

# Force kill if needed (target only our venv python processes)
pkill -9 -f "/opt/local-soc-slm/venv/bin/python"
```

### 1.3 Restart Individual Service

```bash
# Example: Restart SLM triage workers only
pkill -f "python -m engine.slm_triage_worker"
sleep 5
python -m engine.slm_triage_worker --workers 8 --model-config config/models.yaml --daemon

# Verify restart
python -m engine.queue_manager --status
```

### 1.4 Start Overnight Self-Improving Pipeline (v11.9)

```bash
# Schedule via cron (runs 02:00 daily)
# Ensure soc-user has write access to /var/log/local-soc-slm/ and read access to /opt/local-soc-slm/venv/
# Add to /etc/cron.d/local-soc-slm:
# 0 2 * * * soc-user /opt/local-soc-slm/venv/bin/python -m overnight.self_improver --config config/self_improver.yaml >> /var/log/local-soc-slm/self_improver.log 2>&1

# Manual execution for testing (use absolute venv python path)
cd /opt/local-soc-slm
/opt/local-soc-slm/venv/bin/python -m overnight.self_improver --config config/self_improver.yaml --dry-run

# Full run with backlog processing (backlog stored in /data/ for consistency with state files)
/opt/local-soc-slm/venv/bin/python -m overnight.self_improver --config config/self_improver.yaml --process-backlog /data/self_improver/fix_backlog.json
```

---

## 2. Checking Queue Health

### 2.1 Queue Status Overview

```bash
# Get comprehensive queue status
python -m engine.queue_manager --status --verbose

# Expected output:
# QUEUE STATUS REPORT
# ===================
# intake_raw:        1,234 messages (lag: 12s)
# sanitization:        56 messages (lag: 3s)
# triage_pending:     234 messages (lag: 45s)
# enrichment_pending:  12 messages (lag: 8s)
# writeback_pending:    3 messages (lag: 1s)
# quarantine:          87 messages
# dead_letter:          4 messages
```

### 2.2 Per-Queue Depth and Lag

```bash
# Check specific queue
python -m engine.queue_manager --queue triage_pending --depth --lag

# Check all queues with JSON output for monitoring
python -m engine.queue_manager --status --json | jq '.queues[] | {name: .name, depth: .depth, lag_seconds: .lag_seconds, consumers: .active_consumers}'

# Alert if any queue lag > 300s
python -m engine.queue_manager --status --json | jq -r '.queues[] | select(.lag_seconds > 300) | "ALERT: \(.name) lag=\(.lag_seconds)s"'
```

### 2.3 Consumer Health

```bash
# List active consumers per queue
python -m engine.queue_manager --consumers --verbose

# Check SLM triage worker registration
python -m engine.slm_triage_worker --list-workers

# Expected output:
# WORKER REGISTRY
# ===============
# worker-01: ACTIVE  (pid: 12345, gpu: 0, model: llama-3.1-8b, processed: 1,234)
# worker-02: ACTIVE  (pid: 12346, gpu: 1, model: llama-3.1-8b, processed: 1,198)
# worker-03: STALLED (pid: 12347, gpu: 2, model: llama-3.1-8b, last_heartbeat: 120s ago)
```

### 2.4 Queue Backpressure Metrics

```bash
# Get backpressure indicators
python -m engine.queue_manager --backpressure

# Key metrics to watch:
# - intake_raw growth rate > 100/min = upstream surge
# - triage_pending > 5000 = worker saturation
# - quarantine > 1000 = sanitization/triage failure spike
```

---

## 3. Monitoring Hash Chain Integrity

### 3.1 Verify Current Chain State

```bash
# Check hash chain head and integrity
python -m engine.hash_chain_sealer --verify --full

# Expected output:
# HASH CHAIN VERIFICATION
# =======================
# Chain head:        a3f2e8b1c4d5... (block #1,042,311)
# Last sealed:       2025-01-15 14:23:12 UTC
# Blocks verified:   1,042,311 / 1,042,311 (100%)
# Integrity:         OK
# Orphan blocks:     0
# Gap detected:      NO
```

### 3.2 Verify Specific Range

```bash
# Verify last N blocks
python -m engine.hash_chain_sealer --verify --last 10000

# Verify specific block range
python -m engine.hash_chain_sealer --verify --from-block 1040000 --to-block 1042311
```

### 3.3 Check Sealer Daemon Health

```bash
# Check sealer process
ps aux | grep "python -m engine.hash_chain_sealer"

# Check sealer logs for errors
tail -100 /var/log/local-soc-slm/hash_chain_sealer.log | grep -i error

# Verify sealing interval compliance
python -m engine.hash_chain_sealer --stats --last-hour
# Output shows: seals_per_minute, avg_seal_latency_ms, missed_intervals
```

### 3.4 Repair Broken Chain (Emergency)

```bash
# ONLY RUN IF VERIFICATION FAILS AND YOU HAVE CONFIRMED DATA LOSS
# 1. Stop all writers
pkill -f "python -m engine.queue_manager"
pkill -f "python -m engine.slm_triage_worker"

# 2. Find last good block
python -m engine.hash_chain_sealer --find-last-good --from-block 1040000

# 3. Truncate and reseal (DANGEROUS - requires manual confirmation)
# Note: --truncate-at expects a block NUMBER (integer), not a hash
# WARNING: This creates a gap. The sealer will re-index subsequent blocks on next seal cycle.
python -m engine.hash_chain_sealer --repair --truncate-at 1042000 --confirm-i-understand

# 4. Verify repair succeeded
python -m engine.hash_chain_sealer --verify --full

# 5. Restart services
# (see Section 1.1)
```

### 3.5 Hash Chain Monitoring Alerts

```bash
# Add to monitoring (Prometheus/Grafana)
# Alert if: hash_chain_sealer_missed_intervals > 0
# Alert if: hash_chain_verification_failures > 0
# Alert if: hash_chain_head_age_seconds > 120
```

---

## 4. Handling Quarantine Overflow

### 4.1 Detect Quarantine Growth

```bash
# Check quarantine queue depth
python -m engine.queue_manager --queue quarantine --depth

# Check quarantine growth rate (last hour)
python -m engine.queue_manager --queue quarantine --growth-rate --window 3600

# List quarantine reasons
python -m engine.queue_manager --queue quarantine --sample 100 --show-reason
```

### 4.2 Analyze Quarantine Contents

```bash
# Export quarantine samples for analysis
python -m engine.queue_manager --queue quarantine --export /tmp/quarantine_sample.json --limit 500

# Categorize by rejection reason
python -c "
import json
with open('/tmp/quarantine_sample.json') as f:
    data = json.load(f)
reasons = {}
for msg in data['messages']:
    reason = msg.get('quarantine_reason', 'unknown')
    reasons[reason] = reasons.get(reason, 0) + 1
for r, c in sorted(reasons.items(), key=lambda x: -x[1]):
    print(f'{c:4d}  {r}')
"
```

### 4.3 Remediate Common Quarantine Causes

#### 4.3.1 Sanitization Failures (PII/Secrets)

```bash
# Review sanitization rules
cat config/sanitization.yaml | grep -A5 "patterns:"

# Test specific message against sanitizer
python -m engine.sanitization_pipeline --test-message '{"message": "password=secret123"}'

# Update patterns and reload (no restart needed)
python -m engine.sanitization_pipeline --reload-config
```

#### 4.3.2 Schema Validation Failures

```bash
# Check schema registry
python -m engine.intake_wazuh --show-schemas

# Validate sample against schema
python -m engine.intake_wazuh --validate-sample /tmp/quarantine_sample.json
```

#### 4.3.3 Enrichment Failures

```bash
# Check enrichment scheduler errors
grep -i "enrichment failed" /var/log/local-soc-slm/enrichment_scheduler.log | tail -20

# Re-run enrichment for quarantined messages
python -m engine.enrichment_scheduler --reprocess-quarantine --batch-size 100
```

### 4.4 Emergency Quarantine Drain

```bash
# If quarantine > 5000 and growing: EMERGENCY DRAIN
# 1. Pause intake temporarily
python -m engine.intake_wazuh --pause
python -m engine.intake_eve --pause

# 2. Increase triage workers temporarily
pkill -f "python -m engine.slm_triage_worker"
python -m engine.slm_triage_worker --workers 16 --model-config config/models.yaml --daemon

# 3. Process quarantine with relaxed rules (review first!)
python -m engine.queue_manager --queue quarantine --reprocess --relaxed-sanitization --batch-size 500

# 4. Resume intake
python -m engine.intake_wazuh --resume
python -m engine.intake_eve --resume
```

---

## 5. Recovering from Worker Crashes

### 5.1 Detect Worker Failures

```bash
# Check worker heartbeats
python -m engine.slm_triage_worker --list-workers | grep -E "(STALLED|DEAD|MISSING)"

# Check systemd/journald for OOM kills
journalctl -u local-soc-slm --since "1 hour ago" | grep -i "oom\|killed\|segfault"

# Check GPU memory errors
nvidia-smi -q -d PIDS | grep -A5 "Process ID"
```

### 5.2 Automatic Recovery (Configured)

```bash
# Verify auto-recovery is enabled
grep -A10 "auto_recovery:" config/slm_triage_worker.yaml

# Expected config:
# auto_recovery:
#   enabled: true
#   max_restarts: 3
#   restart_window_seconds: 300
#   health_check_interval: 30
```

### 5.3 Manual Worker Recovery

```bash
# Restart single crashed worker (by GPU ID)
python -m engine.slm_triage_worker --restart-worker --gpu 2 --model-config config/models.yaml

# Restart all workers on specific model
python -m engine.slm_triage_worker --restart-model llama-3.1-8b

# Full worker pool restart
pkill -f "python -m engine.slm_triage_worker"
sleep 10
python -m engine.slm_triage_worker --workers 8 --model-config config/models.yaml --daemon
```

### 5.4 Recover In-Flight Messages

```bash
# Check for messages stuck in triage_pending (worker crashed mid-process)
python -m engine.queue_manager --queue triage_pending --stuck-threshold 300 --list

# Re-queue stuck messages (moves back to triage_pending with retry_count++)
python -m engine.queue_manager --queue triage_pending --requeue-stuck --max-retries 3

# Check dead letter queue
python -m engine.queue_manager --queue dead_letter --depth
python -m engine.queue_manager --queue dead_letter --export /tmp/dlq_export.json --limit 100
```

### 5.5 GPU Recovery

```bash
# Reset GPU if workers show CUDA errors
sudo nvidia-smi -r -i 0  # Reset GPU 0 (requires persistence mode off)

# Better: restart with GPU reset
pkill -f "python -m engine.slm_triage_worker"
sleep 5
sudo nvidia-smi -r -i 0,1,2,3  # Reset all GPUs
sleep 10
python -m engine.slm_triage_worker --workers 8 --model-config config/models.yaml --daemon
```

---

## 6. Rotating API Keys

### 6.1 Rotate OpenRouter API Key (v11.9)

```bash
# 1. Generate new key at https://openrouter.ai/keys
# 2. Update quota ledger (master key store) with new key
python -m engine.quota_ledger --rotate-key openrouter --new-key "sk-or-v1-NEW_KEY_HERE"

# 3. Update llm_client.py config (multi-provider fallback)
# Edit config/llm_providers.yaml:
# openrouter:
#   api_key: "sk-or-v1-NEW_KEY_HERE"
#   priority: 1
#   rate_limit_rpm: 60
#   rate_limit_tpm: 100000

# 4. SECURITY: Restrict permissions on config file
chmod 600 config/llm_providers.yaml

# 5. Reload llm_client without restart (model_registry handles provider reload)
python -m orchestrator.model_registry --reload-providers

# 6. Verify key works (llm_client.py routes internally based on llm_providers.yaml priority; model param is logical name)
python -c "
from orchestrator.llm_client import LLMClient
client = LLMClient.from_config('config/llm_providers.yaml')
try:
    result = client.generate('test', model='claude-3.5-sonnet', max_tokens=5)
    print('Key valid:', result is not None)
except Exception as e:
    print('Key invalid:', str(e))
"
```

### 6.2 Rotate Local Model API Keys (Ollama/vLLM)

```bash
# For vLLM with API key auth
# 1. Generate new key
openssl rand -hex 32

# 2. Update vLLM config
# Edit /etc/vllm/config.yaml:
# api_key: "NEW_KEY_HERE"

# 3. Restart vLLM
sudo systemctl restart vllm

# 4. Update model_registry (which updates llm_providers.yaml internally)
python -m orchestrator.model_registry --update-endpoint vllm-local --api-key "NEW_KEY_HERE"
python -m orchestrator.model_registry --reload-providers

# 5. SECURITY: Restrict permissions
chmod 600 config/llm_providers.yaml
```

### 6.3 Rotate Embedding API Keys

```bash
# For memory.embeddings (if using remote embeddings)
python -m memory.embeddings --rotate-key --provider openai --new-key "sk-NEW_KEY"

# Verify
python -m memory.embeddings --test-connection
```

### 6.4 Update OpenRouter Quota Tracking (v11.9)

```bash
# Check current quota status (openrouter_quota is a helper under engine/ that reads from quota_ledger)
python -m engine.openrouter_quota --status

# Expected output:
# OPENROUTER QUOTA STATUS
# ======================
# Current key:       sk-or-v1-abc... (last 4: def1)
# Daily limit:       1,000,000 tokens
# Used today:        234,567 tokens (23.5%)
# Reset at:          2025-01-16 00:00 UTC
# Rate limit:        60 RPM / 100,000 TPM
# Current usage:     12 RPM / 45,000 TPM

# After key rotation in quota_ledger, reset quota tracking helper
python -m engine.openrouter_quota --reset --key "sk-or-v1-NEW_KEY_HERE"

# Verify fallback chain works (llm_client.py handles fallback internally; test by forcing primary failure)
python -c "
from orchestrator.llm_client import LLMClient
client = LLMClient.from_config('config/llm_providers.yaml')

# Test primary (should succeed with new key)
try:
    r1 = client.generate('test', model='claude-3.5-sonnet', max_tokens=10)
    print('Primary:', 'OK' if r1 else 'FAIL')
except Exception as e:
    print('Primary: FAIL -', str(e))

# Test fallback by temporarily disabling primary in config or using a model only on fallback provider
# The client.generate() returns None on failure (not exception) per implementation
r2 = client.generate('test', model='llama-3.1-405b', max_tokens=10)
print('Fallback:', 'OK' if r2 else 'FAIL')
"
```

### 6.5 Key Rotation Checklist

```bash
# Pre-rotation
[ ] New key generated and stored in password manager
[ ] Old key expiration confirmed
[ ] Rollback plan documented

# Rotation
[ ] Update quota_ledger (master)
[ ] Update llm_providers.yaml
[ ] chmod 600 config/llm_providers.yaml
[ ] Reload model_registry
[ ] Verify all providers respond
[ ] Run test triage on sample alerts

# Post-rotation
[ ] Monitor quota_ledger for 15 min
[ ] Check llm_client fallback logs
[ ] Verify overnight.self_improver uses new key
[ ] Revoke old key at provider
```

---

## 7. Overnight Self-Improving Pipeline Operations (v11.9)

### 7.1 Pipeline Overview

The overnight pipeline (`overnight/self_improver.py`) performs:
- Model performance analysis on previous day's triage decisions
- Automatic prompt optimization for SLM triage worker
- False positive/negative pattern mining
- Backlog processing from `/data/self_improver/fix_backlog.json`
- Multi-provider LLM evaluation via `llm_client.py` with fallback
- Quota-aware execution via `engine.openrouter_quota` (reads from `engine.quota_ledger`)

### 7.2 Manual Pipeline Execution

```bash
# Dry run (no changes applied)
/opt/local-soc-slm/venv/bin/python -m overnight.self_improver --config config/self_improver.yaml --dry-run --verbose

# Full run with specific date
/opt/local-soc-slm/venv/bin/python -m overnight.self_improver --config config/self_improver.yaml --date 2025-01-14

# Process accumulated backlog (stored in /data/ for consistency)
/opt/local-soc-slm/venv/bin/python -m overnight.self_improver --config config/self_improver.yaml --process-backlog /data/self_improver/fix_backlog.json --max-items 500

# Force re-evaluation of specific model
/opt/local-soc-slm/venv/bin/python -m overnight.self_improver --config config/self_improver.yaml --reevaluate-model llama-3.1-8b
```

### 7.3 Monitor Pipeline Execution

```bash
# Check last run status
cat /var/log/local-soc-slm/self_improver/latest_run.json | jq .

# Key metrics:
# - "status": "completed" | "partial" | "failed"
# - "models_evaluated": 3
# - "prompts_optimized": 2
# - "backlog_processed": 47
# - "quota_consumed": {"openrouter": 125000, "local": 0}
# - "fallback_activations": 3
# - "duration_seconds": 1847
```

### 7.4 Handle Pipeline Failures

```bash
# Check failure reason
cat /var/log/local-soc-slm/self_improver/latest_run.json | jq '.error'

# Common failures and fixes:

# 1. Quota exhausted
# Check: python -m engine.openrouter_quota --status
# Fix: Wait for reset or rotate key (Section 6.1)

# 2. All LLM providers failed
# Check: grep "fallback exhausted" /var/log/local-soc-slm/self_improver.log
# Fix: Verify llm_providers.yaml, check network connectivity

# 3. Backlog corruption
# Check: python -m overnight.self_improver --validate-backlog /data/self_improver/fix_backlog.json
# Fix: python -m overnight.self_improver --repair-backlog /data/self_improver/fix_backlog.json

# 4. Prompt optimization failed validation
# Check: grep "validation failed" /var/log/local-soc-slm/self_improver.log
# Fix: Review proposed prompts in /tmp/self_improver_proposals/
```

### 7.5 Apply/Revert Pipeline Changes

```bash
# Review proposed changes before applying
ls -la /tmp/self_improver_proposals/
cat /tmp/self_improver_proposals/prompt_changes.yaml

# Apply approved changes
python -m overnight.self_improver --apply-proposals /tmp/self_improver_proposals/ --confirm

# Revert last applied changes
python -m overnight.self_improver --revert-last --confirm

# View change history
python -m overnight.self_improver --history --limit 10
```

---

## 8. Emergency Procedures

### 8.1 Full System Reset

```bash
# 1. Stop all services (Section 1.2)
# 2. Clear queues (CAUTION: DATA LOSS)
python -m engine.queue_manager --purge-all --confirm-i-understand

# 3. Reset hash chain (CAUTION: BREAKS AUDIT TRAIL)
python -m engine.hash_chain_sealer --reset --confirm-i-understand

# 4. Clear quarantine and dead letter
python -m engine.queue_manager --queue quarantine --purge --confirm
python -m engine.queue_manager --queue dead_letter --purge --confirm

# 5. Restart all services (Section 1.1)
```

### 8.2 Disaster Recovery Checklist

```bash
# Run after any major incident
[ ] Verify hash chain integrity (Section 3.1)
[ ] Check queue depths normal (Section 2.1)
[ ] Verify all workers healthy (Section 2.3)
[ ] Test end-to-end flow with sample alert
[ ] Confirm quota ledger operational
[ ] Verify overnight pipeline can run
[ ] Check monitoring alerts clear
[ ] Document incident in runbook
```

---

## 9. Key File Paths Reference

| Component | Config Path | Log Path | Data Path |
|-----------|-------------|----------|-----------|
| Intake Wazuh | `config/intake_wazuh.yaml` | `/var/log/local-soc-slm/intake_wazuh.log` | `/data/queue/intake_raw` |
| Intake Eve | `config/intake_eve.yaml` | `/var/log/local-soc-slm/intake_eve.log` | `/data/queue/intake_raw` |
| Sanitization | `config/sanitization.yaml` | `/var/log/local-soc-slm/sanitization.log` | `/data/queue/sanitization` |
| Queue Manager | `config/queue.yaml` | `/var/log/local-soc-slm/queue_manager.log` | `/data/queue/*` |
| SLM Triage | `config/slm_triage_worker.yaml` | `/var/log/local-soc-slm/slm_triage.log` | `/data/queue/triage_pending` |
| Enrichment | `config/enrichment.yaml` | `/var/log/local-soc-slm/enrichment.log` | `/data/queue/enrichment_pending` |
| Hash Chain | `config/hash_chain.yaml` | `/var/log/local-soc-slm/hash_chain_sealer.log` | `/data/hash_chain/` |
| Model Registry | `config/model_registry.yaml` | `/var/log/local-soc-slm/model_registry.log` | `/data/models/` |
| LLM Providers | `config/llm_providers.yaml` | `/var/log/local-soc-slm/llm_client.log` | - |
| Self Improver | `config/self_improver.yaml` | `/var/log/local-soc-slm/self_improver.log` | `/data/self_improver/` |
| OpenRouter Quota | `config/openrouter_quota.yaml` | `/var/log/local-soc-slm/openrouter_quota.log` | `/data/quota/openrouter.json` |
| Fix Backlog | - | - | `/data/self_improver/fix_backlog.json` |
| Retention | `config/retention.yaml` | `/var/log/local-soc-slm/retention.log` | `/data/memory/` |
| Embeddings | `config/embeddings.yaml` | `/var/log/local-soc-slm/embeddings.log` | `/data/embeddings/` |

---

## 10. Useful One-Liners

```bash
# Quick health check
python -m engine.queue_manager --status --json | jq -r '.overall_health'

# Tail all logs
tail -f /var/log/local-soc-slm/*.log

# Count messages processed last hour
grep "processed" /var/log/local-soc-slm/slm_triage.log | grep "$(date -d '1 hour ago' '+%H:')" | wc -l

# Check GPU utilization
watch -n 5 nvidia-smi

# Check disk space for queues
df -h /data/queue

# Verify all daemons running
pgrep -af "python -m engine\.|python -m orchestrator\.|python -m memory\." | wc -l
```

---

*End of Runbook*
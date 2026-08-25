# LOCAL-SOC-SLM Operator Manual v11.9

## ⚠️ Breaking Changes (v11.9)

- **Removed**: `engine/intake_syslog.py` — Migrate to `intake_wazuh.py` or `intake_eve.py` immediately.
- **Schema Change**: `sanitization_pipeline.py` now requires `config/sanitization_rules.yaml` v2 schema (adds `pii_entity_types` field).
- **Hash Chain**: Seal interval reduced from 10k to 1k events for higher audit granularity.
- **New Dependency**: `liburing-dev` must be installed **before** building the Python environment (`apt install liburing-dev` then `pip install -r requirements.txt`).

---

## 1. System Overview

LOCAL-SOC-SLM is a local Security Operations Center automation platform designed for air-gapped and hybrid environments. The platform processes security events through a multi-layered pipeline:

**Engine Layer** (`engine/`):
- `intake_wazuh.py` — Wazuh agent log ingestion via JSON socket
- `intake_eve.py` — Suricata EVE JSON ingestion
- `sanitization_pipeline.py` — PII redaction, field normalization, schema validation
- `queue_manager.py` — Priority queue with Redis backend, TTL-based eviction
- `slm_triage_worker.py` — Local SLM inference for alert triage (confidence scoring, MITRE ATT&CK tagging)
- `enrichment_scheduler.py` — Async IOC enrichment (VirusTotal, AbuseIPDB, OTX)
- `ioc_extractor.py` — Regex + ML-based indicator extraction
- `hash_chain_sealer.py` — Append-only hash chain for audit integrity
- `quota_ledger.py` — Token budget tracking per model/provider

**Orchestrator Layer** (`orchestrator/`):
- `model_registry.py` — Model metadata, capability tags, routing rules
- `context_stitcher.py` — RAG context assembly from memory layer

**Memory Layer** (`memory/`):
- `retention.py` — TTL-based purge, legal hold, GDPR compliance
- `embeddings.py` — Local embedding generation (sentence-transformers), vector index management

**Overnight Self-Improving Pipeline** (`overnight/`):
- `self_improver.py` — Nightly model fine-tuning loop using triage feedback
- `llm_client.py` — Multi-provider fallback (Ollama, vLLM, OpenRouter) with rate-limit management
- `openrouter_quota.py` — OpenRouter credit tracking, daily budget enforcement
- `fix_backlog.json` — Persistent queue of failed self-improvement tasks for retry (stored in `/var/lib/soc/fix_backlog.json`)

---

## 2. Hardware Requirements (Section 28)

| Component | Minimum | Recommended | Notes |
|-----------|---------|-------------|-------|
| CPU | 8 cores (AVX2) | 16+ cores (AVX-512) | SLM inference benefits from AVX-512 VNNI |
| RAM | 32 GB DDR4 | 64 GB DDR5 | Embeddings index + model weights + Redis |
| GPU | NVIDIA RTX 3080 (10 GB) | 2× RTX 4090 (24 GB) | vLLM tensor parallelism; CUDA 12.1+ |
| Storage | 500 GB NVMe | 2 TB NVMe RAID-1 | WAL + vector index + model checkpoints |
| Network | 1 Gbps | 10 Gbps | Intra-cluster replication, intake throughput |
| OS | Ubuntu 22.04 LTS | Ubuntu 24.04 LTS | Kernel 6.8+ for io_uring support |

**Section 28 Compliance**: All production deployments must pass `scripts/validate_hardware.py --section-28` (exit code 0 = pass, 1 = fail, 2 = warning). Run weekly via cron.

**Critical Note for Ubuntu 24.04**: Install `liburing-dev` **before** creating the Python virtual environment:
```bash
apt update && apt install -y liburing-dev
python3 -m venv /opt/soc/venv
/opt/soc/venv/bin/pip install -r requirements.txt
```
Without `liburing-dev` present at build time, `intake_wazuh.py` falls back to epoll with ~15% throughput reduction.

---

## 3. Database Setup

### 3.1 PostgreSQL (Primary Metadata Store)

```bash
# Initialize schema
psql -U soc_admin -d local_soc -f sql/schema_v11.sql

# Verify migrations
alembic -c alembic.ini upgrade head
# Expected exit codes: 0=success, 1=partial, 2=conflict, 3=db_locked
```

**Required extensions**: `pgvector`, `uuid-ossp`, `pg_trgm`, `btree_gin`

### 3.2 Redis (Queue + Cache)

```bash
# Configure persistence
redis-cli CONFIG SET appendonly yes
redis-cli CONFIG SET appendfsync everysec
redis-cli CONFIG SET maxmemory 8gb
# WARNING: Do NOT use 'allkeys-lru' — it evicts queue keys causing data loss.
# Use 'volatile-lru' and ensure queue keys have no TTL (PERSIST) or very long TTL.
redis-cli CONFIG SET maxmemory-policy volatile-lru
```

**Queue Key Protection**: After starting intake adapters, verify queue keys are persistent:
```bash
redis-cli -n 1 PERSIST triage:queue:high triage:queue:normal triage:queue:low
```

### 3.3 Vector Index (FAISS on Disk)

```bash
# Initialize empty index
python -m memory.embeddings init-index --dim 1024 --index-type IVF4096,PQ32
# Exit codes: 0=created, 1=exists, 2=permission_denied, 3=disk_full
```

---

## 4. Running Intake Adapters

### 4.1 Wazuh Intake (`engine/intake_wazuh.py`)

```bash
# Foreground (debug)
python -m engine.intake_wazuh --config config/intake_wazuh.yaml --log-level DEBUG

# Systemd service (production)
systemctl start soc-intake-wazuh
systemctl status soc-intake-wazuh
# Exit codes: 0=running, 1=config_error, 2=socket_bind_fail, 3=redis_unavailable
```

**Config** (`config/intake_wazuh.yaml`):
```yaml
listen: "0.0.0.0:6060"
batch_size: 500
flush_interval_ms: 100
redis_url: "redis://localhost:6379/1"
sanitization_rules: "config/sanitization_rules.yaml"
```

**SECURITY WARNING**: Port 6060 binds to `0.0.0.0` by default and lacks native TLS/Auth. **Firewall this port to only accept traffic from the Wazuh manager IP(s)**:
```bash
ufw allow from <WAZUH_MANAGER_IP> to any port 6060 proto tcp
```

### 4.2 Suricata EVE Intake (`engine/intake_eve.py`)

```bash
python -m engine.intake_eve --tail /var/log/suricata/eve.json --redis-url redis://localhost:6379/1
# Exit codes: 0=ok, 1=file_not_found, 2=json_parse_error, 3=queue_full
```

### 4.3 Health Check

```bash
curl -s http://localhost:8081/health/intake | jq '.adapters[] | {name, status, lag_ms}'
# Expected: all adapters "healthy", lag_ms < 500
```

---

## 5. Monitoring the Triage Queue

### 5.1 Queue Dashboard

```bash
# Real-time queue depth (adjust -n <db_index> if Redis DB customized)
watch -n 2 'redis-cli -n 1 LLEN triage:queue:high && redis-cli -n 1 LLEN triage:queue:normal && redis-cli -n 1 LLEN triage:queue:low'

# Worker status
python -m engine.queue_manager status --format json
# Output: {"workers": 4, "idle": 1, "processing": 3, "backlog": 127, "avg_latency_ms": 245}
```

### 5.2 SLM Triage Worker (`engine/slm_triage_worker.py`)

```bash
# Start workers (systemd)
systemctl start soc-triage-worker@1 soc-triage-worker@2 soc-triage-worker@3 soc-triage-worker@4

# Manual run with profiling
python -m engine.slm_triage_worker --worker-id 1 --model mistral-7b-instruct-v0.3 --profile
# Exit codes: 0=shutdown, 1=model_load_fail, 2=queue_disconnect, 3=oom, 4=quota_exhausted
```

### 5.3 Key Metrics (Prometheus + Grafana)

| Metric | Alert Threshold | Dashboard Panel |
|--------|-----------------|-----------------|
| `soc_triage_queue_depth` | > 1000 for 5m | Queue Backlog |
| `soc_triage_latency_p99` | > 30s | Latency Heatmap |
| `soc_triage_confidence_low` | > 20% of alerts | Confidence Distribution |
| `soc_worker_oom_total` | > 0 | Worker Health |

---

## 6. Running Retention Cron

### 6.1 Daily Retention Job (`memory/retention.py`)

```bash
# Cron entry (02:30 UTC daily)
30 2 * * * /opt/soc/venv/bin/python -m memory.retention run --config config/retention.yaml >> /var/log/soc/retention.log 2>&1

# Manual execution with dry-run
python -m memory.retention run --dry-run --verbose
# Exit codes: 0=success, 1=config_error, 2=db_lock, 3=legal_hold_conflict, 4=partial_failure
```

### 6.2 Retention Policy (`config/retention.yaml`)

```yaml
policies:
  - name: "raw_events"
    table: "events_raw"
    ttl_days: 30
    legal_hold_tag: "litigation_hold"
  - name: "enriched_events"
    table: "events_enriched"
    ttl_days: 365
  - name: "embeddings"
    index: "faiss_main"
    ttl_days: 730
    purge_orphaned_vectors: true
  - name: "triage_feedback"
    table: "triage_feedback"
    ttl_days: 1095  # 3 years for model training
```

### 6.3 Verification

```bash
python -m memory.retention verify --policy raw_events
# Output: {"scanned": 2847321, "purged": 12453, "errors": 0, "duration_ms": 45210}
```

---

## 7. Checking Hash-Chain Integrity

### 7.1 Seal Verification (`engine/hash_chain_sealer.py`)

```bash
# Full chain verification (run weekly)
python -m engine.hash_chain_sealer verify --full --config config/hash_chain.yaml
# Exit codes: 0=valid, 1=corrupt, 2=missing_seal, 3=config_error, 4=truncated

# Incremental verification (daily cron)
python -m engine.hash_chain_sealer verify --since-last-seal
```

### 7.2 Seal Generation (Automatic)

The sealer runs as a background thread in `queue_manager.py` every 1000 events or 1 hour (whichever comes first). Manual seal:

```bash
python -m engine.hash_chain_sealer seal --force
# Exit codes: 0=sealed, 1=queue_empty, 2=redis_fail, 3=write_fail
```

### 7.3 Audit Log

```bash
# View last 10 seals
sqlite3 /var/lib/soc/hash_chain.db "SELECT seal_id, timestamp, event_count, root_hash FROM seals ORDER BY seal_id DESC LIMIT 10;"
```

---

## 8. Overnight Self-Improving Pipeline (v11.9)

### 8.1 Pipeline Overview

The overnight pipeline runs 03:00-05:00 local time, consuming triage feedback to improve the local SLM:

1. **Data Collection** — Pulls `triage_feedback` where `used_for_training=false`
2. **Dataset Construction** — Formats as instruction-tuning pairs (prompt: alert context, completion: analyst decision)
3. **Training Loop** — LoRA fine-tuning on base model (default: `mistral-7b-instruct-v0.3`)
4. **Evaluation** — Benchmarks against held-out set (F1, calibration error)
5. **Promotion** — If metrics improve, registers new adapter in `model_registry.py`
6. **Cleanup** — Marks feedback rows `used_for_training=true`

### 8.2 Running the Pipeline (`overnight/self_improver.py`)

```bash
# Systemd timer (recommended)
systemctl enable --now soc-self-improver.timer

# Manual execution (ALWAYS run from /opt/soc/ project root)
cd /opt/soc && python -m overnight.self_improver run --config config/self_improver.yaml --verbose
# Exit codes:
#   0 = success, model promoted
#   1 = config error
#   2 = insufficient feedback data (< 100 samples)
#   3 = training failed (OOM, divergence)
#   4 = evaluation failed (metrics regressed)
#   5 = promotion blocked (quota, registry lock)
#   6 = fix_backlog processing required (pipeline halts if backlog has unrecoverable tasks)
```

**Systemd Unit Requirement**: The `soc-self-improver.service` must include:
```ini
Restart=on-failure
RestartPreventExitStatus=6
```
This ensures exit code 6 (fix_backlog intervention required) forces manual operator action.

### 8.3 Configuration (`config/self_improver.yaml`)

```yaml
schedule: "0 3 * * *"  # 03:00 daily
base_model: "mistral-7b-instruct-v0.3"
lora_config:
  r: 16
  alpha: 32
  dropout: 0.05
  target_modules: ["q_proj", "v_proj", "k_proj", "o_proj"]
training:
  epochs: 3
  batch_size: 4
  grad_accum: 8
  lr: 2e-4
  max_seq_len: 4096
evaluation:
  min_f1_improvement: 0.02
  max_calibration_error: 0.15
  holdout_fraction: 0.1
providers:
  primary: "vllm"
  fallback: ["ollama", "openrouter"]
quota:
  daily_token_budget: 500000
  openrouter_daily_usd: 10.00
```

### 8.4 Multi-Provider LLM Client (`overnight/llm_client.py`)

**Important**: Always run from the project root (`/opt/soc/`) or ensure `PYTHONPATH` includes `/opt/soc/` in your shell profile (`export PYTHONPATH=/opt/soc:$PYTHONPATH`).

```python
from overnight.llm_client import MultiProviderClient, ProviderConfig

client = MultiProviderClient([
    ProviderConfig(name="vllm", base_url="http://localhost:8000/v1", priority=1, rate_limit_rpm=600),
    ProviderConfig(name="ollama", base_url="http://localhost:11434/v1", priority=2, rate_limit_rpm=100),
    ProviderConfig(name="openrouter", base_url="https://openrouter.ai/api/v1", priority=3, rate_limit_rpm=50, api_key_env="OPENROUTER_API_KEY"),
])

# Automatic fallback on 429, 503, timeout
response = client.chat.completions.create(
    model="mistral-7b-instruct-v0.3",
    messages=[{"role": "user", "content": prompt}],
    temperature=0.1,
    max_tokens=2048,
)
```

**Rate-limit management**: Token bucket per provider, shared across workers via Redis (`quota:llm:{provider}`). Exhaustion triggers fallback.

**Air-Gapped Environments**: If deployed without internet, the `openrouter` provider will fail with connection errors. Verify connectivity:
```bash
curl -I https://openrouter.ai/api/v1/models --max-time 5
# If this fails, remove 'openrouter' from the fallback list in config/self_improver.yaml
```

### 8.5 OpenRouter Quota Tracking (`overnight/openrouter_quota.py`)

The `openrouter_daily_usd` limit is a **soft limit with warning only**. The script logs a `WARNING` when 80% is reached and `CRITICAL` at 100%, but **does not automatically stop the pipeline**.

**Critical Behavior**: If `openrouter_daily_usd` is reached, the `llm_client` will automatically shift to the next available provider in the `fallback` list. **If no local providers (vLLM, Ollama) are configured and healthy, the pipeline will stall.**

```bash
# Check current usage
python -m overnight.openrouter_quota status
# Output: {"daily_used_usd": 3.42, "daily_limit_usd": 10.00, "remaining_usd": 6.58, "reset_utc": "2025-01-15T00:00:00Z"}

# Reset (manual override)
python -m overnight.openrouter_quota reset --confirm
# Exit codes: 0=ok, 1=not_authorized, 2=api_error
```

### 8.6 Fix Backlog (`/var/lib/soc/fix_backlog.json`)

**Location**: `/var/lib/soc/fix_backlog.json` (persistent data directory, NOT in source tree). The `self_improver.py` module **explicitly uses this absolute path**; ensure the service user has write permissions to `/var/lib/soc/`. Do not rely on relative paths.

Failed self-improvement tasks are persisted here for manual review:

```json
{
  "tasks": [
    {
      "task_id": "simp_20250114_030000_abc123",
      "stage": "training",
      "error": "CUDA OOM: tried to allocate 2.50 GiB",
      "timestamp": "2025-01-14T03:15:22Z",
      "retry_count": 2,
      "max_retries": 3,
      "context": {"batch_size": 4, "grad_accum": 8, "seq_len": 4096}
    }
  ]
}
```

**Recovery**:
```bash
# Inspect backlog
python -m overnight.self_improver backlog list

# Retry specific task
python -m overnight.self_improver backlog retry --task-id simp_20250114_030000_abc123 --reduce-batch-size

# Clear resolved
python -m overnight.self_improver backlog clear --older-than 7d
```

### 8.7 Quota Ledger Billing Export

Generate monthly billing report for token usage across all providers:

```bash
# Monthly billing export (run 1st of month)
python -m engine.quota_ledger export_billing --month 2025-01 --output /var/log/soc/billing_2025-01.json
# Exit codes: 0=success, 1=db_error, 2=permission_denied

# Output format:
# {"period": "2025-01", "providers": {"vllm": {"tokens": 12450000, "est_cost_usd": 0.0}, "openrouter": {"tokens": 892000, "est_cost_usd": 4.46}}, "total_est_cost_usd": 4.46}
```

Add to monthly checklist (Section 10.3).

---

## 9. Troubleshooting Common Failures

### 9.1 Intake Adapter Failures

| Symptom | Cause | Resolution |
|---------|-------|------------|
| `intake_wazuh` exit 2 | Port 6060 in use | `ss -ltnp | grep 6060`, kill conflicting process |
| `intake_eve` exit 2 | Malformed JSON line | `jq -c . /var/log/suricata/eve.json | tail -n 1000 > /tmp/test.json && python -m engine.intake_eve --tail /tmp/test.json` (use `tail` to catch end-of-file corruption) |
| Redis `OOM` | Queue backlog > 10k | Scale workers: `systemctl start soc-triage-worker@5` |

### 9.2 Triage Worker Failures

| Exit Code | Meaning | Action |
|-----------|---------|--------|
| 1 | Model load fail | Check `/var/log/soc/triage-worker*.log` for `torch.cuda.OutOfMemoryError`; reduce `batch_size` in config |
| 3 | OOM during inference | Enable `offload_to_cpu` in `model_registry.py` for this model |
| 4 | Quota exhausted | Check `quota_ledger.py` dashboard; wait for reset or increase budget |

### 9.3 Retention Job Failures

| Exit Code | Meaning | Action |
|-----------|---------|--------|
| 2 | DB lock | `SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state='idle in transaction' AND query LIKE '%retention%';` |
| 3 | Legal hold conflict | Review `legal_hold` table; coordinate with legal before forcing purge |

### 9.4 Hash Chain Corruption

```bash
# Diagnose
python -m engine.hash_chain_sealer verify --full --verbose 2>&1 | tail -50

# Rebuild from last good seal (DANGEROUS - requires audit approval)
python -m engine.hash_chain_sealer rebuild --from-seal 12450 --confirm-i-understand
```

### 9.5 Self-Improver Pipeline Failures

| Exit Code | Stage | Resolution |
|-----------|-------|------------|
| 2 | Data collection | Wait for more feedback; minimum 100 samples required |
| 3 | Training | Reduce `batch_size` to 2, `grad_accum` to 16; check GPU memory |
| 4 | Evaluation | New model regressed; check `fix_backlog.json` for details |
| 5 | Promotion | Registry lock; `python -m orchestrator.model_registry unlock --force` |
| 6 | Fix backlog | Run `python -m overnight.self_improver backlog list` and address manually |

### 9.6 OpenRouter Quota Exhausted

```bash
# Check quota
python -m overnight.openrouter_quota status

# Switch to local-only mode (edit config)
sed -i 's/providers:.*/providers:\n  primary: "vllm"\n  fallback: ["ollama"]/' config/self_improver.yaml

# Restart pipeline
systemctl restart soc-self-improver
```

### 9.7 Network / Firewall (Air-Gapped Deployments)

If the environment is air-gapped, the `openrouter` provider in `llm_client.py` will fail with connection errors. Verify and adjust:

```bash
# Test connectivity
curl -I https://openrouter.ai/api/v1/models --max-time 5

# If failed, remove openrouter from fallback chain
sed -i '/openrouter/d' config/self_improver.yaml
# Ensure local providers are configured:
# providers:
#   primary: "vllm"
#   fallback: ["ollama"]
systemctl restart soc-self-improver
```

---

## 10. Operational Checklists

### 10.1 Daily (Automated via Cron)

- [ ] Retention job completes (exit 0)
- [ ] Hash chain incremental verify (exit 0)
- [ ] Self-improver pipeline runs (exit 0 or 2)
- [ ] Queue depth < 500
- [ ] All workers healthy (`soc_triage_worker_oom_total == 0`)

### 10.2 Weekly

- [ ] Full hash chain verification
- [ ] Hardware validation (`scripts/validate_hardware.py --section-28`)
- [ ] Model registry audit (`python -m orchestrator.model_registry audit`)
- [ ] OpenRouter quota review
- [ ] Fix backlog review (`python -m overnight.self_improver backlog list`)

### 10.3 Monthly

- [ ] Embedding index rebuild (`python -m memory.embeddings rebuild --full`)
- [ ] Disaster recovery test (restore from backup, verify hash chain)
- [ ] Capacity planning (storage growth, GPU utilization trends)
- [ ] **Billing export**: `python -m engine.quota_ledger export_billing --month $(date -d 'last month' +%Y-%m) --output /var/log/soc/billing_$(date -d 'last month' +%Y-%m).json`

---

## 11. Emergency Procedures

### 11.1 Full Pipeline Stop

```bash
systemctl stop soc-intake-wazuh soc-intake-eve soc-triage-worker@* soc-enrichment-scheduler
# Drain queues
python -m engine.queue_manager drain --timeout 300
```

### 11.2 Model Rollback

```bash
# List available adapters
python -m orchestrator.model_registry list --status promoted

# Rollback to previous
python -m orchestrator.model_registry promote --adapter-id mistral-7b-lora-v11.8 --force
```

### 11.3 Data Recovery

```bash
# Restore PostgreSQL from backup
pg_restore -U soc_admin -d local_soc /backups/soc_20250114_0200.dump

# Restore FAISS index
tar -xzf /backups/faiss_index_20250114.tar.gz -C /var/lib/soc/embeddings/

# Verify hash chain after restore
python -m engine.hash_chain_sealer verify --full
```

---

## 12. Key File Paths Reference

| Purpose | Path |
|---------|------|
| Main config | `/opt/soc/config/` |
| Logs | `/var/log/soc/` |
| Data (Redis, FAISS, hash chain, fix_backlog.json) | `/var/lib/soc/` |
| Model weights/adapters | `/opt/soc/models/` |
| Backups | `/backups/soc/` |
| Virtual env | `/opt/soc/venv/` |
| Scripts | `/opt/soc/scripts/` |

---

## 13. Version-Specific Notes (v11.9)

- **Breaking**: `sanitization_pipeline.py` now requires `config/sanitization_rules.yaml` v2 schema (adds `pii_entity_types` field)
- **New**: `quota_ledger.py` tracks per-model token usage; integrate with billing via `quota_ledger.export_billing()`
- **Changed**: `hash_chain_sealer.py` seal interval reduced from 10k to 1k events for higher audit granularity
- **Added**: `overnight/` package with self-improving pipeline; enable via `systemctl enable soc-self-improver.timer`
- **Deprecated**: `engine/intake_syslog.py` removed; migrate to `intake_wazuh` or `intake_eve`

---

**Document Version**: 11.9.0  
**Last Updated**: 2025-01-15  
**Maintainer**: SOC Engineering Team  
**Classification**: INTERNAL - OPERATIONAL
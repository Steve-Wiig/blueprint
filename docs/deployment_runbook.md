# LOCAL-SOC-SLM Deployment Runbook v11.9

## 1. Prerequisites

### 1.1 System Requirements
- **OS**: Ubuntu 22.04 LTS or Debian 12 (Bookworm)
- **CPU**: 8+ cores (AVX2 support required for embedding inference)
- **RAM**: 32 GB minimum (64 GB recommended for pgvector HNSW indexes)
- **Storage**: 500 GB NVMe (OS + PostgreSQL) + 2 TB HDD (CMR mount for cold storage)
- **Network**: Static IP, outbound HTTPS for model provider APIs (OpenRouter, Ollama, local vLLM)

### 1.2 Required Packages (Pre-Install)
```bash
sudo apt-get update && sudo apt-get install -y \
  postgresql-16 postgresql-client-16 postgresql-16-pgvector \
  python3.11 python3.11-venv python3.11-dev \
  python3-psycopg2 \
  zstd zstdmt \
  nginx certbot python3-certbot-nginx \
  git curl jq htop iotop nvme-cli smartmontools \
  build-essential libpq-dev pkg-config \
  redis-server prometheus-node-exporter
```

### 1.3 Python Environment
```bash
python3.11 -m venv /opt/soc-slm/venv
source /opt/soc-slm/venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt  # Includes: psycopg2-binary, pgvector, numpy, torch, sentence-transformers, openai, httpx, pyyaml, prometheus-client, aiolimiter, pydantic
```

---

## 2. VM Setup

### 2.1 User & Directory Structure
```bash
sudo useradd -r -s /bin/bash -d /opt/soc-slm -m socslm
sudo mkdir -p /opt/soc-slm/{engine,orchestrator,memory,tools,overnight,config,logs,var/lib/postgresql,var/lib/redis}
sudo chown -R socslm:socslm /opt/soc-slm
# Ensure overnight directory is writable for self_improver.py fix_backlog.json writes
sudo chmod 755 /opt/soc-slm/overnight
```

### 2.2 Systemd Drop-ins (Resource Limits)
```bash
sudo mkdir -p /etc/systemd/system/{postgresql,redis,nginx}.service.d
cat <<'EOF' | sudo tee /etc/systemd/system/postgresql.service.d/override.conf
[Service]
LimitNOFILE=65536
LimitMEMLOCK=infinity
EOF
sudo systemctl daemon-reload
```

### 2.3 Kernel Tuning (pgvector HNSW)
```bash
cat <<'EOF' | sudo tee /etc/sysctl.d/99-soc-slm.conf
vm.max_map_count=262144
vm.swappiness=10
net.core.somaxconn=4096
net.ipv4.tcp_max_syn_backlog=8192
EOF
sudo sysctl --system
```

---

## 3. PostgreSQL with pgvector Installation

### 3.1 Cluster Initialization
```bash
sudo pg_createcluster 16 main --start -d /opt/soc-slm/var/lib/postgresql/16/main
sudo -u postgres psql -c "CREATE ROLE socslm WITH LOGIN PASSWORD 'changeme_in_prod';"
sudo -u postgres psql -c "CREATE DATABASE soc_slm OWNER socslm;"
sudo -u postgres psql -c "CREATE DATABASE soc_slm_audit OWNER socslm;"
```

### 3.2 pgvector Extension & Tuning
```bash
sudo -u postgres psql -d soc_slm -c "CREATE EXTENSION IF NOT EXISTS vector;"
sudo -u postgres psql -d soc_slm -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
sudo -u postgres psql -d soc_slm -c "CREATE EXTENSION IF NOT EXISTS btree_gin;"
# Required for shared_preload_libraries = 'pg_stat_statements,auto_explain'
sudo -u postgres psql -d soc_slm -c "CREATE EXTENSION IF NOT EXISTS pg_stat_statements;"
sudo -u postgres psql -d soc_slm -c "CREATE EXTENSION IF NOT EXISTS auto_explain;"

cat <<'EOF' | sudo tee /etc/postgresql/16/main/conf.d/99-soc-slm.conf
shared_buffers = 8GB
effective_cache_size = 24GB
maintenance_work_mem = 2GB
work_mem = 256MB
max_parallel_workers_per_gather = 4
max_parallel_maintenance_workers = 4
random_page_cost = 1.1
effective_io_concurrency = 200
wal_buffers = 64MB
min_wal_size = 2GB
max_wal_size = 8GB
checkpoint_completion_target = 0.9
max_connections = 200
shared_preload_libraries = 'pg_stat_statements,auto_explain'
auto_explain.log_min_duration = 1000
auto_explain.log_analyze = on
EOF
sudo systemctl restart postgresql@16-main
```

### 3.3 Verify pgvector
```bash
sudo -u postgres psql -d soc_slm -c "SELECT extname, extversion FROM pg_extension WHERE extname='vector';"
# Expected: vector | 0.7.0+
```

---

## 4. zstd Setup (Multi-threaded Compression)

### 4.1 Install zstdmt (if not in distro)
```bash
# Ubuntu 22.04 includes zstdmt via zstd package
zstd --version  # Verify 1.5.5+
```

### 4.2 Compression Profiles (Used by `engine/hash_chain_sealer.py`)
```bash
cat <<'EOF' | sudo tee /opt/soc-slm/config/zstd_profiles.yaml
profiles:
  hot:
    level: 3
    threads: 2
    window_log: 24
  warm:
    level: 9
    threads: 2
    window_log: 27
  cold:
    level: 19
    threads: 1
    window_log: 30
    long_distance_matching: true
EOF
```
> **Note**: Thread counts reduced to 2 to align with `CPUQuota=200%` (2 cores) on engine services, avoiding context-switch contention.

---

## 5. CMR HDD Mount (Cold Storage Tier)

### 5.1 Identify & Format
```bash
lsblk -o NAME,SIZE,TYPE,MODEL,SERIAL,TRAN  # Identify CMR HDD (e.g., /dev/sdb)
sudo mkfs.ext4 -L soc-cold -m 1 -E lazy_itable_init=1,lazy_journal_init=1 /dev/sdb
```

### 5.2 Mount with noatime & discard
```bash
sudo mkdir -p /mnt/cold
echo "LABEL=soc-cold /mnt/cold ext4 defaults,noatime,discard,commit=60 0 2" | sudo tee -a /etc/fstab
sudo mount -a
sudo chown socslm:socslm /mnt/cold
sudo -u socslm mkdir -p /mnt/cold/{archives,backups,vector_offload}
```

### 5.3 Verify SMART Health
```bash
sudo smartctl -a /dev/sdb | grep -E '(SMART overall|Reallocated_Sector|Current_Pending|Offline_Uncorrectable)'
```

---

## 6. Database Schema Migration (memory/schema/*.sql)

### 6.1 Migration Order (Dependency-Aware)
```bash
cd /opt/soc-slm
# Use .pgpass for security instead of PGPASSWORD env var
sudo -u socslm cp /opt/soc-slm/.pgpass ~/.pgpass && chmod 600 ~/.pgpass
sudo -u socslm psql -h localhost -U socslm -d soc_slm -f memory/schema/00_extensions.sql
sudo -u socslm psql -h localhost -U socslm -d soc_slm -f memory/schema/01_embeddings.sql
sudo -u socslm psql -h localhost -U socslm -d soc_slm -f memory/schema/02_retention_policies.sql
sudo -u socslm psql -h localhost -U socslm -d soc_slm -f memory/schema/03_rag_indexes.sql
sudo -u socslm psql -h localhost -U socslm -d soc_slm -f memory/schema/04_audit_tables.sql
sudo -u socslm psql -h localhost -U socslm -d soc_slm -f memory/schema/05_quota_ledger.sql
sudo -u socslm psql -h localhost -U socslm -d soc_slm -f memory/schema/06_hash_chain.sql
```

### 6.2 Required Content for `memory/schema/00_extensions.sql`
```sql
-- memory/schema/00_extensions.sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gin;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

CREATE SCHEMA IF NOT EXISTS memory;
GRANT ALL ON SCHEMA memory TO socslm;
ALTER DEFAULT PRIVILEGES IN SCHEMA memory GRANT ALL ON TABLES TO socslm;
ALTER DEFAULT PRIVILEGES IN SCHEMA memory GRANT ALL ON SEQUENCES TO socslm;
```

### 6.3 Verify Migration
```bash
sudo -u socslm psql -h localhost -U socslm -d soc_slm -c "\dt memory.*"
# Expected tables: embeddings, retention_policies, rag_chunks, audit_events, quota_ledger, hash_chain
```

### 6.4 Create HNSW Indexes (Post-Load)
```bash
sudo -u socslm psql -h localhost -U socslm -d soc_slm -c "
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_embeddings_vector_hnsw
ON memory.embeddings USING hnsw (vector vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
"
```
> **Note**: `maintenance_work_mem = 2GB` (set in 3.2) is sufficient for HNSW build on datasets up to ~50M vectors. Monitor for OOM if scaling beyond.

---

## 7. Config File Placement

### 7.1 Main Configuration (`/opt/soc-slm/config/production.yaml`)
```yaml
# /opt/soc-slm/config/production.yaml
database:
  host: "localhost"
  port: 5432
  name: "soc_slm"
  user: "socslm"
  password: "${DB_PASSWORD}"
  pool_size: 20
  max_overflow: 10

redis:
  host: "localhost"
  port: 6379
  db: 0
  max_connections: 50

engine:
  intake_wazuh:
    listen_port: 5140
    batch_size: 500
    flush_interval_ms: 100
  sanitization_pipeline:
    pii_patterns_file: "config/pii_patterns.yaml"
    max_event_size_mb: 10
  slm_triage_worker:
    model: "local-slm-v11.9"
    batch_size: 32
    timeout_seconds: 30
  quota_ledger:
    daily_limit: 100000
    burst_limit: 5000
    provider: "openrouter"
  queue_manager:
    max_queue_size: 100000
    persistence: "redis"
  enrichment_scheduler:
    interval_seconds: 300
    ioc_sources: ["abuse.ch", "otx", "misp"]
  ioc_extractor:
    enable_yara: true
    yara_rules_path: "config/yara/"
  intake_eve:
    listen_port: 5141
    json_only: true
  hash_chain_sealer:
    interval_seconds: 60
    zstd_profile: "warm"
    cold_storage_path: "/mnt/cold/archives"

orchestrator:
  context_stitcher:
    max_context_tokens: 8192
    embedding_model: "bge-large-en-v1.5"
  model_registry:
    providers:
      - name: "openrouter"
        api_key: "${OPENROUTER_API_KEY}"
        models: ["anthropic/claude-3.5-sonnet", "meta-llama/llama-3.1-70b"]
        fallback_order: 1
      - name: "ollama"
        base_url: "http://localhost:11434"
        models: ["llama3.1:70b", "qwen2.5:72b"]
        fallback_order: 2
      - name: "vllm"
        base_url: "http://localhost:8000"
        models: ["local-slm-v11.9"]
        fallback_order: 3

memory:
  embeddings:
    model: "BAAI/bge-large-en-v1.5"
    device: "cuda"
    batch_size: 64
    dimension: 1024
  retention:
    hot_days: 7
    warm_days: 90
    cold_days: 2555
    archive_path: "/mnt/cold/vector_offload"

overnight:
  self_improver:
    enabled: true
    schedule_cron: "0 2 * * *"
    max_iterations: 5
    fix_backlog_path: "overnight/fix_backlog.json"
    llm_client:
      rate_limit_rpm: 60
      rate_limit_tpm: 100000
      circuit_breaker_threshold: 5
      circuit_breaker_timeout: 300
    openrouter_quota:
      daily_limit: 500000
      warning_threshold: 0.8

logging:
  level: "INFO"
  format: "json"
  output: "/opt/soc-slm/logs/soc-slm.log"
  rotation: "daily"
  retention_days: 30

metrics:
  prometheus_port: 9090
  pushgateway: "http://localhost:9091"
```

### 7.2 Environment File (`/opt/soc-slm/.env.production`)
```bash
cat <<'EOF' > /opt/soc-slm/.env.production
DB_PASSWORD="changeme_in_prod"
OPENROUTER_API_KEY="sk-or-v1-..."
REDIS_PASSWORD=""
GRAFANA_ADMIN_PASSWORD="changeme"
EOF
chmod 600 /opt/soc-slm/.env.production
chown socslm:socslm /opt/soc-slm/.env.production
```

### 7.3 PostgreSQL Password File (`/opt/soc-slm/.pgpass`)
```bash
cat <<'EOF' > /opt/soc-slm/.pgpass
localhost:5432:soc_slm:socslm:changeme_in_prod
localhost:5432:soc_slm_audit:socslm:changeme_in_prod
EOF
chmod 600 /opt/soc-slm/.pgpass
chown socslm:socslm /opt/soc-slm/.pgpass
```

### 7.4 PII Patterns (`/opt/soc-slm/config/pii_patterns.yaml`)
```yaml
patterns:
  - name: "ipv4"
    regex: "\\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\\b"
    replacement: "[IP_REDACTED]"
  - name: "email"
    regex: "\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Z|a-z]{2,}\\b"
    replacement: "[EMAIL_REDACTED]"
  - name: "credit_card"
    regex: "\\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|3(?:0[0-5]|[68][0-9])[0-9]{11}|6(?:011|5[0-9]{2})[0-9]{12})\\b"
    replacement: "[CC_REDACTED]"
```

### 7.5 Log Rotation (`/etc/logrotate.d/soc-slm`)
```bash
cat <<'EOF' | sudo tee /etc/logrotate.d/soc-slm
/opt/soc-slm/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0640 socslm socslm
    sharedscripts
    postrotate
        systemctl reload soc-slm-engine@intake_wazuh > /dev/null 2>&1 || true
        systemctl reload soc-slm-engine@intake_eve > /dev/null 2>&1 || true
    endscript
}
EOF
```

---

## 8. Service Startup Order (systemd Units)

### 8.1 Create Service Files
```bash
# /etc/systemd/system/soc-slm-engine@.service
cat <<'EOF' | sudo tee /etc/systemd/system/soc-slm-engine@.service
[Unit]
Description=SOC SLM Engine - %i
After=network.target postgresql@16-main.service redis.service
Requires=postgresql@16-main.service redis.service

[Service]
Type=exec
User=socslm
Group=socslm
WorkingDirectory=/opt/soc-slm
EnvironmentFile=/opt/soc-slm/.env.production
ExecStart=/opt/soc-slm/venv/bin/python -m engine.%i
Restart=on-failure
RestartSec=5
StartLimitIntervalSec=60
StartLimitBurst=3
LimitNOFILE=65536
MemoryLimit=8G
CPUQuota=200%

[Install]
WantedBy=multi-user.target
EOF

# /etc/systemd/system/soc-slm-orchestrator@.service
cat <<'EOF' | sudo tee /etc/systemd/system/soc-slm-orchestrator@.service
[Unit]
Description=SOC SLM Orchestrator - %i
After=network.target soc-slm-engine@queue_manager.service
Requires=soc-slm-engine@queue_manager.service

[Service]
Type=exec
User=socslm
Group=socslm
WorkingDirectory=/opt/soc-slm
EnvironmentFile=/opt/soc-slm/.env.production
ExecStart=/opt/soc-slm/venv/bin/python -m orchestrator.%i
Restart=on-failure
RestartSec=5
LimitNOFILE=32768
MemoryLimit=4G

[Install]
WantedBy=multi-user.target
EOF

# /etc/systemd/system/soc-slm-memory@.service
cat <<'EOF' | sudo tee /etc/systemd/system/soc-slm-memory@.service
[Unit]
Description=SOC SLM Memory - %i
After=network.target postgresql@16-main.service
Requires=postgresql@16-main.service

[Service]
Type=exec
User=socslm
Group=socslm
WorkingDirectory=/opt/soc-slm
EnvironmentFile=/opt/soc-slm/.env.production
ExecStart=/opt/soc-slm/venv/bin/python -m memory.%i
Restart=on-failure
RestartSec=10
LimitNOFILE=32768
MemoryLimit=16G

[Install]
WantedBy=multi-user.target
EOF

# /etc/systemd/system/soc-slm-overnight.service
cat <<'EOF' | sudo tee /etc/systemd/system/soc-slm-overnight.service
[Unit]
Description=SOC SLM Overnight Self-Improving Pipeline
After=network.target postgresql@16-main.service redis.service
Requires=postgresql@16-main.service redis.service

[Service]
Type=oneshot
User=socslm
Group=socslm
WorkingDirectory=/opt/soc-slm
EnvironmentFile=/opt/soc-slm/.env.production
ExecStart=/opt/soc-slm/venv/bin/python -m overnight.self_improver
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# /etc/systemd/system/soc-slm-overnight.timer
cat <<'EOF' | sudo tee /etc/systemd/system/soc-slm-overnight.timer
[Unit]
Description=Run overnight self-improver daily at 02:00

[Timer]
OnCalendar=*-*-* 02:00:00
Persistent=true
RandomizedDelaySec=15m

[Install]
WantedBy=timers.target
EOF
```

### 8.2 Enable & Start in Order
```bash
sudo systemctl daemon-reload

# Phase 1: Infrastructure (Redis MUST be active before engine services)
sudo systemctl enable --now postgresql@16-main redis nginx
sudo systemctl is-active --quiet redis || { echo "Redis failed to start"; exit 1; }

# Phase 2: Engine (dependency order matters)
sudo systemctl enable --now soc-slm-engine@queue_manager
sudo systemctl enable --now soc-slm-engine@quota_ledger
sudo systemctl enable --now soc-slm-engine@intake_wazuh
sudo systemctl enable --now soc-slm-engine@intake_eve
sudo systemctl enable --now soc-slm-engine@sanitization_pipeline
sudo systemctl enable --now soc-slm-engine@ioc_extractor
sudo systemctl enable --now soc-slm-engine@enrichment_scheduler
sudo systemctl enable --now soc-slm-engine@slm_triage_worker
sudo systemctl enable --now soc-slm-engine@hash_chain_sealer

# Phase 3: Orchestrator
sudo systemctl enable --now soc-slm-orchestrator@context_stitcher
sudo systemctl enable --now soc-slm-orchestrator@model_registry

# Phase 4: Memory
sudo systemctl enable --now soc-slm-memory@embeddings
sudo systemctl enable --now soc-slm-memory@retention

# Phase 5: Overnight Pipeline (v11.9)
sudo systemctl enable --now soc-slm-overnight.timer

# Verify all active
systemctl list-units 'soc-slm-*' --state=active
```

---

## 9. Smoke Tests (tools/*_check.py)

### 9.1 Run All Health Checks
```bash
cd /opt/soc-slm
source venv/bin/activate

# Database connectivity & pgvector
python tools/db_check.py --dsn "postgresql://socslm:${DB_PASSWORD}@localhost:5432/soc_slm" --test-vector

# Redis connectivity
python tools/redis_check.py --host localhost --port 6379

# Engine modules
python tools/engine_check.py --module intake_wazuh --port 5140
python tools/engine_check.py --module intake_eve --port 5141
python tools/engine_check.py --module sanitization_pipeline --test-pii
python tools/engine_check.py --module slm_triage_worker --model local-slm-v11.9
python tools/engine_check.py --module quota_ledger --provider openrouter
python tools/engine_check.py --module queue_manager --depth-check
python tools/engine_check.py --module enrichment_scheduler --test-ioc
python tools/engine_check.py --module ioc_extractor --test-yara
python tools/engine_check.py --module hash_chain_sealer --verify-chain

# Orchestrator modules
python tools/orchestrator_check.py --module context_stitcher --test-embedding
python tools/orchestrator_check.py --module model_registry --test-fallback

# Memory modules
python tools/memory_check.py --module embeddings --model BAAI/bge-large-en-v1.5 --dim 1024
python tools/memory_check.py --module retention --test-policy

# Overnight pipeline (v11.9)
python tools/overnight_check.py --module self_improver --dry-run
python tools/overnight_check.py --module llm_client --test-fallback --test-rate-limit
python tools/overnight_check.py --module openrouter_quota --check-daily
python tools/overnight_check.py --module fix_backlog --validate-json
```

### 9.2 Expected Smoke Test Output
```
[PASS] db_check: Connection OK, pgvector 0.7.0, HNSW index exists
[PASS] redis_check: PING OK, 50/50 connections available
[PASS] engine_check:intake_wazuh: Listening on 0.0.0.0:5140
[PASS] engine_check:intake_eve: Listening on 0.0.0.0:5141
[PASS] engine_check:sanitization_pipeline: PII redaction functional (5/5 patterns)
[PASS] engine_check:slm_triage_worker: Model loaded, inference <500ms
[PASS] engine_check:quota_ledger: OpenRouter quota 487,231/500,000 remaining
[PASS] engine_check:queue_manager: Depth 0/100000, Redis backend healthy
[PASS] engine_check:enrichment_scheduler: 3 IOC sources configured
[PASS] engine_check:ioc_extractor: YARA rules loaded (247 rules)
[PASS] engine_check:hash_chain_sealer: Chain verified, last seal 2025-01-15T02:00:00Z
[PASS] orchestrator_check:context_stitcher: Embedding dim 1024, context window 8192
[PASS] orchestrator_check:model_registry: 3 providers, fallback chain verified
[PASS] memory_check:embeddings: Model loaded on CUDA, batch 64 OK
[PASS] memory_check:retention: Policies active (hot:7d, warm:90d, cold:2555d)
[PASS] overnight_check:self_improver: Dry-run completed, 0 fixes generated
[PASS] overnight_check:llm_client: Fallback chain OpenRouter->Ollama->vLLM tested
[PASS] overnight_check:llm_client: Rate limit 60 RPM / 100k TPM enforced
[PASS] overnight_check:openrouter_quota: Daily 500k, current 2.3%, warning at 80%
[PASS] overnight_check:fix_backlog: JSON valid, 12 pending fixes
```

---

## 10. Spike Validation (R-001 through R-117)

### 10.1 Validation Script
```bash
cd /opt/soc-slm
python tools/spike_validator.py --requirements docs/requirements_spike_v11.9.yaml --output spike_report.json
```

### 10.2 Key Spike Requirements (Subset)
| ID | Requirement | Validation Method |
|----|-------------|-------------------|
| R-001 | Wazuh JSON intake at 10k EPS | `tools/load_test.py --module intake_wazuh --rate 10000 --duration 60` |
| R-002 | Eve JSON intake at 5k EPS | `tools/load_test.py --module intake_eve --rate 5000 --duration 60` |
| R-003 | PII redaction <5ms/event | `tools/latency_check.py --module sanitization_pipeline --p99 5` |
| R-004 | SLM triage <30s p99 | `tools/latency_check.py --module slm_triage_worker --p99 30000` |
| R-005 | Quota ledger accuracy ±0.1% | `tools/quota_check.py --precision 0.001` |
| R-006 | Queue persistence survive restart | `tools/chaos_test.py --kill queue_manager --verify-depth` |
| R-007 | Enrichment adds ≥3 IOC fields | `tools/enrichment_check.py --min-fields 3` |
| R-008 | IOC extraction recall >95% | `tools/ioc_recall_test.py --dataset mitre-attack --threshold 0.95` |
| R-009 | Hash chain immutability | `tools/hash_chain_verify.py --tamper-test` |
| R-010 | Context stitcher token budget | `tools/context_check.py --max-tokens 8192 --verify-truncation` |
| R-011 | Model registry fallback <2s | `tools/fallback_latency.py --max-failover 2000` |
| R-012 | Embedding inference >1k/sec | `tools/embedding_throughput.py --target 1000` |
| R-013 | Retention policy execution | `tools/retention_dryrun.py --verify-deletion` |
| R-014 | pgvector HNSW recall@10 >0.9 | `tools/vector_recall.py --k 10 --threshold 0.9` |
| R-015 | Cold storage offload >100MB/s | `tools/cold_offload_bench.py --target 100` |
| R-016 | zstd compression ratio >3:1 | `tools/compression_ratio.py --profile warm --min-ratio 3` |
| R-017 | Overnight pipeline completes <4h | `tools/overnight_timing.py --max-hours 4` |
| R-018 | Self-improver generates valid patches | `tools/patch_validator.py --syntax-check --test-apply` |
| R-019 | LLM client multi-provider fallback | `tools/llm_fallback_test.py --providers 3 --verify-order` |
| R-020 | Rate limit enforcement (RPM/TPM) | `tools/rate_limit_test.py --rpm 60 --tpm 100000` |
| R-021 | Circuit breaker activation | `tools/circuit_breaker_test.py --threshold 5 --timeout 300` |
| R-022 | OpenRouter quota tracking | `tools/quota_tracking_test.py --daily-limit 500000` |
| R-023 | Fix backlog JSON schema valid | `tools/json_schema_check.py --schema overnight/fix_backlog.schema.json` |
| R-024 | End-to-end alert to ticket <60s | `tools/e2e_latency.py --p99 60000` |
| R-025 | High availability (single node) | `tools/ha_check.py --single-node --mttr 300` |

### 10.3 Full Validation Command
```bash
# Run all 117 spike validations (takes ~45 minutes)
python tools/spike_validator.py \
  --requirements docs/requirements_spike_v11.9.yaml \
  --parallel 4 \
  --timeout 3600 \
  --output /opt/soc-slm/logs/spike_validation_$(date +%Y%m%d_%H%M%S).json \
  --junit /opt/soc-slm/logs/spike_validation_$(date +%Y%m%d_%H%M%S).xml
```

### 10.4 Acceptance Criteria
- **All 117 spikes must PASS** for production deployment
- Any FAIL blocks deployment; investigate via `spike_report.json`
- Re-run failed spikes individually: `python tools/spike_validator.py --only R-042`

---

## 11. v11.9 Overnight Self-Improving Pipeline

### 11.1 Pipeline Components
```
overnight/
├── self_improver.py          # Main orchestrator
├── llm_client.py             # Multi-provider LLM client with fallback & rate limiting
├── openrouter_quota.py       # Quota tracking & alerting
├── fix_backlog.json          # Persistent backlog of code fixes
├── fix_backlog.schema.json   # JSON schema validation
└── patches/                  # Generated patch files (git apply compatible)
```

### 11.2 self_improver.py Flow
```python
# Simplified flow in overnight/self_improver.py
async def run_pipeline():
    # 1. Load fix_backlog.json
    backlog = load_backlog("overnight/fix_backlog.json")
    
    # 2. Analyze production metrics (error rates, latency, quota usage)
    metrics = await collect_metrics(prometheus_url="http://localhost:9090")
    
    # 3. Generate improvement hypotheses via LLM
    hypotheses = await llm_client.generate_hypotheses(
        metrics=metrics,
        codebase_context=get_codebase_context(),
        max_iterations=config.max_iterations
    )
    
    # 4. Validate hypotheses (syntax, tests, security)
    validated = await validate_hypotheses(hypotheses)
    
    # 5. Create patches & append to backlog
    for fix in validated:
        patch = create_patch(fix)
        backlog.append({"patch": patch, "timestamp": utcnow(), "status": "pending"})
    
    # 6. Save updated backlog
    save_backlog(backlog, "overnight/fix_backlog.json")
    
    # 7. Emit metrics
    push_metrics({"fixes_generated": len(validated), "backlog_size": len(backlog)})
```

### 11.3 llm_client.py Multi-Provider Fallback with Circuit Breaker Persistence
```python
# overnight/llm_client.py - Complete implementation
import asyncio
import time
import json
import redis.asyncio as redis
from aiolimiter import AsyncLimiter
from dataclasses import dataclass
from typing import Optional, List
from

## Recent Architectural Updates (v11.9.x)

### Environment Variables
The `TriageQueueManager` is now fully configurable via environment variables. If not provided, it falls back to safe defaults:
- `QUEUE_LEASE_INTERVAL`: Lease duration in seconds (default: `900`)
- `QUEUE_MAX_ATTEMPTS`: Max retry attempts before marking failed (default: `3`)
- `QUEUE_EMERGENCY_DEPTH`: Backpressure threshold for low-priority jobs (default: `1000`)
- `RETENTION_DAYS`: Days to retain partition data before archiving (default: `90`)

### Optional Dependencies
- **`psycopg2`** (or `psycopg2-binary`) is now an **optional** dependency. It is only required if you are actively using PostgreSQL features (e.g., `enrichment_scheduler.py` or `retention.py`). The codebase will load and run in SQLite-only environments without it.

### Schema Management
- The database initialization schema has been extracted from Python code into `engine/schema.sql` for better version control and readability.

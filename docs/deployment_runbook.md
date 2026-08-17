# LOCAL-SOC-SLM Blueprint v11.6.0 Deployment Runbook

## 1. Prerequisites
- Hardware: NVIDIA GPU (16GB VRAM min), 64GB DDR5 RAM (96GB preferred).
- OS: Ubuntu 22.04 LTS / 24.04 LTS (Kernel 6.x).
- Dependencies: `build-essential`, `python3-pip`, `git`, `zstd`, `postgresql-16`, `postgresql-16-pgvector`.

## 2. VM Setup
- Provision VM with dedicated NVMe storage for OS/PostgreSQL.
- Configure secondary CMR HDD (Cold Metadata Repository) for long-term telemetry.
- Ensure non-root user with sudo privileges for service execution.

## 3. PostgreSQL & pgvector Installation
- Install PostgreSQL 16: `sudo apt install postgresql-16 postgresql-16-pgvector`.
- Initialize database cluster: `sudo -u postgres /usr/lib/postgresql/16/bin/initdb -D /var/lib/postgresql/16/main`.
- Enable extension: `CREATE EXTENSION IF NOT EXISTS vector;`.
- Configure `postgresql.conf` for 768-dimensional embedding performance.

## 4. Zstd & CMR HDD Setup
- Install zstd: `sudo apt install zstd`.
- Mount CMR HDD: `sudo mount /dev/sdb1 /mnt/cmr_archive`.
- Configure fstab for persistent mounting at boot.
- Set directory permissions: `chown -R soc_user:soc_user /mnt/cmr_archive`.

## 5. Database Schema Migration
- Navigate to `memory/schema/`.
- Execute migration scripts in order:
  1. `001_init_tables.sql`
  2. `002_vector_indices.sql`
  3. `003_partitioning.sql`
- Verify schema integrity: `psql -d soc_db -f verify_schema.sql`.

## 6. Configuration Placement
- Copy `config/slm_config.yaml` to `/etc/soc-slm/`.
- Set environment variables in `/etc/environment` for `MODEL_PATH`, `DB_URL`, and `API_KEYS`.
- Ensure restricted file permissions: `chmod 600 /etc/soc-slm/slm_config.yaml`.

## 7. Service Startup Order
1. Start PostgreSQL: `systemctl start postgresql`.
2. Start Embedding Engine: `systemctl start soc-embedder`.
3. Start Orchestration Engine: `systemctl start soc-orchestrator`.
4. Start Ingestion Pipeline: `systemctl start soc-ingest`.

## 8. Smoke Tests
- Run `python3 tools/db_check.py` to verify connectivity and vector support.
- Run `python3 tools/model_check.py` to verify nomic-embed-text loading.
- Run `python3 tools/api_check.py` to verify integration with Wazuh/TheHive.

## 9. Spike Validation (R-001 through R-117)
- Execute `python3 tools/validate_spikes.py --range 001-117`.
- Verify R-001 (GPU VRAM allocation) matches 16GB baseline.
- Verify R-042 (pgvector HNSW index) recall latency < 50ms.
- Verify R-117 (Atomic Rollback) triggers successfully on simulated failure.
- Log all validation results to `/var/log/soc-slm/validation.log`.

## 10. Final Readiness
- Confirm append-only table constraints.
- Verify partition pruning logic for CMR HDD.
- Finalize documentation and commit to internal repository.
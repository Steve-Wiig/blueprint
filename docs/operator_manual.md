# LOCAL-SOC-SLM Blueprint v11.6.0 Operator Manual

## 1. System Overview
The LOCAL-SOC-SLM is a hardened, local-first security orchestration and inference engine. It is designed to ingest telemetry from Wazuh, Security Onion, Suricata, TheHive, and pfSense, process it via a local LLM, and store orchestration state in PostgreSQL. The system prioritizes data integrity through append-only logs and hash-chain verification.

## 2. Hardware Requirements (Section 28)
The system requires specific hardware configurations to maintain stability during inference and ingestion phases:
- GPU: Single NVIDIA GPU with 16GB VRAM (Primary baseline).
- RAM: 64GB DDR5 minimum for serialized operation; 96GB DDR5 preferred for concurrent operation.
- Storage: High-speed NVMe for active PostgreSQL/SQLite databases; CMR HDD for long-term telemetry archives.
- Memory Upgrades: Must use matched-kit replacements only to prevent bus instability.

## 3. Database Setup
The system utilizes a dual-database architecture:
- PostgreSQL: Stores orchestration state and long-term memory. Requires `pgvector` extension for 768-dimensional embeddings.
- SQLite: Stores ephemeral working state and triage queues.
- Initialization: Run `scripts/db_init.sh`.
- Exit Codes: 0 (Success), 2 (Config Error - check `db_conn.conf`).

## 4. Running Intake Adapters
Intake adapters decouple raw telemetry from the inference engine.
- Command: `python3 adapters/intake_manager.py --start`
- Adapters must be cryptographically signed. Unsigned adapters will be rejected by the loader.
- Monitoring: Check `logs/intake.log` for ingestion throughput.
- Exit Codes: 0 (Running), 1 (Adapter Failure), 3 (Dependency Missing).

## 5. Monitoring the Triage Queue
The triage queue holds events awaiting semantic analysis.
- Tool: `scripts/monitor_queue.sh`
- The queue is stored in SQLite. If the queue depth exceeds 5000 items, verify GPU VRAM availability.
- High-entropy unknown tokens are automatically quarantined to `data/quarantine/`.

## 6. Running Retention Cron
Retention is managed via time-partitioned pruning.
- Command: `crontab -e` -> Add `0 2 * * * /opt/soc/scripts/retention_prune.sh`
- Process: Archives data to CMR HDD, then drops PostgreSQL partitions.
- Integrity: Ensure `archive_verify.sh` runs post-pruning to confirm data persistence.

## 7. Checking Hash-Chain Integrity
Every handoff and correction is recorded in an append-only hash chain.
- Command: `python3 tools/verify_chain.py --check`
- This script validates the cryptographic link between all state transitions.
- If the chain is broken, the system enters a "Read-Only" safety state.
- Exit Codes: 0 (Chain Valid), 1 (Integrity Violation - Manual Audit Required).

## 8. Troubleshooting Common Failures
- VRAM Exhaustion: If inference fails, check `nvidia-smi`. Reduce batch size in `config/inference.yaml`.
- API Connectivity: If pfSense/Wazuh integration fails, verify API keys in `secrets/`. Ensure `LAB-VERIFY` dependencies are met as per Section 32.2.
- Embedding Mismatch: Ensure `nomic-embed-text` is correctly loaded. Check `logs/embedding_engine.log`.
- Database Lock: If SQLite is locked, run `scripts/db_repair.sh` to clear stale journal files.

## 9. Operational Constraints
- Autonomous online tuning is strictly prohibited.
- All model promotions require a replay-mix evaluation followed by a canary deployment.
- Rollbacks must be executed via `scripts/rollback.sh` for atomic state restoration.
- Wiki and documentation updates must be sanitized and committed via the append-only pipeline.

## 10. Emergency Procedures
- In the event of a detected breach of the hash-chain, execute `scripts/emergency_freeze.sh`.
- This script halts all intake adapters and locks the PostgreSQL database to prevent further state mutation.
- Restore from the last verified snapshot using `scripts/restore_snapshot.sh`.
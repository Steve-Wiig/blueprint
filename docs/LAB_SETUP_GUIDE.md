# LOCAL-SOC-SLM Lab Setup Guide

## 1. Hardware Requirements

To ensure stable performance for the LOCAL-SOC-SLM stack, the following minimum specifications are required:

*   **CPU:** 8 vCPUs (Minimum) - Required for concurrent processing of `slm_triage_worker` and embedding generation.
*   **RAM:** 32 GB DDR4/DDR5 - High memory overhead is required for the `memory/` module (pgvector) and the SLM inference engine.
*   **Storage:** 200 GB NVMe SSD - High IOPS are critical for `intake_wazuh` logs and `queue_manager` persistence.
*   **Network:** 1 Gbps NIC - Dedicated interface for traffic mirroring to `intake_eve`.

## 2. Docker Compose Stack

The following `docker-compose.yml` defines the core infrastructure. Ensure you have a `.env` file configured with `POSTGRES_PASSWORD` and `WAZUH_API_KEY`.

```yaml
version: '3.8'
services:
  wazuh:
    image: wazuh/wazuh-manager:latest
    ports:
      - "1514:1514"
      - "55000:55000"
    volumes:
      - wazuh_data:/var/ossec/data

  suricata:
    image: jasonish/suricata:latest
    network_mode: host
    cap_add:
      - NET_ADMIN
      - NET_RAW
    volumes:
      - ./suricata/rules:/var/lib/suricata/rules

  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: soc_memory
      POSTGRES_USER: soc_admin
    ports:
      - "5432:5432"
    volumes:
      - pg_data:/var/lib/postgresql/data

  thehive:
    image: strangebee/thehive:latest
    depends_on:
      - postgres

  engine-worker:
    build: ./engine
    environment:
      - QUEUE_MANAGER_URL=redis://queue:6379
      - MEMORY_DB_URL=postgresql://soc_admin@postgres:5432/soc_memory
    depends_on:
      - postgres

volumes:
  wazuh_data:
  pg_data:
```

## 3. Network Topology and Port Mappings

The platform operates on a segmented internal network:

| Service | Port | Purpose |
| :--- | :--- | :--- |
| `intake_wazuh` | 1514 | Wazuh agent communication |
| `intake_eve` | 9200 | Suricata EVE JSON ingestion |
| `orchestrator` | 8080 | Model routing and API gateway |
| `memory` | 5432 | Vector database (pgvector) |
| `thehive` | 9000 | Case management dashboard |

**Traffic Flow:**
1. Raw logs arrive at `intake_wazuh` or `intake_eve`.
2. `sanitization_pipeline` cleans the data.
3. `queue_manager` buffers events for the `slm_triage_worker`.
4. `context_stitcher` queries `memory/` for historical context.
5. `slm_triage_worker` generates triage decisions.

## 4. Initial Configuration Steps

### Step 1: Environment Setup
Create the `.env` file in the project root:
```bash
POSTGRES_PASSWORD=secure_random_string
SLM_API_KEY=your_local_llm_key
WAZUH_MANAGER_IP=127.0.0.1
```

### Step 2: Database Initialization
Initialize the vector extensions in PostgreSQL:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE embeddings (
    id uuid PRIMARY KEY,
    content text,
    embedding vector(1536),
    metadata jsonb
);
```

### Step 3: Module Activation
Ensure the `engine/` modules are registered in the `orchestrator/model_registry`:
1. Navigate to `orchestrator/`.
2. Run `python3 -m model_registry --init`.
3. Verify `hash_chain_sealer` is active to ensure log integrity.

## 5. Verification Checklist

- [ ] **Connectivity:** Can `engine/intake_wazuh` reach the Wazuh API on port 55000?
- [ ] **Queueing:** Does `queue_manager` show active consumers in the logs?
- [ ] **Memory:** Run `SELECT count(*) FROM embeddings;` in `postgres` to verify `memory/retention` is writing data.
- [ ] **Enrichment:** Trigger a test alert and verify `ioc_extractor` populates the `metadata` field in the database.
- [ ] **Orchestration:** Check `orchestrator/context_stitcher` logs to ensure historical data is being retrieved for new alerts.
- [ ] **Triage:** Confirm `slm_triage_worker` is receiving payloads from the queue and returning a classification.
- [ ] **Integrity:** Verify `hash_chain_sealer` is generating valid hashes for incoming log batches.

## Troubleshooting
- **Memory Errors:** If `slm_triage_worker` fails, increase the `shm-size` in `docker-compose.yml`.
- **Latency:** If `enrichment_scheduler` lags, verify the connection to the external threat intel feeds.
- **Logs:** All logs are centralized. Use `docker compose logs -f [service_name]` to debug specific modules.
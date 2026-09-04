SOURCE: soc-autopilot (historical)
BLOCK:  v11.3 AMENDMENTS TO PRESERVED TEXT
SHA256: 4d6ce1090af836ca
────────────────────────────────────────────────────────────────────────

AMEND-1 — Section 20.0, Goals
ADD bullet:
- Produce an open-source enrichment engine ("glue" layer) that integrates Wazuh,
Security Onion, Suricata, TheHive, and pfSense so the combined system provides
continuous enrichment and triage support even when no analyst is present
(Section 26).
AMEND-2 — Sections 23.1, 25.2, 25.6, Appendix C, Appendix D — RAM policy
23.1 RAM:
REPLACE bullets with:
- 64GB minimum; approved as the v1 lab starting configuration when operated in
serialized phases per Section 28.
- 96GB recommended if running local SOC containers and training concurrently.
- Preferred stable configuration on consumer platforms: 2x48GB DDR5 for 96GB
total.
- RAM upgrades are performed by matched-kit REPLACEMENT, not addition.
25.6:
ADD:
- 64GB as a matched 2x32GB DDR5 kit is an approved v1 starting configuration
when the lab operates in serialized phases (Section 28).
- Upgrading to 96GB must replace the kit: retire/sell the 2x32GB kit and
install a matched 2x48GB kit. Adding a second kit to an existing kit is not
approved.
Appendix C RAM line:
REPLACE with:
"64GB DDR5 (2x32GB matched kit) approved v1 start;
96GB (2x48GB matched kit) preferred upgrade via kit replacement."
Appendix D memory block:
Set:
capacity_gb: 64
configuration: "2x32GB"
upgrade_policy: "replace-not-add; matched kits only; 2x48GB target"
AMEND-3 — Sections 23.2, 25.7 — dual-GPU framing
ADD:
- The GPU 1 inference role includes hosting the enrichment engine SLM worker
("analyst on shift"). GPU 0 remains the development bench (training, merge,
heavy eval). A second GPU grants sustained operational availability, NOT
increased autonomy; autonomy levels remain governed by 25.3 and the Section 24
contract.
AMEND-4 — Section 20.1 — schema optional fields
ADD optional fields:
- metadata.enrichment_status
Values: pending | partial | complete | quota_deferred
- metadata.enrichment_sources
List of provider ids.
- metadata.external_api_quota_id
- metadata.memory_context
List of past_case refs injected into the prompt.
- validation.enrichment_slo_pass
- validation.memory_injection_pass
ADD "pfsense" to allowed values of optional field `engine` for alias/blocklist
drafts.
AMEND-5 — Section 24.1 — tool categories
ADD:
read:
lookup_domain_reputation
lookup_url_reputation
query_thehive_observables
query_pfsense_tables
query_memory_similar_cases
query_memory_handoff_ledger
draft:
draft_pfsense_alias
draft_enrichment_summary
draft_earlier_alerting_rule
approval_required:
apply_pfsense_alias
push_blocklist
All pfSense-adjacent mutations remain approval-gated; the engine never applies
them autonomously.
AMEND-6 — Appendix G — repository skeleton
ADD:
├── engine/
│   ├── intake_wazuh.py
│   ├── intake_eve.py
│   ├── ioc_extractor.py
│   ├── enrichment_scheduler.py
│   ├── quota_ledger.py
│   ├── slm_triage_worker.py
│   └── writeback/
│       ├── thehive.py
│       ├── wazuh_proposals.py
│       ├── so_cases.py
│       └── pfsense_alias.py
├── lab/
│   ├── scenarios/
│   ├── targets.md
│   └── run_capture.sh
├── memory/
│   ├── schema/
│   │   └── orchestration_memory.sql
│   ├── adapters/
│   ├── embeddings.py
│   ├── retention.py
│   └── migration/
├── orchestrator/
│   ├── routing.yaml
│   ├── context_stitcher.py
│   └── model_registry.py
├── configs/
│   ├── enrichment_engine.v11.2.yaml
│   ├── orchestration_memory.v11.3.yaml
│   └── adapter_routing.v11.3.yaml
├── docs/
│   ├── enrichment-engine.md
│   ├── purple-team-lab.md
│   ├── serialized-lab-operations.md
│   ├── orchestration-memory.md
│   └── continual-learning.md
├── tools/
│   ├── external_credential_permission_check.py
│   ├── embedding_prefix_check.py
│   ├── embedding_prefix_idempotency_check.py
│   ├── sanitization_redaction_check.py
│   ├── sanitization_entropy_check.py
│   ├── sanitization_field_policy_check.py
│   ├── dynamic_vram_budget_check.py
│   ├── payload_ref_integrity_check.py
│   ├── hash_chain_verify.py
│   ├── hash_chain_concurrency_check.py
│   ├── queue_backpressure_check.py
│   ├── queue_stale_recovery_check.py
│   ├── vector_partition_index_check.py
│   ├── memory_schema_migrate_check.py
│   ├── changelog_completeness_check.py
│   └── wiki_sanitization_check.py
AMEND-7 — Section 26.1 — Enrichment Engine components
ADD bullet:
- Orchestration Memory client (30.1): the intake adapters, IOC extractor, and
scheduler share a single PostgreSQL connection pool and a per-process SQLite
quota ledger. Memory reads/writes are part of the fast path.
AMEND-8 — Section 29.1 — Orchestrator pattern
REPLACE with:
- PLAN.md holds goal/phase/decisions; SQLite task DB tracks task status, prompt,
code, test results, retries, commit hash.
- PostgreSQL is the orchestration's persistent memory (30.x): IOCs, handoffs,
investigations, corrections, model registry.
- The orchestrator stitches prompt context from memory using
query_memory_similar_cases, recent accepted corrections, and the
model_registry row for the active adapter, then writes every handoff back.
The model is a worker; the memory + harness compose.
AMEND-9 — Section 25.4 — Defense improvement pipeline, step 2
ADD:
- SLM proposal is produced in the context of the orchestrator memory: similar
past cases (pgvector top-k), related accepted corrections, linked
investigation state. This is retrieval-driven experience, not weight change
(31.2).
AMEND-10 — Section 21 — Signed adapter policy
ADD:
- Adapter promotion requires a replay-mix evaluation (31.5): the held-out test
set plus a replay sample of the golden evaluation set, to guard against
catastrophic forgetting. Promotion is atomic with instant rollback (31.6).
AMEND-11 — Appendix I — Enrichment Engine reference config
ADD keys:
memory:
postgres_dsn: "postgresql://engine@127.0.0.1:5432/local_soc_slm"
sqlite_quota_ledger: "engine/quota.db"
embedding_model: "nomic-embed-text"
embedding_dim: 768
similar_cases_top_k: 5
similar_cases_max_age_days: 90
AMEND-12 — Section 24.4 — Orchestration CI checks
ADD checks:
- Memory schema migration check
tools/memory_schema_migrate_check.py --fail-on-drift
- Handoff ledger append-only audit
No UPDATE/DELETE on handoffs table in migration history.
- Replay-mix evaluation check for adapter promotion PRs
Required by Section 31.5.
AMEND-13 — Appendix M
ADD:
Appendix M — Documentation for open source security software and API
documentation. This appendix provides a human-readable documentation index for
the open-source security platforms integrated by the Enrichment Engine and the
associated API surfaces used by the soc-autopilot project.


SOURCE: LOCAL_SOC_SLM_Blueprint_v11.6.0_master.txt
BLOCK:  Header → Blueprint Layers, CONTENTS, CORE BLUEPRINT RETENTION, AMENDMENT NUMBERING POLICY
SHA256: 7f1f12bdab630ff5
────────────────────────────────────────────────────────────────────────

LOCAL-SOC-SLM v11.6.0 — Master Architecture, Development Blueprint & Scripts
Operational Readability, Knowledge Wiki, Runbook, and Hardening Edition
================================================================================
VERSION: v11.6.0-master
STATUS: Living document; changelog maintained at end of file
BASELINE:
Consolidates v11.3, v11.3-updated, v11.4-complete, v11.5, v11.5-master,
v11.5.1 edge-case hardening, the v11.5.2 completeness-restoration
corrections, and the v11.6.0 operational readability, knowledge-wiki,
runbook, and failure-mode layer into one master document.
VERIFICATION POSTURE:
[VERIFIED-INTERNAL]
Directly supported by the v11.3/v11.4/v11.5/v11.6 blueprint lineage supplied
by the user.
[LAB-VERIFY]
Must be proven against the actual local lab versions, packages, APIs,
credentials, and hardware before production use.
[RESEARCH]
Open design or research question tracked in Appendix N.
ROLE:
Single source of truth for pre-deployment validation, CI gating, deterministic
verification, telemetry-driven canary rollouts, reproducible local SLM training
and inference for a self-hosted Security Operations Center; the v11.2 Enrichment
Engine ("glue" layer) that integrates Wazuh, Security Onion, Suricata, TheHive,
and pfSense; the v11.3 Orchestration Memory Architecture (Postgres + pgvector +
SQLite); the v11.3 Continual Learning & Experience Policy; the v11.3 Appendix M
open-source security software/API documentation index; the v11.4 Deployment
Readiness, Inference Governance, Sanitization/Artifact Reference, and CI Tooling
hardening layer; the v11.5 production-hardening layer covering asynchronous
ingestion backpressure, time-partitioned vector memory, dynamic VRAM governance,
multi-layer sanitization, and hash-chained audit integrity; the v11.5.1
edge-case hardening layer covering stale queue recovery, field-aware entropy
sanitization, hash-chain concurrency control, idempotent embedding prefixes,
and changelog completeness; the v11.5.2 completeness-restoration layer
recovering full Appendix M, full amendment text, Appendix O implementation
skeletons, CI examples, and strengthened completeness checks; and the v11.6.0
operational readability, externalized knowledge-wiki, runbook, and failure-mode
layer.
PRIMARY HARDWARE BASELINE: [VERIFIED-INTERNAL]
Commodity gaming PC / consumer workstation with a single NVIDIA GPU and 16GB
VRAM. Approved v1 lab memory configuration: 64GB DDR5 operated in serialized
phases (Section 28); 96GB preferred for concurrent operation.
FUTURE HARDWARE PATH: [VERIFIED-INTERNAL]
Optional second GPU for separation of duties (development bench vs.
analyst-on-shift). RAM upgrades by matched-kit replacement only.
PROJECT INTENT: [VERIFIED-INTERNAL]
Fine-tune local SLMs; ship an open-source integration/extension layer
(the Enrichment Engine); and provide a persistent orchestration memory layer so
the sum of community security tools is greater than its parts — continuous
enrichment, Tier 1 triage support, experience-driven (but never autonomously
retrained) SLMs, and approval-gated defense-improvement proposals for defenders
who cannot purchase enterprise SOAR/XDR tooling. Blue-team designed;
deterministic safety.

================================================================================
EXECUTIVE SUMMARY [v11.6]
================================================================================
This blueprint defines a local, self-hosted SOC enrichment and orchestration
layer integrating Wazuh, Security Onion, Suricata, TheHive, and pfSense.

The system uses local SLMs for triage support, enrichment, and institutional
knowledge generation, but all state-changing actions are approval-gated.
Models are workers; the orchestrator and database own state.

Core principles:
- Read broadly, draft carefully, mutate only with approval.
- No autonomous online tuning.
- No raw telemetry in PostgreSQL.
- Append-only audit ledger.
- Sanitize before insert, including Wiki generation.
- Deterministic CI verification before production use.
- Operational documentation generation is append-only or draft-only and is
  queued at low priority so it never displaces high-severity alert triage.

================================================================================
HOW TO READ THIS DOCUMENT [v11.6]
================================================================================
New maintainer:
  Read Executive Summary, Sections 1–5, Section 24, Section 30, Section 38,
  Appendix M.9, and Glossary.

Security engineer:
  Read Sections 24, 30, 32, 34, 35, 37, 38, Appendix M.6, Appendix Q.

CI engineer:
  Read Sections 24.4, 32.4, Appendix O, Appendix P.

SOC analyst:
  Read Sections 24, 26, 30.5, 31.2, Appendix M.8.

Operator/deployer:
  Read Sections 23, 28, 33, 35, 36, Appendix N, Appendix Q, release checklist.

================================================================================
GLOSSARY OF TERMS [v11.6]
================================================================================
Adapter:
  Signed fine-tuned model artifact.

Canary:
  Controlled evaluation deployment before full promotion.

Corrections:
  Human accept/fix/reject decisions used as gated training source.

Handoff ledger:
  Append-only audit record of artifacts exchanged between components.

payload_ref:
  Canonical reference to a large external artifact.

Replay-mix evaluation:
  Evaluation combining held-out examples and golden replay samples.

Quarantine-by-reference:
  Preserving a suspicious high-value payload outside orchestration memory by
  secure reference where inline redaction would destroy analytical value.

Shedding:
  Deferring or excluding low-severity queue work under backpressure. Shedding
  is auditable and is not silent deletion.

Wiki / Journalist:
  SLM task type that synthesizes orchestration memory into sanitized Markdown
  documentation under orchestrator control.

Externalized Institutional Memory:
  Human-readable operational documentation generated from orchestration memory
  and governed by Section 38.

================================================================================
BLUEPRINT LAYERS [v11.6]
================================================================================
Layer 0: Hardware
  GPU, VRAM, RAM, serialized phases.

Layer 1: Telemetry sources
  Wazuh, Suricata, Security Onion/OpenSearch.

Layer 2: Intake and sanitization
  Adapters, normalization, quarantine, payload_ref.

Layer 3: Orchestration memory
  PostgreSQL, pgvector, SQLite, append-only audit ledger.

Layer 4: Model workers
  SLM inference, embedding, verifier, Wiki drafter.

Layer 5: Action governance
  Drafts, approvals, writeback, pfSense gating.

Layer 6: Verification
  CI gates, Appendix N evidence, canary/replay.

Layer 7: Operations
  Runbooks, metrics, dashboards, Appendix Q.

================================================================================
CONTENTS
================================================================================
1–19
Preserved from master blueprint lineage.
20
Open-Source Fine-Tuning, Dataset Curation & Hugging Face Publishing Pipeline
21
Community contribution governance, dataset acceptance tests, and signed
adapter policy
22
Developer prompt for LLM-assisted blueprint development
23
Hardware constraints and upgrade path
24
Tier 1 SOC orchestration and tool-use safety contract
25
Commodity gaming-PC lab and automatic defense improvement model
26
Enrichment Engine ("glue" layer) architecture [v11.2, amended]
27
Scripted purple-team lab operations & batch dataset generation [v11.2]
28
Serialized lab operations for consumer hardware (64GB start) [v11.2]
29
Model scaling, harness patterns, and analyst-on-shift paradigm [v11.2]
30
Orchestration Memory Architecture
[v11.3, amended by v11.4/v11.5/v11.5.1/v11.5.2/v11.6]
31
Continual Learning & Experience Policy
[v11.3, amended by v11.4]
32
Deployment Readiness & Verification Register
[v11.4, amended by v11.5/v11.5.1/v11.5.2/v11.6]
33
Inference, Embedding, and VRAM Governance
[v11.4, amended by v11.5]
34
Sanitization, Quarantine, and Artifact Reference Governance
[v11.4, amended by v11.5/v11.5.1]
35
Asynchronous Ingestion, Backpressure, and Triage Queue Governance
[v11.5, amended by v11.5.1]
36
Time-Partitioned Vector Memory and Index Lifecycle [v11.5]
37
Hash-Chained Audit Ledger and Tamper Detection
[v11.5, amended by v11.5.1]
38
Operational Knowledge Generation & Externalized Memory [v11.6]
Appendix A–H
Preserved from v11.1 with amendments.
Appendix I
Enrichment Engine reference config & enrichment status schema [v11.2]
Appendix J
Starter purple-team scenario & expected alerts [v11.2]
Appendix K
Orchestration Memory DDL, retention, and backup [v11.3]
Appendix L
Adapter routing & continual-learning config [v11.3]
Appendix M
Documentation for open source security software and API documentation
[v11.3, amended by v11.4, restored and amended by v11.5.2/v11.6]
Appendix N
Pre-Implementation Research & Verification Register
[v11.4, amended by v11.5/v11.5.1/v11.6]
Appendix O
CI Verification Tool Contracts & Skeletons
[v11.4, amended by v11.5/v11.5.1, restored and expanded by v11.5.2/v11.6]
Appendix P
Production-Hardening SQL, Python, and CI Templates
[v11.5, amended by v11.5.1/v11.5.2/v11.6]
Appendix Q
Runbooks & Failure Mode Analysis [v11.6]
Full v11.6.0 Release Checklist
Completeness Manifest
Changelog

================================================================================
CORE BLUEPRINT RETENTION
================================================================================
Sections 1–19 remain preserved from the master blueprint lineage.
Sections 20–29 and Appendices A–J remain preserved from v11.2 and v11.3,
applying the mechanical amendments listed in this document.
Appendix K and Appendix L remain the v11.3 operational memory and adapter
routing references.
Appendix M is restored to the full v11.3-updated human-readable edition,
amended by v11.4 verification notes, and further amended by v11.5.1/v11.5.2/
v11.6 where embedding prefix idempotency, completeness checks, and knowledge
Wiki governance apply.
Appendix N, Appendix O, Appendix P, and Appendix Q are part of the
v11.4/v11.5/v11.5.1/v11.5.2/v11.6 hardening layer.
Where external software behavior is version-dependent, this blueprint does not
assert external facts unless they are directly present in the supplied lineage
or proven in the lab. External integration behavior is LAB-VERIFY and recorded
in Appendix N.
The v11.6.0 safety contract remains unchanged and is extended by the Wiki
governance rules in Section 38:
- Read broadly, draft carefully, mutate only with approval.
- pfSense mutations remain approval-gated.
- Wazuh and Suricata rule changes remain draft-only until approved.
- TheHive operational writes remain policy-controlled.
- PostgreSQL handoffs and corrections remain append-only.
- Raw telemetry remains outside PostgreSQL.
- Autonomous online tuning remains prohibited.
- Queue shedding is auditable and is not silent deletion.
- High-value suspicious payloads are quarantined by reference when inline
redaction would destroy analytical value.
- Hash-chain generation is serialized and tamper-evident.
- Embedding prefix injection is idempotent.
- Completeness checks must detect omitted appendices, truncated changelog
entries, and missing termination markers.
- SLM Wiki generation is append-only or draft-only, sanitized before commit,
and queued at low priority to protect operational triage VRAM.

================================================================================
AMENDMENT NUMBERING POLICY
================================================================================
This master document uses one cumulative amendment sequence:
AMEND-1   through AMEND-13   = v11.3 amendments
AMEND-14  through AMEND-26   = v11.4 amendments
AMEND-27  through AMEND-36   = v11.5 amendments
AMEND-37  through AMEND-41   = v11.5.1 amendments
AMEND-42  through AMEND-46   = v11.5.2 amendments
AMEND-47  through AMEND-52   = v11.6.0 amendments
This sequence supersedes earlier draft numbering that collided between v11.4,
v11.5, and v11.5 update documents.


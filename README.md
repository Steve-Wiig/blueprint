# soc-autopilot

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/Tests-274%20Passed%20(2%20transient%20failures)-orange.svg)](https://github.com/Steve-Wiig/soc-autopilot)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Architecture](https://img.shields.io/badge/Architecture-Hybrid%20Cloud%2BEdge-orange.svg)](docs/ARCHITECTURE.md)

**A locally operated Security Operations Center with LLM-assisted triage and a governed, self-improving codebase.**

---

### 🏗️ High-Level Architecture

```mermaid
graph TD
    A[Wazuh / pfSense] -->|Telemetry| B(Engine: Ingestion & Sanitization)
    B --> C{Orchestrator & Queue}
    C -->|Tier 1 Triage| D[Cloud LLMs: OpenRouter/Groq/Mistral]
    C -->|Async Patch Gen/Review| E[Edge: Raspberry Pi + Qwen 3B]
    C -->|State & Memory| F[(SQLite + planned pgvector)]
    C -->|Audit Ledger| G[Hash-Chain Append-Only Log]
    E -.->|Fallback / Quota-Free| C
    C -->|Safety Gates| H[Pytest 274+ Suite]
    H -->|Pass| I[Shadow Branch Commit]
    I -->|Human Approval| J[Master Merge]
```

---

### 🎯 Problem & Solution

**Problem:** Enterprise SOAR/XDR tools are expensive, cloud-bound, and often lack transparent, auditable automation. LLMs, when wired directly to systems, are untrusted and prone to hallucination.

**Solution:** `soc-autopilot` is a local-first, self-hosted platform (with cloud-assisted generation) that uses Small Language Models (SLMs) for Tier 1 triage and enrichment, governed by a strict, test-gated autonomous engineering pipeline.

**Core Philosophy:** *LLMs propose → safety gates validate → tests verify → Git records → humans decide.*

---

### 🛡️ Security & Governance Model

This is not an "autonomous AI" that acts without oversight. It is a **bounded decision-support system** built on security engineering principles:

* **Zero Trust for LLM Output:** All generated code must pass AST validation, ghost-name checks, and a 274+ test pytest suite before being considered.
* **Negative Memory:** The system actively learns from failed patches and stores them as "AVOID" constraints for future attempts.
* **Tamper-Evident Auditing:** Pipeline decisions are tracked in structured JSONL ledgers. A tamper-evident hash-chain audit ledger is prototyped but not yet in production use.
* **Hybrid Verification Plane:** A decoupled Raspberry Pi edge worker acts as an independent, heterogeneous code-review node, ensuring failure isolation and quota-free fallback.

---

### 📊 Current Status & Evidence

| Component                                  | Status          | Notes                                                         |
| ------------------------------------------ | --------------- | ------------------------------------------------------------- |
| Telemetry Sanitization & Queue Governance  | ✅ Implemented   | Two-pass regex + entropy sanitization; backpressure handling. |
| Hash-Chain Audit Ledger | △ Prototype | Concurrency tool exists; production ledger planned. |
| Self-Improvement Pipeline (10 Safety Gates) | ✅ Implemented   | TDD Red Phase, Forensic Analysis, Ghost Detection, Shadow Canary, Proven Memory, etc.          |
| Negative/Proven Memory Stores              | ✅ Implemented   | System stores proven and failed fix patterns to inform future generation.               |
| Hybrid Edge/Cloud Compute                  | ✅ Implemented   | Async Pi worker (Qwen 3B) decoupled via Redis.                |
| Live Wazuh Integration              | △ Lab-Validated | Tested in local Dockerized lab environment.                   |
| Longitudinal Learning Metrics              | △ Prototype     | Tracking fix acceptance rates; immutable eval corpus planned. |

---

### 🚀 Quick Start

#### Prerequisites
- Suricata integration (planned - architecture supports it)

* Python 3.10+
* API keys for LLM providers (OpenRouter, Groq, Mistral)
* Optional: Raspberry Pi 4B+ (8GB) for edge critique worker

#### Installation

```bash
git clone https://github.com/Steve-Wiig/soc-autopilot.git
cd soc-autopilot
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
```

#### Verification

```bash
# Run the regression suite
python3 -m pytest tests/ -q
# Expected: 274 passed (2 transient test_tdd_auto_* failures are harmless)
```

#### Operator CLI

```bash
dashboard          # Live status, scorecard, disk health, and edge worker status
```

---

### 📚 Documentation

For deep dives into the architecture, operations, and self-improvement mechanics:

| Resource                                                   | Purpose                                              |
| ---------------------------------------------------------- | ---------------------------------------------------- |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)             | System architecture, data flow, and design decisions |
| [`docs/OPERATIONS_RUNBOOK.md`](docs/OPERATIONS_RUNBOOK.md) | Operational workflows, troubleshooting, and runbooks |
| [`docs/OVERNIGHT_PIPELINE.md`](docs/OVERNIGHT_PIPELINE.md) | Self-improvement pipeline internals and safety gates |
| [`docs/WINTER_ROADMAP.md`](docs/WINTER_ROADMAP.md)         | Future development, including immutable eval corpus  |

---

### ⚠️ Limitations

* **Not a replacement for human analysts:** The system is designed to augment Tier 1 triage and propose *candidate* fixes. Human approval is mandatory for all merges.
* **Hardware constraints:** While the edge worker is resilient, high-volume local inference requires an NVIDIA GPU (16GB+ VRAM). The current default relies on free-tier cloud APIs + a Raspberry Pi for async review.

---

## License

**MIT License**
Copyright (c) 2026 Steve Wiig

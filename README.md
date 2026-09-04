# soc-autopilot

**A local Security Operations Center with LLM-assisted triage and a self-improving codebase.**

---

## What It Is

soc-autopilot is a **locally operated** security platform that:
- Ingests and sanitizes security telemetry (Wazuh, Security Onion, Suricata)
- Uses Small Language Models (SLMs) for triage, enrichment, and institutional knowledge
- Maintains an **append-only audit ledger** for all actions
- Includes a **constrained self-improvement pipeline** that proposes and tests its own fixes

**Core principle:** *LLMs propose, safety gates validate, tests verify, Git records, humans decide.*

---

## Why It Exists

Enterprise SOAR/XDR tools are expensive and often cloud-only. soc-autopilot provides:
- **Tier 1 triage support** for defenders without enterprise budgets
- **Local control** over data, models, and operations
- **Continuous improvement** via a safe, gated self-improvement loop
- **Open-source integration** with existing security tools (Wazuh, TheHive, pfSense)

---

## Key Components

| Component | Purpose |
|-----------|---------|
| **Engine** | Ingestion, sanitization, queue management, SLM triage |
| **Memory** | Orchestration memory (PostgreSQL + pgvector + SQLite) |
| **Orchestrator** | Context stitching, model routing, action governance |
| **Tools** | CI gates, audit checks, dashboard, and verification |
| **Overnight Pipeline** | Self-improvement loop (advisory → fix → test → commit) |

---

## Self-Improvement Pipeline

The overnight pipeline is the project's defining feature. It closes the loop on autonomous engineering:

1. **Analyze** the codebase for genuine logic bugs and improvements.
2. **Validate** findings via cross-model critique (Gemini, Groq, OpenRouter).
3. **Propose** surgical fixes using proven patterns and avoiding known failures.
4. **Test** all changes via a rigorous pytest suite.
5. **Commit** to a shadow branch, then merge if safe.

### Safety Gates

Every proposed change must pass through this gauntlet:

- ✅ **TDD Red Phase:** Rejects vacuous tests that pass without a fix.
- ✅ **Ghost Name Gate:** AST validation catches hallucinated imports instantly.
- ✅ **Lenient Fuzzy Matcher:** Tolerates indent/whitespace drift in SEARCH blocks.
- ✅ **Delta Acceptance:** Rejects fixes that break previously-passing tests.
- ✅ **Pi Critic:** Asynchronous edge-model review via Redis (quota-free).
- ✅ **Shadow Canary:** Cyclomatic complexity + runtime safety checks.
- ✅ **Memory Stores:** Retrieves proven fixes (few-shot) and failed patterns (AVOID).
- ✅ **Git Boundary:** Commits locally, never auto-pushes to remote.

---

## Hybrid Compute Architecture

soc-autopilot uses a decoupled **cloud + edge** architecture for resilience and cost control:

- **Cloud:** OpenRouter (primary), Groq, and Mistral with dynamic fallback and rate-limit pacing.
- **Edge:** A Raspberry Pi 4B running Qwen2.5-Coder-3B as an asynchronous critic.
- **Queue:** Redis job queue for decoupled, fault-tolerant reviews.
- **Principle:** The edge worker can crash, lag, or reboot without ever blocking the main pipeline.

---

## Quick Start# soc-autopilot

**A locally operated Security Operations Center with LLM-assisted triage and a self-improving codebase.**

---

## What It Is

soc-autopilot is a **self-hosted** security platform that:
- Ingests and sanitizes telemetry from **Wazuh, Security Onion, and Suricata**
- Uses **Small Language Models (SLMs)** for triage, enrichment, and institutional knowledge
- Maintains an **append-only audit ledger** for all actions and state changes
- Features a **constrained self-improvement pipeline** that autonomously proposes, tests, and commits fixes

**Core principle:** *LLMs propose, safety gates validate, tests verify, Git records, humans decide.*

---

## Why It Exists

Enterprise SOAR/XDR tools are expensive and often cloud-only. soc-autopilot provides:
- **Tier 1 triage support** for defenders without enterprise budgets
- **Local control** over data, models, and operations (no vendor lock-in)
- **Continuous improvement** via a safe, gated self-improvement loop
- **Open-source integration** with existing security tools (Wazuh, TheHive, pfSense, OpenSearch)

---

## Key Components

| Component          | Purpose                                                                 |
|--------------------|-------------------------------------------------------------------------|
| **`engine/`**      | Telemetry ingestion, sanitization, queue management, SLM triage workers |
| **`memory/`**      | Orchestration memory (PostgreSQL + pgvector + SQLite)                   |
| **`orchestrator/`**| Context stitching, model routing, action governance                     |
| **`tools/`**       | CI gates, audit checks, dashboard, and verification tools               |
| **`overnight/`**   | Self-improvement pipeline (advisory → fix → test → commit)              |
| **`lab/`**         | Dockerized test environments for Wazuh, PostgreSQL, etc.                |

---

## Self-Improvement Pipeline

The overnight pipeline is soc-autopilot's **defining feature**. It closes the loop on autonomous engineering:

1. **Analyze** the codebase for genuine logic bugs and architectural improvements.
2. **Validate** findings via cross-model critique (Gemini, Groq, OpenRouter).
3. **Propose** surgical fixes using proven patterns and avoiding known failure modes.
4. **Test** all changes via a **268-test pytest suite** (must pass before commit).
5. **Commit** to a **shadow branch**, then merge to `master` only if safe.

### Safety Gates

Every proposed change must pass this gauntlet:

| Gate                     | Purpose                                                                 |
|--------------------------|-------------------------------------------------------------------------|
| **TDD Red Phase**        | Rejects vacuous tests that pass without a real fix                      |
| **Ghost Name Gate**      | AST validation catches hallucinated imports instantly                   |
| **Lenient Fuzzy Matcher**| Tolerates indent/whitespace drift in SEARCH/REPLACE blocks              |
| **Delta Acceptance**     | Rejects fixes that break previously passing tests                       |
| **Pi Critic**            | Async edge-model review via Redis (quota-free fallback)                 |
| **Shadow Canary**        | Cyclomatic complexity + runtime safety checks                           |
| **Memory Stores**        | Retrieves proven fixes (few-shot) and failed patterns (AVOID list)      |
| **Git Boundary**         | Commits locally to `autofix-*` branches; **never auto-pushes to remote**|

---

## Hybrid Compute Architecture

soc-autopilot uses a **decoupled cloud + edge architecture** for resilience and cost control:

- **Cloud Models:**
  OpenRouter (primary), Groq, Mistral.
  *Dynamic fallback with rate-limit pacing and 24h lockout on exhaustion.*

- **Edge Critic (Optional):**
  Raspberry Pi 4B+ (8GB) running **Qwen2.5-Coder-3B** as an async reviewer.
  *Uses a Redis job queue; edge can crash/lag without blocking the main pipeline.*

- **Local Inference (Production):**
  NVIDIA GPU with **16GB+ VRAM** for high-volume telemetry processing.

**Principle:** The edge worker can **crash, lag, or reboot** without ever blocking the main pipeline.

---

## Quick Start

### Prerequisites

#### 🧪 Development / Evaluation *(No GPU Required)*
- Python 3.10+
- API keys for LLM providers (Gemini, Groq, OpenRouter)
- Optional: Raspberry Pi 4B+ (8GB) for edge critique worker

#### 🏭 Production *(Full Telemetry Ingestion)*
- Python 3.10+
- **PostgreSQL + pgvector**
- **NVIDIA GPU with 16GB+ VRAM** *(for local SLM inference)*
- Wazuh / Security Onion / pfSense integration
- API keys for LLM providers *(fallback and consensus voting)*

### Installation & Testing

```bash
# Clone the repo
git clone https://github.com/Steve-Wiig/soc-autopilot.git
cd soc-autopilot

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys:
# GEMINI_API_KEY=your_key_here
# LAB_URL=https://127.0.0.1
# WAZUH_USER=readonly_user
# WAZUH_TOKEN=your_token

# Verify the test suite
python3 -m pytest tests/ -q
# ✅ Expected: 268 passed, 1 skipped
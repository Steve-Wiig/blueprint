# LOCAL-SOC-SLM

## Local Security Operations Center · Small Language Model Platform

**v11.11 — Current Documentation & Operational Baseline**
**Status: Active / Experimental Infrastructure**

LOCAL-SOC-SLM is a locally operated security-operations platform for ingesting, sanitizing, triaging, enriching, persisting, auditing, and acting on security telemetry with controlled Small Language Model (SLM) assistance.

The project also contains a constrained overnight self-improvement pipeline that allows LLMs to **analyze the codebase and propose or attempt surgical fixes**, while enforcing multiple safety gates before generated code can become a Git commit.

> **LLMs may propose changes. Safety gates, tests, Git history, and human operators decide what survives.**

---

## Current Version

### v11.11 — Documentation / Operational Baseline

The v11.11 baseline incorporates the latest Aug. 29, 2026 operational state and the lessons learned while exercising the v11.10 hardened overnight pipeline.

**Verified source baseline:**

```text
0f41f4d
fix: eliminate all Python 3.12 datetime deprecation warnings
```

The current working tree also contains runtime state generated during overnight/Qwen analysis, including advisory-queue and backlog state.

**Important:** the existence of an advisory does not mean the underlying issue has been accepted or fixed.

The current v11.11 baseline therefore distinguishes between:

* verified implementation;
* runtime/queue state;
* LLM-generated advisories;
* deferred work;
* human-approved fixes.

---

# What the System Does

At a high level:

```text
                    SECURITY TELEMETRY
                           │
              ┌────────────┴────────────┐
              │                         │
           Wazuh                       EVE
              │                         │
              └────────────┬────────────┘
                           ▼
                  Sanitization /
                    Quarantine
                           │
                           ▼
                    Queue Manager
                           │
                           ▼
                       SLM Triage
                           │
             ┌─────────────┼─────────────┐
             ▼             ▼             ▼
           IOC         Enrichment      Context
        Extraction      Scheduler      Stitching
             │             │             │
             └─────────────┼─────────────┘
                           ▼
                    Persistent Memory
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
          Embeddings    Retention    Audit Chain
              │            │            │
              └────────────┼────────────┘
                           ▼
                     Security Actions
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
        Wazuh           TheHive          Security Onion
       Proposals        Writeback          / pfSense
```

The repository contains dedicated components for:

* Wazuh ingestion;
* EVE ingestion;
* sanitization and redaction;
* queue management and backpressure;
* SLM triage;
* IOC extraction;
* enrichment;
* context stitching;
* model registration/routing;
* embeddings;
* retention;
* hash-chain audit sealing;
* Wazuh proposals;
* TheHive writeback;
* Security Onion cases;
* pfSense aliases.

---

# Overnight Self-Improvement Pipeline

The overnight subsystem is deliberately constrained.

It is **not** an unrestricted autonomous coding agent.

The current conceptual flow is:

```text
Advisory Generation
        │
        ▼
 Advisory Queue
        │
        ▼
 Human / Pipeline Triage
        │
        ▼
    Fix Backlog
        │
        ▼
   LLM Code Proposal
        │
        ▼
     Safety Gates
        │
        ▼
      Pytest
        │
     ┌──┴──┐
     │     │
   FAIL   PASS
     │     │
  Restore  │
     │     ▼
     │   Local Git Commit
     │
     ▼
 Deferred / Manual Triage
```

### Advisory Queue

The current queue is persisted under:

```text
overnight/advisory_queue/pending/
```

This makes findings inspectable and restartable.

### Fix Backlog

The active backlog is:

```text
overnight/fix_backlog.json
```

Deferred work is maintained separately.

### Important distinction

An advisory is an **observation**, not proof of a defect.

Before implementing an advisory:

1. verify the issue still exists;
2. inspect the actual source;
3. inspect the relevant tests;
4. determine whether the issue is architectural or surgical;
5. reject false-positive or cosmetic recommendations;
6. apply the smallest safe change;
7. run validation;
8. review the Git diff.

---

# Autonomous-Fix Safety Architecture

Generated code is treated as untrusted.

The v11.10 hardening introduced and confirmed several active controls.

## AST Gate

Generated Python is parsed with:

```python
ast.parse(...)
```

before the candidate is accepted.

This prevents malformed Python, Markdown, or other non-code output from silently becoming source code.

## CoT / Reasoning Detector

The `_looks_like_reasoning` detector identifies responses that contain reasoning prose rather than executable source.

This protects against model output such as:

```text
Let me think about this...
```

being written into a Python file.

## Pytest Gate

Generated fixes must pass the project test suite before they can be accepted.

Current verified suite:

```text
182 passed
```

## Truncation Guard

Suspiciously short generated replacements are rejected rather than allowing an incomplete model response to destroy source code.

## Backup / Rollback

Candidate changes use an original-file backup/recovery mechanism before replacement.

## Git Boundary

Autonomous fixes are committed locally.

The autonomous pipeline does **not** have authority to publish directly to GitHub.

That leaves repository publication under human control.

---

# LLM Provider Architecture

The current provider architecture uses differentiated roles:

```text
                 ┌────────────────┐
                 │     Gemini     │
                 │ Analysis /     │
                 │ Critique       │
                 └───────┬────────┘
                         │
                         ▼
                   Advisory / QA
                         │
                         ▼
                 ┌────────────────┐
                 │   OpenRouter   │
                 │    Primary     │
                 └───────┬────────┘
                         │
                   fallback
                         ▼
                 ┌────────────────┐
                 │      Groq      │
                 │    Fallback    │
                 └────────────────┘
```

The v11.10 documentation identifies the funded OpenRouter allowance as **1000 requests/day**, with persistent quota/cooldown state.

Runtime state includes:

```text
overnight/openrouter_quota.json
overnight/api_usage.json
overnight/model_fallback_cache.json
```

Provider credentials themselves must never be committed to Git.

---

# Human-in-the-Loop

The overnight system deliberately retains human triage.

The primary triage decisions are:

| Decision    | Meaning                                                             |
| ----------- | ------------------------------------------------------------------- |
| **PHANTOM** | The reported issue is already resolved or no longer exists          |
| **REJECT**  | The advisory is incorrect, inappropriate, or not worth implementing |
| **FIX**     | The issue is real and warrants a surgical change                    |

The operator should verify every recommendation rather than treating model output as authoritative.

---

# Operational Workflow

### Check repository state

```bash
git status
```

### Inspect recent work

```bash
git log --oneline -20
```

### Run the test suite

```bash
python3 -m pytest tests/ -q
```

### Inspect overnight status

```bash
bash overnight/dashboard.sh
```

### Read the morning report

```bash
cat overnight/morning_report.md
```

### Review recent autonomous commits

```bash
git log --oneline --since="12 hours ago"
```

---

# Critical Operational Lessons

These are operational rules learned from actual use of the overnight system.

### Queue-file race condition

The drain holds the backlog in memory and rewrites the JSON after each item. Editing `fix_backlog.json` or `fix_backlog_deferred.json` while the drain runs gets OVERWRITTEN on its next save.

**Queue surgery requires: stop drain → edit → commit → relaunch.**

### Configuration-class trap

Wrapping `os.environ.get()` in a class with class attributes still evaluates the calls at class-definition time, which is still module load.

**Environment variables that must reflect runtime configuration should be read inside functions/methods rather than relying on class-attribute initialization.**

### Duplicate advisories

Twin copies of an advisory can cause the drain to retry the same issue repeatedly and consume quota.

Clear duplicates by matching their description/content rather than relying on list indexes.

### Global replacement corruption

Blind string replacement can modify unrelated identifiers, comments, or documentation.

Prefer anchored replacements, word boundaries, or AST-based transformations.

### Subprocess environment inheritance

A subprocess does not automatically read variables from a `.env` file merely because the parent project contains one.

The launch path must explicitly load the environment when required.

### Silent background crashes

A PID existing does not prove that the actual processing loop remains healthy.

Use unbuffered output and inspect logs/dashboard state rather than relying only on `pgrep`.

### Reuse proven entry points

Prefer the project's tested CLI entry points over ad-hoc wrapper logic that can accidentally omit initialization or safety behavior.

---

# v11.11 Advisory State

The Aug. 29 Qwen analysis generated a persistent advisory queue containing findings across multiple project components.

Examples include:

```text
memory/retention.py
memory/embeddings.py
orchestrator/context_stitcher.py
orchestrator/model_registry.py
engine/slm_triage_worker.py
engine/writeback/*
tools/*
```

These findings are retained as **pending analysis**, not represented as completed fixes.

This distinction is intentional.

The project should only claim a fix after:

```text
Issue verified
    ↓
Surgical change
    ↓
Validation
    ↓
Tests pass
    ↓
Git diff reviewed
    ↓
Commit
```

---

# Testing

The current verified test result is:

```text
182 passed
```

Run:

```bash
python3 -m pytest tests/ -q
```

The test suite covers areas including:

* queue management;
* queue backpressure;
* stale queue recovery;
* sanitization;
* redaction;
* embeddings;
* enrichment;
* IOC extraction;
* context stitching;
* model registry;
* retention;
* audit-chain behavior;
* hash-chain concurrency;
* Wazuh proposals;
* TheHive writeback;
* Security Onion cases;
* pfSense aliases;
* autonomous-fix validation.

---

# Repository Structure

```text
blueprint/
├── engine/
│   ├── intake_wazuh.py
│   ├── intake_eve.py
│   ├── sanitization_pipeline.py
│   ├── queue_manager.py
│   ├── slm_triage_worker.py
│   ├── enrichment_scheduler.py
│   ├── ioc_extractor.py
│   ├── hash_chain_sealer.py
│   └── writeback/
│
├── memory/
│   ├── embeddings.py
│   ├── retention.py
│   └── schema/
│
├── orchestrator/
│   ├── context_stitcher.py
│   ├── model_registry.py
│   └── routing.yaml
│
├── overnight/
│   ├── self_improver.py
│   ├── advisory_queue/
│   ├── fix_backlog.json
│   ├── dashboard.sh
│   ├── morning_report.md
│   ├── api_usage.json
│   ├── openrouter_quota.json
│   └── model_fallback_cache.json
│
├── tools/
├── tests/
└── docs/
```

---

# Known Limitations

LOCAL-SOC-SLM remains experimental infrastructure.

Known limitations include:

* difficult architectural issues still require human intervention;
* advisory queues can accumulate;
* provider quotas can halt autonomous processing;
* large files may exceed available model context;
* fallback providers may have smaller context capabilities;
* background processing requires monitoring;
* LLM-generated recommendations can be false positives;
* autonomous code generation remains probabilistic;
* the current v11.11 baseline contains pending advisory findings rather than verified fixes for every finding.

The project's safety model intentionally favors:

> **A rejected change over a corrupted change.**

---

# Version History

## v11.8

Historical development phase preceding the current hardened overnight architecture.

## v11.9

Historical baseline containing the earlier self-improvement architecture and documentation that was subsequently superseded.

The v11.9 material is retained for historical reference but is **not the current operational architecture**.

## v11.10

Introduced the hardened overnight operating model, including:

* synchronous advisory/fix processing;
* persistent advisory and fix queues;
* OpenRouter/Groq/Gemini provider architecture;
* AST validation;
* CoT detection;
* truncation protection;
* pytest gating;
* backup/rollback behavior;
* quota-aware execution;
* operational dashboard/reporting;
* documented queue/configuration failure modes.

## v11.11

**Current documentation and operational baseline — Aug. 29, 2026.**

v11.11 incorporates the latest operational/Qwen analysis state and preserves the resulting advisory queue for human review.

**Verified source HEAD remains:**

```text
0f41f4d
```

v11.11 should not be interpreted as claiming that every Aug. 29 advisory has been implemented or that a new source-code release exists.

---

# Project Philosophy

LOCAL-SOC-SLM is an experiment in building a security platform where language models can participate in operations and software maintenance without becoming an unrestricted authority.

The central design rule is:

```text
AI proposes
    ↓
System validates
    ↓
Tests verify
    ↓
Git records
    ↓
Human decides
```

The objective is not maximum autonomy.

The objective is **useful autonomy with bounded failure modes, recoverability, auditability, and human control**.

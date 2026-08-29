# LOCAL-SOC-SLM — MASTER DOCUMENTATION BUNDLE

## 1. Document Control

| Field                      | Value                                                                    |
| -------------------------- | ------------------------------------------------------------------------ |
| Document                   | `MASTER_DOCUMENTATION_BUNDLE.md`                                         |
| Canonical System State     | **v11.10 Hardened State**                                                |
| Document Version           | **v11.10**                                                               |
| Date                       | **2026-08-29**                                                           |
| Status                     | Canonical consolidated operational documentation                         |
| Supersedes                 | v11.9-era overnight/self-improvement documentation                       |
| Historical Baseline        | Aug 23, 2026 v11.9 status/resume material                                |
| Primary Operational Source | `overnight/` implementation and current v11.10 operational documentation |

This document describes the **v11.10 Hardened State** of LOCAL-SOC-SLM.

The Aug 23 v11.9 material is historical and is not authoritative for current overnight-pipeline architecture, queue format, provider selection, quota behavior, scheduling, or safety controls. The project tree still contains v11.9 blueprint artifacts, but the operational state has advanced to v11.10. 

The canonical v11.10 state is characterized by a synchronous, user-scheduled overnight process, disk-backed advisory queueing, OpenRouter/Groq/Gemini provider roles, persistent quota/cooldown state, and test-gated autonomous code changes. 

---

# 2. Executive Summary & Current State Snapshot

## 2.1 What Is This System Today?

LOCAL-SOC-SLM is a local security-operations platform with:

* Wazuh and EVE ingestion;
* sanitization and quarantine;
* queue management and backpressure;
* SLM-based triage;
* IOC extraction;
* enrichment;
* orchestration/context stitching;
* persistent memory and embeddings;
* hash-chain audit sealing;
* downstream writeback integrations;
* and a separate overnight autonomous self-improvement subsystem.

The project tree confirms dedicated implementations for Wazuh/EVE intake, sanitization, queue management, SLM triage, enrichment, IOC extraction, hash-chain sealing, memory, orchestration, and multiple writeback targets. 

The overnight subsystem is **not an unrestricted autonomous software agent**. It is an automated review-and-fix loop operating inside explicit budget, provider, parsing, test, rollback, concurrency, and human-triage boundaries.

## 2.2 Canonical Version

**Canonical operational state: v11.10 Hardened State.**

The v11.10 hardening was introduced on August 25, 2026 and added the current safety controls and overnight wrapper. 

There is not yet a separately named `LOCAL_SOC_SLM_Blueprint_v11.10...` master artifact in the supplied project tree; the named blueprint artifacts stop at v11.9. This document therefore serves as the consolidated v11.10 master documentation state. 

## 2.3 Autonomous vs. Human-Controlled Operation

### Autonomous

Once invoked, the overnight pipeline can:

1. read source files and advisory state;
2. perform Gemini pre-analysis;
3. process advisories using OpenRouter/Groq;
4. validate findings;
5. generate candidate fixes;
6. apply candidate fixes;
7. run the full pytest gate;
8. revert failed fixes;
9. commit successful fixes locally;
10. continue processing until the backlog or available budget is exhausted;
11. defer repeatedly failing items for human triage;
12. produce a morning report.

The wrapper is explicitly described as a closed-loop autonomous process that generates fixes, test-gates them, commits successful changes, defers failures after three attempts, and writes `overnight/morning_report.md`. 

### Human intervention

Humans remain responsible for:

* choosing the execution schedule;
* monitoring pipeline health;
* responding to process death;
* responding to budget-gate failures;
* reviewing deferred items;
* classifying `PHANTOM`, `REJECT`, or `FIX`;
* applying hard architectural fixes;
* resolving operational races;
* and making manual changes where autonomous fixing repeatedly fails.

The deferred workflow explicitly requires human judgment after three failed attempts. 

## 2.4 Current Operational Principle

The LLM is an **untrusted execution environment**.

The architecture therefore treats generated code as untrusted output rather than as inherently correct output. Safety gates, testing, rollback, quota control, audit history, and human architectural judgment remain authoritative.

---

# 3. Current Architecture

## 3.1 High-Level Flow

```text
Security Sources
      |
      v
+----------------------+
| Wazuh / EVE Intake   |
+----------------------+
      |
      v
+----------------------+
| Sanitization         |
| Quarantine           |
+----------------------+
      |
      v
+----------------------+
| Queue Manager        |
| Backpressure         |
+----------------------+
      |
      v
+----------------------+
| SLM Triage           |
+----------------------+
      |
      +--------------------+
      |                    |
      v                    v
+-------------+     +-------------------+
| IOC         |     | Enrichment /      |
| Extraction  |     | Context Stitching |
+-------------+     +-------------------+
      |                    |
      +----------+---------+
                 |
                 v
        Persistence / Memory
                 |
                 +----------------------+
                 |                      |
                 v                      v
          Audit Hash Chain       Downstream Writeback
                                  - Wazuh proposals
                                  - TheHive
                                  - SO cases
                                  - pfSense aliases
```

The corresponding engine modules are present in the supplied tree. 

## 3.2 Ingestion

Current ingestion components include:

* `engine/intake_wazuh.py`
* `engine/intake_eve.py`

These provide the Wazuh and EVE entry points into the processing system. 

## 3.3 Normalization and Sanitization

`engine/sanitization_pipeline.py` is the principal sanitization component.

The repository also contains dedicated verification for:

* sanitization entropy;
* sanitization field policy;
* sanitization redaction;
* wiki sanitization.

These are represented by both implementation tests and dedicated checking tools.  

## 3.4 Queue Management

`engine/queue_manager.py` manages the operational queue layer.

The current system explicitly includes queue-depth, lag, consumer-health, and backpressure concepts. The documented operational thresholds include:

* `intake_raw` growth above 100/min as an upstream surge indicator;
* `triage_pending` above 5000 as a worker-saturation indicator;
* `quarantine` above 1000 as a sanitization/triage failure-spike indicator.

These metrics are operational indicators rather than universal correctness thresholds. 

Dedicated tests cover queue management, queue backpressure, and stale-queue recovery. 

## 3.5 Triage

`engine/slm_triage_worker.py` provides the SLM triage layer.

The system also contains:

* `orchestrator/context_stitcher.py`;
* `orchestrator/model_registry.py`;
* `orchestrator/routing.yaml`.

These provide orchestration and model-routing infrastructure. 

## 3.6 Enrichment and IOC Extraction

The current tree contains:

* `engine/enrichment_scheduler.py`
* `engine/ioc_extractor.py`

Enrichment and IOC extraction are therefore first-class current components, not merely historical architectural concepts. 

## 3.7 Persistence and Memory

The current tree contains:

* `memory/embeddings.py`;
* `memory/retention.py`;
* `memory/schema/audit_chain.sql`;
* `memory/schema/orchestration_memory.sql`;
* `memory/schema/partitioned_case_embeddings.sql`.

The system therefore includes persistent memory, embeddings, retention, and audit-chain schema components. 

## 3.8 Audit Chain

`engine/hash_chain_sealer.py` provides hash-chain sealing and verification.

Operational procedures include full-chain verification and targeted verification of recent blocks. 

Emergency repair is destructive to the audit history and must only be undertaken after confirming the underlying data-loss condition. 

## 3.9 Writeback

The current tree contains writeback implementations for:

* pfSense aliases;
* SO cases;
* TheHive;
* Wazuh proposals.



---

# 4. The v11.10 Overnight Self-Improvement Pipeline

## 4.1 Design

The v11.10 overnight pipeline is:

**synchronous, user-scheduled, queue-based, cross-model validated, test-gated, and locally committed.**

It runs only when explicitly invoked through cron, systemd, a wrapper, or manual execution. There is no hardcoded schedule in the pipeline code. 

## 4.2 Entry Point

Primary entry point:

```text
overnight/self_improver.py
```

The current implementation is a flat script with three primary functions:

```text
prefill_advisory_queue()
process_advisory_queue()
drain_fix_backlog()
```



These names define the current logical flow and replace the obsolete v11.9 async Phase A/B/C API.

## 4.3 Stage 1 — Advisory Prefill

`prefill_advisory_queue()` reads source files and generates initial analysis through Gemini.

The resulting advisory material is persisted in the disk-backed pending queue:

```text
overnight/advisory_queue/pending/
```

One advisory JSON file is maintained per source file. 

Current advisory queue naming is based on a safe representation of the source path, for example:

```text
engine__queue_manager.json
tools__embedding_prefix_check.json
```

The implementation derives the queue filename from the source path and stores it under `overnight/advisory_queue/pending/`. 

## 4.4 Stage 2 — Advisory Processing

`process_advisory_queue()` processes pending advisory material and produces fix plans using the current LLM provider architecture.

The current implementation defines safe categories and severities for processing:

```text
SAFE_CATEGORIES =
    maintainability
    blueprint_compliance
    performance

SAFE_SEVERITIES =
    low
    informational
    medium
```



## 4.5 Stage 3 — Fix Backlog Drain

`drain_fix_backlog()` applies fixes through the autonomous-fix safety pipeline.

Current backlog location:

```text
overnight/fix_backlog.json
```

The implementation loads the backlog as a JSON list and returns an empty list when no valid backlog exists. 

The current backlog is therefore **not** the historical `/data/self_improver/` state model.

## 4.6 Deferred Queue

Items that cannot be safely resolved after repeated attempts are quarantined into:

```text
overnight/fix_backlog_deferred.json
```

The documented rule is three failed attempts followed by human triage. 

## 4.7 Prompt Feedback Loop

The pipeline maintains accumulated architectural lessons in:

```text
overnight/lessons_learned.json
```

`self_improver._lessons_block_for(file_path)` selects constraints applicable to the current file and injects them into future fix prompts as a `KNOWN CONSTRAINTS` block. 

This prevents repeatedly deferred issues from being retried with exactly the same context.

A discovered constraint should be distilled into a one-line imperative rule and added to the appropriate file-specific key or `_global` before retrying a deferred item. 

## 4.8 Pipeline Lock

The principal pipeline lock is:

```text
overnight/.pipeline.lock
```

It prevents concurrent pipeline runs. 

Backlog surgery has a separate operational locking mechanism described in the Critical Operational Lessons section.

---

# 5. Autonomous-Fix Safety Architecture

Every autonomous code change is treated as untrusted generated output.

## 5.1 Safety Chain

```text
LLM-generated candidate
        |
        v
Strip markdown fences
        |
        v
CoT / reasoning detection
        |
        v
AST parse validation
        |
        v
Truncation / size sanity check
        |
        v
Write original -> .orig_backup
        |
        v
Write candidate
        |
        v
Full pytest suite
        |
   +----+----+
   |         |
 FAIL       PASS
   |         |
   v         v
Restore     Remove backup
original       |
   |           v
   +------> Git commit
```

## 5.2 CoT Detector

The active CoT detector is:

```text
_looks_like_reasoning
```

Its purpose is to reject model responses that contain reasoning prose instead of executable source code.

The v11.10 hardening explicitly identifies the CoT detector as an active defense against model responses such as `"let me think..."` being treated as code. 

Anti-CoT prompting additionally instructs models to return code rather than reasoning prose and requires the first non-empty line to be valid Python. 

## 5.3 AST Gate

The autonomous-fix path uses an active `ast.parse` gate.

Its purpose is to ensure that generated Python content is syntactically valid before it is accepted as a code candidate.

The v11.10 hardening identifies the AST gate as rejecting non-Python output, including CoT prose and Markdown, before normal fix acceptance. 

AST-based or anchored surgical modification is also the preferred strategy for avoiding identifier-replacement corruption.

## 5.4 Truncation Guard

A generated fix is rejected when it is suspiciously short relative to the original file.

The current implementation explicitly rejects generated content shorter than 50% of the original file length. 

This protects against a model returning an incomplete file and accidentally deleting substantial source code.

## 5.5 Backup

Before replacing a source file, the current implementation creates:

```text
<file>.orig_backup
```

The backup exists during the pytest window.

A leftover `.orig_backup` at startup is treated as evidence of an interrupted/crashed test window and is handled by startup recovery logic. 

## 5.6 Pytest Gate

The current autonomous-fix implementation runs:

```bash
python -m pytest tests/ -q --tb=no
```

with a **120-second timeout**. 

A failed or timed-out suite causes the original file to be restored and the backup removed. 

No autonomous fix is committed after a failed test gate.

## 5.7 Git Commit Gate

Only a fix that survives the test gate reaches the commit operation.

The implementation stages the modified file and creates a local commit with an `Auto-fix: <filename>` message. 

The pipeline does **not** perform `git push`.

## 5.8 Operational Result

The v11.10 hardening documentation records:

> zero corrupted files across 90+ auto-fix commits.



This is an operational result reported by the supplied documentation, not a universal guarantee that future generated fixes cannot fail.

---

# 6. LLM Provider & Quota Architecture

## 6.1 Provider Roles

The current provider architecture is:

```text
Gemini
  |
  | pre-analysis / critique
  v
Advisory / validation

OpenRouter
  |
  | primary code-analysis generation
  v
Generated analysis / fixes

Groq
  |
  | fallback when OpenRouter is unavailable/saturated
  v
Generated analysis / fixes
```

The v11.10 operational model is **OpenRouter → Groq**, with Gemini used for pre-analysis and critique. 

## 6.2 OpenRouter

OpenRouter is protected by a hard **1000 requests/day** funded-tier limit.

The quota state is stored in:

```text
overnight/openrouter_quota.json
```

The implementation:

* counts attempts;
* persists the counter;
* rolls the counter over by UTC calendar day;
* locks OpenRouter for one hour when the hard limit is exhausted;
* and immediately force-locks for one hour when a 429 is received.  

## 6.3 OpenRouter Model Discovery

The client can discover free instruct/chat models dynamically.

Models are filtered for:

* zero prompt pricing;
* zero completion pricing;
* at least 8K context;
* instruct/chat characteristics.

Candidates are ranked by estimated parameter count and context length, with the top candidates retained in the fallback list. 

The cached model list is maintained separately from the quota state.

## 6.4 Rate Limiting

OpenRouter reads rate-limit responses and handles:

* 429 responses;
* quota exhaustion;
* unavailable models;
* model fallback;
* persisted quota state.

A 429 immediately force-locks OpenRouter for one hour rather than repeatedly probing exhausted models. 

## 6.5 Groq Fallback

Groq is used as the fallback provider when OpenRouter is saturated or unavailable.

The current client also tracks Groq rate-limit state and avoids probing models whose server-provided remaining request/token budget has already reached zero. 

Groq calls are also recorded by the budget manager. 

## 6.6 Gemini

Gemini is used for:

* initial pre-analysis;
* cross-model critique/validation.

The current Gemini API path performs explicit retry handling for 429 responses. 

Gemini is therefore not documented as the primary replacement for OpenRouter in the current v11.10 generation path.

## 6.7 Provider State

Current provider-related state includes:

```text
overnight/openrouter_quota.json
overnight/llm_cooldown.json
overnight/model_fallback_cache.json
overnight/groq_model_cache.json
```

The current v11.10 architecture documents per-provider cooldown timestamps and cached provider model lists. 

---

# 7. Human-in-the-Loop & Triage Procedures

## 7.1 Deferred-Item Rule

An item that fails three autonomous attempts is deferred for human judgment.

Human classification is:

### PHANTOM

The drain already fixed the issue.

Action:

* clear the stale entry;
* make no code change.

### REJECT

The advisory is incorrect.

Action:

* clear the entry;
* record the rationale.

### FIX

The issue is real.

Action:

* verify it still exists;
* make a surgical change;
* run tests;
* commit only if all required validation succeeds.



## 7.2 Manual-Fix Discipline

Manual fixes follow these principles:

1. Do not edit files actively being committed by the drain.
2. Verify the issue still exists.
3. Fix one issue at a time.
4. Prefer surgical modifications.
5. Run `py_compile`.
6. Run affected tests.
7. Run the full test suite.
8. Clear the deferred entry.
9. Commit with an explanatory message.

The operator playbook explicitly identifies bulk replacement as dangerous because interconnected signatures, bodies, callers, and tests can break in ways `py_compile` alone cannot detect. 

## 7.3 Manual Pre-Commit Commands

```bash
python3 -m py_compile <file>.py
python3 -m pytest tests/test_<file>*.py -q
python3 -m pytest tests/ -q
```

If any test fails, do not commit. 

## 7.4 Phantom Check

Before fixing a deferred item:

```bash
git log --oneline -- <file> | head -5
```

Recent autonomous-fix commits may mean that the advisory is already resolved. 

## 7.5 Do Not Guess About Tests

Always inspect the actual test files before selecting or interpreting a test.

Never infer test names or expected behavior from memory.

---

# 8. Operational Procedures & Runbook

## 8.1 Standard Overnight Launch

The v11.10 wrapper is the preferred operational entry point for a normal overnight run.

Example:

```bash
cd /home/swiig/Documents/blueprint
nohup bash overnight/overnight_run.sh > overnight/overnight_console.log 2>&1 &
echo "Launched PID $!"
```

The wrapper:

1. checks daily Gemini and OpenRouter budget;
2. stops if either has fewer than 60 calls remaining;
3. invokes the backlog drain;
4. writes `overnight/morning_report.md`.



The exact filesystem root is deployment-specific; the command above is the documented example.

## 8.2 Scheduling

There is **no hardcoded overnight schedule in the application**.

The operator may use:

```text
cron
systemd timer
manual execution
```

Example systemd schedule:

```text
OnCalendar=*-*-* 02:00:00
```

Example cron schedule:

```text
0 2 * * * /path/to/venv/python -m overnight.self_improver
```

These are examples only. The application itself does not mandate 02:00 or any other time. 

## 8.3 Manual Pipeline Modes

Current documented entry points include:

```bash
python -m overnight.self_improver
python -m overnight.self_improver --prefill-only
python -m overnight.self_improver --process-only
```



The `--drain-backlog` CLI is the preferred proven entry point for backlog draining and should be favored over custom wrappers that reproduce initialization logic.

## 8.4 Monitoring

Primary operator tools:

```bash
bash overnight/dashboard.sh
tail -f overnight/run_*.log
```



Current state inspection:

```bash
cat overnight/improver_state.json | jq '{fixes, reverts, last_run}'
cat overnight/openrouter_quota.json | jq '{used_today, remaining, locked_until}'
ls overnight/advisory_queue/pending/*.json | wc -l
cat overnight/fix_backlog.json | jq 'length'
git log --oneline --grep="Auto-fix" -20
```



## 8.5 Morning Routine

```bash
cat overnight/morning_report.md
bash overnight/dashboard.sh
python3 -m pytest tests/ -q
git log --oneline --since='12 hours ago'
```

Then triage new deferred items. 

## 8.6 Normal Overnight Behavior

Normal behavior includes:

* backlog decreasing in pass-boundary steps;
* approximately 1–3 commits/minute during active work;
* rejected fixes appearing as safety-gate events;
* deferred items accumulating when hard issues cannot be safely automated.

Operators should intervene when:

* the process dies;
* the budget gate trips;
* or the test suite breaks.

Otherwise, the safety gates are intended to allow the autonomous drain to continue. 

## 8.7 Locking Workflow

Two locking concepts must not be confused:

### Pipeline lock

```text
overnight/.pipeline.lock
```

Prevents concurrent pipeline runs. 

### Backlog lock

```text
overnight/backlog.lock
```

Used when deliberately performing queue surgery.

The backlog must not be manually edited while the drain is actively rewriting it.

The exact procedure is documented in Section 9.

---

# 9. Critical Operational Lessons

## The Aug 29 Hard-Won Rules

These are canonical operational rules captured from actual autonomous operation.

### 1. The Queue-File Race Condition

**Symptom:** The background drain loop overwrites manual edits made to `fix_backlog.json`.
**Resolution:** **NEVER** edit the backlog while the drain is running.
**Workflow:**

1. Run `lock_backlog` (creates `overnight/backlog.lock`)
2. The drain will now gracefully skip processing and print a warning.
3. Edit and `git commit` your changes to the JSON.
4. Run `unlock_backlog` to resume autonomous processing.

### 2. The Configuration-Class Trap

**Symptom:** Moving environment variable access into class attributes does *not* make it lazy. Class attributes are evaluated at definition/import time, meaning `.env` files loaded *after* import will be ignored.
**Resolution:** Always read environment variables inside functions/methods at runtime, or use `os.getenv` with explicit reload logic if dynamic changes are expected.

### 3. Global Replacement Corruption

**Symptom:** Blind `str.replace()` on identifiers (e.g., replacing `user` with `admin_user`) can corrupt unrelated definitions, docstrings, or comments.
**Resolution:** Use anchored, unique replacements (e.g., regex with word boundaries `\buser\b`) or AST-based refactoring for code modifications.

### 4. Duplicate Advisories Burn Quota

**Symptom:** Twin advisories in the queue cause the drain to repeatedly retry the same unfixable issue, burning API quota.
**Resolution:** Clear duplicates by matching `description`/`content`, **never** by list index (which shifts as items are removed).

### 5. `.env` Inheritance in Subprocesses

**Symptom:** A `nohup python3 ...` subprocess does not automatically inherit variables from a `.env` file unless explicitly told to.
**Resolution:** The launch script must explicitly source the environment (e.g., `set -a; source .env; set +a`) before invoking the Python process.

### 6. Silent Background Crashes

**Symptom:** A background process appears to be running (PID exists) but has silently exited its main loop due to an unhandled exception.
**Resolution:** Always use unbuffered output (`python3 -u`) and verify the process is actively logging or check its state via a dashboard command, not just `pgrep`.

### 7. Reuse Proven Entry Points

**Symptom:** Writing custom wrapper scripts that reproduce initialization logic often misses edge cases handled by the main CLI.
**Resolution:** Prefer the tested `--drain-backlog` CLI entry point over custom ad-hoc wrappers.



---

# 10. Testing & Validation Matrix

| Area                 | Implementation / Test Surface           | Purpose                                         |
| -------------------- | --------------------------------------- | ----------------------------------------------- |
| Python syntax        | `ast.parse` gate                        | Reject syntactically invalid generated Python   |
| CoT detection        | `_looks_like_reasoning`                 | Reject reasoning prose masquerading as code     |
| Truncation           | `apply_auto_fix`                        | Reject suspiciously short generated files       |
| Backup / rollback    | `.orig_backup`                          | Restore original source after failed test/crash |
| Full pytest          | `python -m pytest tests/ -q --tb=no`    | Validate candidate change before commit         |
| Test timeout         | 120-second subprocess timeout           | Prevent indefinitely hung validation            |
| Queue manager        | `test_queue_manager.py`                 | Validate queue behavior                         |
| Queue backpressure   | `test_queue_backpressure_check.py`      | Validate saturation controls                    |
| Queue stale recovery | `test_queue_stale_recovery_check.py`    | Validate stale-state recovery                   |
| Sanitization         | entropy, field-policy, redaction tests  | Validate input sanitization controls            |
| Hash chain           | concurrency, sealing, integration tests | Validate audit-chain integrity                  |
| Payload references   | `test_payload_ref_integrity_check.py`   | Validate payload/reference consistency          |
| Memory schemas       | migration checks                        | Validate memory schema state                    |
| Embeddings           | embedding and prefix tests              | Validate embedding behavior                     |
| Vector storage       | vector partition/index checks           | Validate vector partition/index requirements    |
| Model registry       | `test_model_registry.py`                | Validate model registry behavior                |
| Context stitching    | `test_context_stitcher.py`              | Validate orchestration context                  |
| Enrichment           | `test_enrichment_scheduler.py`          | Validate enrichment scheduling                  |
| IOC extraction       | `test_ioc_extractor.py`                 | Validate IOC extraction                         |
| Writeback            | Wazuh, TheHive, SO cases, pfSense tests | Validate downstream integrations                |
| Wiki sanitization    | `test_wiki_sanitization_check.py`       | Validate knowledge/wiki sanitization            |

The supplied project tree contains the corresponding tests and validation tools across these areas.  

## 10.1 Autonomous-Fix Validation Order

The autonomous fix path must follow:

1. Generate candidate.
2. Remove response fences if present.
3. Reject reasoning/CoT output.
4. Parse candidate with `ast.parse`.
5. Apply truncation sanity check.
6. Back up original file.
7. Write candidate.
8. Run full pytest suite.
9. Revert on failure/timeout.
10. Commit only on success.

The v11.10 safety hardening explicitly identifies AST, CoT, pytest, and truncation as the four primary defenses. 

---

# 11. Known Limitations & Open Issues

## 11.1 Deferred Accumulation

Hard architectural problems can accumulate in the deferred queue and require periodic human triage. 

## 11.2 Large Files

Files over approximately 800 lines may fail to process successfully when a sufficiently capable model is unavailable.

The pipeline therefore contains large-prompt routing intended to direct prompts above approximately 25K characters toward higher-capacity models. 

## 11.3 Groq Context Limits

Groq is a fallback provider and may have context limitations that affect very large prompts. 

## 11.4 Budget Exhaustion

OpenRouter has a hard 1000-RPD quota. Once exhausted, OpenRouter is locked and processing must rely on the available fallback path or await quota recovery. 

The wrapper also budget-gates execution before starting the drain. 

## 11.5 Human Architectural Judgment Remains Necessary

The autonomous pipeline is deliberately conservative. A rejected fix is not necessarily a pipeline failure; rejection is often the expected result of a safety gate.

The operator playbook explicitly frames the human operator as the architectural authority:

> The LLMs are the tradespeople — they swing the hammer. You are the General Contractor.

The architecture, safety discipline, resource control, and audit responsibility remain human responsibilities. 

## 11.6 Documentation Drift

The project still contains historical v11.9 artifacts, including:

* `LOCAL_SOC_SLM_Blueprint_v11.9.0_master.txt`;
* `LOCAL-SOC-SLM Blueprint v11.9 — Status & Resume Guide.md`;
* `docs/OVERNIGHT_PIPELINE.md`;
* `docs/OPERATIONS_RUNBOOK.md`.



Those files must not be interpreted as overriding this v11.10 consolidated state.

## 11.7 Historical Path and API Documentation Must Not Be Reintroduced

The following are explicitly **not current**:

```text
/data/self_improver/
50 RPD OpenRouter quota
overnight/advisory_queue.jsonl
async Phase A/B/C API
LoRA fine-tuning architecture
DBSCAN SelfImprover architecture
Ollama/vLLM/LM Studio overnight-provider architecture
hardcoded overnight schedule
```

The Aug 23 errata explicitly identifies these claims as stale or inaccurate relative to the corrected overnight implementation. 

---

# 12. Historical Evolution

## v11.8 — Prior Blueprint Generation

The project tree contains a `LOCAL_SOC_SLM_Blueprint_v11.8.0_master.txt` artifact. It represents an earlier architectural generation.

The supplied audit corpus does not provide sufficient evidence to reconstruct every v11.8 implementation detail. Therefore, details beyond the existence of the v11.8 artifact are **UNVERIFIED** in this consolidated document. 

## v11.9 — Aug 23 Baseline

v11.9 was the documented baseline immediately preceding the hardening work.

Its overnight documentation contained a number of architectural claims that were subsequently superseded, including:

* async Phase A/B/C;
* JSONL advisory queue;
* historical provider abstraction;
* 50-RPD quota;
* historical `/data/self_improver/` paths;
* hardcoded scheduling;
* confidence-based fix gating;
* and the obsolete SelfImprover/LoRA/DBSCAN architecture.

The Aug 23 audit explicitly identified these discrepancies and established that the `overnight/` implementation should be treated as the source of truth. 

## v11.10 — Hardened State

v11.10 replaced the stale overnight model with the current operational architecture:

* synchronous pipeline;
* `prefill_advisory_queue()`;
* `process_advisory_queue()`;
* `drain_fix_backlog()`;
* disk-backed per-file advisory queue;
* `overnight/fix_backlog.json`;
* persistent OpenRouter quota state;
* 1000-RPD funded-tier quota;
* one-hour OpenRouter lock behavior;
* OpenRouter primary generation;
* Groq fallback;
* Gemini pre-analysis and critique;
* AST gate;
* `_looks_like_reasoning` CoT detector;
* truncation guard;
* backup/rollback;
* full pytest gate;
* budget-gated wrapper;
* morning reporting;
* deferred human triage;
* and operational lessons learned from actual autonomous execution.

  

**Canonical conclusion:**

> **LOCAL-SOC-SLM is currently in v11.10 Hardened State. v11.9 is the historical baseline; v11.10 is the operational authority.**

# Operator Playbook — Lessons from the Overnight Pipeline

**v1.0 — 2026-08-26** — Operational wisdom for future LLM sessions and human operators.

---

## 1. The Overnight Drain

overnight_run.sh is a closed-loop autonomous agent: reads fix_backlog.json,
generates fixes via Gemini/OpenRouter/Groq, test-gates every fix, commits the good
ones, defers failures after 3 attempts, writes overnight/morning_report.md.

Monitor:

    bash overnight/dashboard.sh
    tail -f overnight/run_*.log

Normal behavior:
- Backlog drops in steps (at pass boundaries, not per-commit)
- ~1-3 commits/min during active work
- Every rejected fix is a safety gate working — not a failure
- Deferred queue grows as hard items get quarantined

Intervene only if: process dies, budget gate trips, or the test suite breaks.
Otherwise let it run — AST parsing, pytest rollback, and truncation guards prevent corruption.

---

## 2. Manual Triage of Deferred Items

Deferred items (overnight/fix_backlog_deferred.json) failed 3x and need human judgment.
Classify each as one of:

- PHANTOM — the drain already fixed it; the entry is stale. Clear it, no code change.
- REJECT — the advisory is wrong. Clear it with a rationale.
- FIX — a real issue. Apply it surgically, test-first.

---

## 3. The Five Iron Rules (learned the hard way)

### Rule 1 — Surgical, never bulk
Bulk string-replacement across multiple files BREAKS interdependent code
(signature + body + callers + tests) in ways py_compile cannot catch.
Fix ONE item at a time. This cost us a full revert once. Do not repeat it.

### Rule 2 — Avoid files the drain is actively committing

    git log --since='20 minutes ago' --name-only --pretty=format: | grep -v '^$' | sort -u

Do not edit those files — you will race the drain and cause conflicts.

### Rule 3 — Test-first, always
Before committing any manual fix:

    python3 -m py_compile <file>.py
    python3 -m pytest tests/test_<file>*.py -q
    python3 -m pytest tests/ -q

If anything fails, do not commit. The drain's pytest gate would reject it; so should you.

### Rule 4 — Verify the issue still exists (phantom check)
Before fixing, check whether the drain already resolved it:

    git log --oneline -- <file> | head -5

Recent Auto-fix commits on the file often mean the item is a phantom.

### Rule 5 — Guess nothing about tests
Never assume test filenames or expected behavior. Read the actual test file first.
Guessing test names gave us zero verification once. Always confirm.

---

## 4. Known Rejection Patterns

- "Combine two UPDATEs into one CASE" — Loop required for approval gates. REJECT.
- "Add audit logging to CI validation gate" — Stateless validator, not a handoff path. REJECT.
- "sys.exit() in __main__ violates AMEND-64" — AMEND-64 targets library functions, not CLI entry points. REJECT.
- "Move inline comments to docstring" — Cosmetic churn, no functional value. REJECT.

---

## 5. The Meta-Lesson

The LLMs are the tradespeople — they swing the hammer. You are the General Contractor:
you read the blueprints, inspect the foundation, and reject substandard work.

Your value is not memorizing syntax. It is:
- Designing secure, resilient, fault-tolerant architectures
- Treating the AI as an untrusted execution environment (safety gates)
- Budget and resource control
- Audit trails and compliance

The code the AI writes is the output. The architecture and safety discipline are yours.

---

## 6. Pre-Commit Checklist (manual fixes)

- File NOT in the drain's active-commit list (last 20 min)
- Issue verified to still exist (phantom check done)
- Fix is surgical — one file, one issue
- py_compile passes
- Affected tests pass
- Full suite passes
- Deferred entry cleared
- Commit message explains what + why

---

## 7. Morning Routine

1. cat overnight/morning_report.md
2. bash overnight/dashboard.sh
3. python3 -m pytest tests/ -q  (confirm green)
4. git log --oneline --since='12 hours ago'
5. Triage new deferred items per Section 2

---
v1.0 — LOCAL-SOC-SLM overnight pipeline operator lessons

---

## 8. Session Addenda — Additional Failure Modes (discovered while operating the drain)

### 8.1 Duplicate advisories in the backlog
The backlog can contain TWIN copies of the same advisory. Clearing by list index
removes one copy and leaves the twin, which the drain keeps retrying (burning quota).
Always clear by description-substring match, never by index.

### 8.2 Queue-file race condition
The drain holds the backlog in memory and rewrites the JSON after each item. Editing
fix_backlog.json or fix_backlog_deferred.json while the drain runs gets OVERWRITTEN on
its next save. Queue surgery requires: stop drain -> edit -> commit -> relaunch.

### 8.3 The config-class trap (does NOT fix module-level side effects)
Wrapping os.environ.get() in a class with class attributes still evaluates the calls at
class-definition time, which is still module load. To make env reads truly lazy, use a
cached function:

    from functools import lru_cache

    @lru_cache(maxsize=1)
    def _config():
        return {"archive_base": os.environ.get("ARCHIVE_BASE", "/archive/iocs")}

### 8.4 Global identifier replacement corrupts definitions
str.replace("ARCHIVE_BASE", "Cfg.ARCHIVE_BASE") rewrites the symbol inside its OWN
definition and inside docstrings, producing a NameError on import. NEVER globally replace
a bare identifier. Anchor replacements on full, unique lines or statements.

### 8.5 Reuse proven entry points, don't reinvent
A custom wrapper that hand-rolled budget/key init crashed silently where the battle-tested
--drain-backlog CLI worked. Prefer the CLI paths that already ran successfully overnight.

### 8.6 Silent background crashes
An empty log usually means the job crashed during startup AND stdout was buffered. Launch
with PYTHONUNBUFFERED=1, then sleep a few seconds and tail to confirm it entered its main
loop before walking away.

### 8.7 .env is not the shell environment
nohup subshells do not inherit .env automatically. Run 'set -a; source .env; set +a' in the
SAME shell before launching, or API keys arrive empty and every call returns 401.

---
*Addenda captured 2026-08-27 during hard-items triage session*

### 8.8 Module-level __getattr__ does NOT work for internal references
Defining __getattr__ in a module only intercepts EXTERNAL attribute access
(e.g. `from module import X` or `module.X`). Bare-name references INSIDE the
module's own functions (e.g. `if shutil.which(ZSTD_COMMAND)`) bypass __getattr__
and raise NameError. To lazily provide module globals that internal code AND
monkeypatch-based tests both use, prefer plain module-level names plus an
explicit _load_config() called from entry points — not __getattr__.

### 8.9 Heredocs with nested triple-quotes are brittle
A Python patch script inside a bash heredoc that contains triple-quoted strings
with its own triple-quoted strings will silently mis-parse. Always write the
patch to a temp file first (`cat > /tmp/patch.py << 'EOF'`) then execute it.

---

## 9. The Prompt Feedback Loop (lessons_learned.json)

### 9.1 Why it exists
By default the drain was STATELESS: every fix attempt used the same base prompt,
so the LLMs kept rediscovering the same traps (retention.py failed 5x on the same
monkeypatch issue). The playbook captured wisdom for humans but not for the models.

### 9.2 How it works
overnight/lessons_learned.json maps file-name substrings (plus a special "_global"
key) to constraint strings. self_improver._lessons_block_for(file_path) matches the
current file and injects a "KNOWN CONSTRAINTS" block into the fix prompt, so each
attempt carries the accumulated architectural wisdom.

### 9.3 Maintaining it
After any manual architect fix or a repeatedly-deferred item, distill the lesson into
a one-line imperative constraint and add it under the matching file key (or "_global"
if universal). Example: "do NOT remove DB_PATH; tests patch engine.quota_ledger.DB_PATH."

### 8.10 Stateless retry is the biggest hidden cost
Retrying a deferred item without new context just re-fails the same way. Always add
the discovered constraint to lessons_learned.json BEFORE re-queuing a deferred item.

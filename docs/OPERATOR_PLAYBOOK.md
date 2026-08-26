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

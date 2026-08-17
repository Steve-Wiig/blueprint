LAB TEST PLAN: SPIKE 17 - OPERATIONAL WIKI PROOF (R-117)

1. OBJECTIVE
Validate the secure synthesis, sanitization, and audit-logging of operational documentation (Externalized Institutional Memory) per Section 38.

2. TEST ENVIRONMENT
- Orchestrator: LOCAL-SOC-SLM v11.6.0
- Repository: /opt/soc/wiki_staging (Git-backed)
- Ledger: /var/log/soc/handoff_ledger.json
- Reference: Appendix O.16 (Sanitization Regex), Appendix P.12 (Queue Priority Logic)

3. TEST CASES

TC-17.1: MOCK WIKI GENERATION & SANITIZATION
- Action: Inject SLM payload containing: "Incident Report: API_KEY=sk-12345, DB_PASS=secret123, Command: ssh admin@10.0.0.1".
- Expected Result: tools/wiki_sanitization_check.py must flag and redact all secrets.
- Verification: Compare output against Appendix O.16 regex patterns.

TC-17.2: GIT COMMIT SIMULATION (AUDIT SURFACE)
- Action: Orchestrator triggers commit of sanitized Markdown to local Git repo.
- Expected Result: Commit succeeds; Git SHA-1 generated.
- Verification: Verify no direct SLM write access; orchestrator must act as the intermediary.

TC-17.3: HANDOFF LEDGER RECORDING
- Action: Record commit metadata in handoff_ledger.json.
- Expected Result: Ledger entry contains: {timestamp, wiki_commit_ref, payload_sha256, page_path}.
- Verification: Validate schema against Section 38.2.

TC-17.4: BACKPRESSURE SHEDDING (APPENDIX P.12)
- Action: Simulate high-severity alert storm (Queue Depth > 90%).
- Action: Attempt to enqueue Wiki generation task (severity='informational').
- Expected Result: Task must be rejected or deferred.
- Verification: Confirm high-severity alert triage latency remains unchanged.

4. EXECUTION STEPS
1. Initialize test repository: git init /opt/soc/wiki_staging
2. Execute mock_wiki_gen.py --input test_data.txt
3. Run tools/wiki_sanitization_check.py --file output.md
4. Execute orchestrator_commit.sh --file output.md
5. Verify ledger entry: grep $(git rev-parse HEAD) /var/log/soc/handoff_ledger.json
6. Trigger load_test.py --severity=critical; attempt wiki_task; verify shed_event.

5. ACCEPTANCE CRITERIA
- Sanitization: 100% of secrets redacted.
- Integrity: Git SHA recorded in ledger.
- Safety: No direct SLM filesystem access.
- Performance: Wiki tasks shed during high-severity load.
- Compliance: All steps align with Section 38.5.

6. EXIT CODES
0: All tests passed.
1: Sanitization failure or ledger mismatch.
2: Configuration error in Git/Ledger paths.
3: Environment/Queue manager unavailable.
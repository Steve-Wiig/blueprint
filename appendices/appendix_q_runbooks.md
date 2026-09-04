SOURCE: soc-autopilot (historical)
BLOCK:  APPENDIX Q — RUNBOOKS & FAILURE MODE
SHA256: d9f0ca8161873641
────────────────────────────────────────────────────────────────────────

Q.1 Runbook: GPU OOM during inference
Symptoms:
- Inference worker killed.
- VRAM budget exceeded.
- Queue backlog increasing.
Immediate actions:
1. Stop new worker claims.
2. Check dynamic VRAM budget output.
3. Reduce context length or concurrency.
4. Reduce embedding batch size.
5. Restart worker.
6. Record event in handoff ledger or lab evidence.
Verification:
- tools/dynamic_vram_budget_check.py passes.
- Queue stale recovery completes.
- No high-severity alerts are lost.
Q.2 Runbook: Hash-chain mismatch
Symptoms:
- tools/hash_chain_verify.py fails.
- chain_seq gap or row_hash mismatch.
Immediate actions:
1. Stop chain sealer.
2. Freeze promotion/writeback operations.
3. Identify first mismatched chain_seq.
4. Compare audit_chain against source rows.
5. Restore from known good anchor if necessary.
6. Record incident and evidence.
Verification:
- Hash-chain verifier passes on restored clean data.
- Latest chain hash is re-anchored.
Q.3 Runbook: Queue backlog emergency
Symptoms:
- Queue depth exceeds emergency_queue_depth.
- Low-severity shedding active.
Immediate actions:
1. Verify high/critical alerts are still processing.
2. Check worker concurrency and VRAM pressure.
3. Confirm shed events are auditable.
4. Delay low-severity enrichment and Wiki generation.
5. Investigate intake burst source.
Verification:
- High-severity alerts are not silently dropped.
- Shed events have shed_reason and ledger records.
- Queue depth returns below warning threshold.
Q.4 Runbook: Wiki sanitization failure
Symptoms:
- tools/wiki_sanitization_check.py fails.
- Secret pattern detected in generated Markdown.
Immediate actions:
1. Stop Wiki writer.
2. Quarantine generated draft.
3. Do not commit to Git or publish to Wiki.
4. Review sanitizer policy and prompt context.
5. Re-run Wiki generation after sanitizer fix.
Verification:
- wiki_sanitization_check.py passes.
- No secret is present in committed Markdown.
- Ledger records the failed draft or quarantine event.
Q.5 Failure Mode and Effects Analysis summary
GPU OOM:
Impact: Inference stops.
Mitigation: VRAM cap, concurrency limits.
Detection: dynamic VRAM check.
Queue burst:
Impact: Backlog, shedding.
Mitigation: severity priority, audited shedding.
Detection: queue metrics.
Worker crash:
Impact: Jobs stuck.
Mitigation: lease expiration, reaper.
Detection: stale recovery check.
Secret leakage:
Impact: Credential exposure.
Mitigation: regex + entropy sanitization.
Detection: sanitization checks.
IOC over-redaction:
Impact: Loss of triage value.
Mitigation: allowlists, field-aware quarantine.
Detection: field policy check.
Hash-chain corruption:
Impact: Audit integrity loss.
Mitigation: serialized sealer, verifier.
Detection: hash-chain check.
Prompt injection:
Impact: Unsafe model output.
Mitigation: inert memory_context, verifier.
Detection: eval metrics.
Wiki secret leak:
Impact: Secrets in documentation.
Mitigation: Section 34 sanitize before commit.
Detection: wiki_sanitization_check.
Documentation drift:
Impact: Operator confusion.
Mitigation: completeness manifest, versioned amendments.
Detection: changelog/completeness check.


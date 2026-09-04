SOURCE: soc-autopilot (historical)
BLOCK:  SECTION 38: OPERATIONAL KNOWLEDGE GENERATION
SHA256: fea9f8d266311dff
────────────────────────────────────────────────────────────────────────

38.0 Purpose
The SLM may synthesize orchestration memory into human-readable operational
documentation, such as a local Wiki, shift summaries, incident narratives,
runbook drafts, or lab-journal entries.

This is classified as Externalized Institutional Memory. It supports Loop 1
retrieval and Loop 2 deterministic playbook growth without changing model
weights.

38.1 Writeback governance
The SLM never writes directly to the filesystem, Git repository, or Wiki API.

Required flow:
1. Orchestrator selects a documentation task.
2. Orchestrator stitches memory context from handoffs, corrections,
   investigations, and accepted summaries.
3. SLM produces a structured wiki_draft payload.
4. Verifier checks schema and prohibited content.
5. Sanitizer applies Section 34 rules to the Markdown text.
6. Orchestrator commits or stores the sanitized Markdown.
7. Orchestrator records provenance in the handoff ledger.

Documentation actions:
- New incident reports, shift summaries, and lab-journal entries are
  append-only.
- Modifications to core normative runbooks, architecture documents, or
  safety policy remain draft-only and require human approval.

38.2 Git as an audit surface
If the Wiki is backed by a local Git repository:
- The orchestrator commits sanitized Markdown.
- The Git commit SHA is recorded in the handoff ledger.
- The sanitized Markdown artifact hash may be recorded as payload_sha256.
- The repository path and page path are recorded in ledger metadata.

This extends Section 37 tamper-evidence discipline to externalized
documentation without granting the SLM direct mutation rights.

38.3 VRAM and queue prioritization
Wiki generation is a background knowledge task.

Required queue policy:
- Wiki generation tasks are enqueued with severity = 'low' or
  severity = 'informational'.
- Under backpressure, Wiki generation is delayed or shed before operational
  alert triage.
- High-severity and critical alert triage must never be displaced by Wiki
  generation.
- Wiki generation must respect the dynamic VRAM budget in Section 33.

38.4 Sanitization requirements
Generated Wiki text must pass the same sanitization discipline as any other
payload entering orchestration memory or durable artifacts.

The Wiki pipeline must prevent:
- API keys,
- bearer tokens,
- passwords,
- private key material,
- session cookies,
- cloud credentials,
- high-entropy unknown tokens not explicitly allowlisted.

High-value suspicious command snippets may be preserved by reference where
policy allows, but raw unsanitized payloads must not be committed to the Wiki.

38.5 Acceptance criteria
- Wiki generation tasks pass through the Section 34 sanitization pipeline.
- No SLM process has direct write access to normative documentation.
- New Wiki pages are append-only or stored as drafts.
- Normative document edits require human approval.
- Wiki commits are recorded in the handoff ledger.
- Wiki tasks shed safely under emergency queue depth.
- Wiki generation does not displace high-severity alert triage.
- tools/wiki_sanitization_check.py passes.


SOURCE: soc-autopilot (historical)
BLOCK:  v11.6.0 AMENDMENTS TO v11.5.2 TEXT
SHA256: c1e9a02ac5b33da3
────────────────────────────────────────────────────────────────────────

AMEND-47 — Add readability layers
ADD Executive Summary, How to Read This Document, Glossary, and Documentation
Layers to the top of the master document to reduce cognitive load and provide
role-based navigation paths.

AMEND-48 — Add Section 38, Operational Knowledge Generation
ADD Section 38: Operational Knowledge Generation & Externalized Memory.
This defines the SLM lab-journalist role, Git-as-audit-ledger for Markdown
files, sanitization of generated Wiki text, and VRAM queue prioritization.

AMEND-49 — Add Appendix Q, Runbooks & Failure Modes
ADD Appendix Q: Runbooks & Failure Mode Analysis.
This provides operational response templates for GPU OOM, hash-chain
mismatch, queue backlog, Wiki sanitization failure, and related failure
classes.

AMEND-50 — Update Appendix O for Wiki CI
ADD tools/wiki_sanitization_check.py to Appendix O.
ADD O.16 Wiki sanitization tool contract.
ADD Gate 16 to the CI pipeline example.

AMEND-51 — Update Appendix P for Wiki audit metadata
ADD P.12 ledger metadata for Wiki commit reference.
This records the Git commit SHA, sanitized Markdown hash, and repository path
for externalized documentation generated under Section 38.

AMEND-52 — Update completeness manifest and checklist
ADD Section 38, Appendix Q, Appendix N R-117, and v11.6.0 AMEND-47 through
AMEND-52 to the completeness manifest and release checklist.


SOURCE: soc-autopilot (historical)
BLOCK:  v11.5 AMENDMENTS TO v11.4 TEXT
SHA256: 93540526be7fd11f
────────────────────────────────────────────────────────────────────────

AMEND-27 — Section 33.3, VRAM budget
REPLACE hardcoded VRAM budget language with dynamic hardware-aware governance.
AMEND-28 — Section 34.1, Sanitization pipeline
ADD two-pass sanitization: deterministic regex plus Shannon entropy detection.
AMEND-29 — Section 26 and Section 30
ADD asynchronous ingestion, backpressure, and triage queue governance as
Section 35.
AMEND-30 — Section 30.2
ADD time-partitioned vector memory and index lifecycle governance as Section 36.
AMEND-31 — Section 30.3
ADD hash-chained audit ledger and tamper detection as Section 37.
AMEND-32 — Appendix N
ADD research items R-107 through R-111.
AMEND-33 — Appendix O
ADD v11.5 CI tool requirements.
AMEND-34 — Appendix P
ADD production-hardening SQL, Python, and CI templates.
AMEND-35 — Full Release Checklist
ADD v11.5 production-hardening release checks.
AMEND-36 — Completeness Manifest
ADD a completeness manifest and end-of-document marker to reduce the risk of
truncation or accidental omission.


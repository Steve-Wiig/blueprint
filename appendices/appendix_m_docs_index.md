SOURCE: LOCAL_SOC_SLM_Blueprint_v11.6.0_master.txt
BLOCK:  APPENDIX M — OPEN SOURCE SECURITY SOFTWARE
SHA256: 4b53ed94b3caef3f
────────────────────────────────────────────────────────────────────────

VERSION: v11.3 / v11.4-amended / v11.5.2-restored / v11.6-amended
STATUS: Human-readable reference appendix
PURPOSE:
Provide maintainers, analysts, and developers with a readable index of the
open-source security platforms integrated by the Local SOC SLM Blueprint,
including primary documentation, API references, integration boundaries,
credential guidance, and safety constraints.
This appendix does not replace the technical contracts in Sections 20, 24, 26,
30, 31, 32, 33, 34, 35, 36, 37, and 38. It exists to make external software
documentation easier to locate, review, and operate safely.
--------------------------------------------------------------------------------
M.0 HOW TO USE THIS APPENDIX
--------------------------------------------------------------------------------
This appendix is organized around the following questions:
1. What open-source tools are integrated?
2. Where is their official documentation?
3. Where is their API or programmatic interface documentation?
4. What does the Local SOC SLM Enrichment Engine read from them?
5. What does the Local SOC SLM Enrichment Engine write or propose?
6. What actions require human approval?
7. What credentials and access levels should be used?
The blueprint follows a strict safety model:
Read broadly, draft carefully, mutate only with approval.
All state-changing operations remain approval-gated per Section 24.
Examples of approval-gated operations:
apply_pfsense_alias
push_blocklist
Wazuh rule proposal acceptance
Suricata rule reload
TheHive operational case mutation
Normative documentation mutation [v11.6]
--------------------------------------------------------------------------------
M.1 PRIMARY INTEGRATED SECURITY PLATFORMS
--------------------------------------------------------------------------------
WAZUH
Role:
Endpoint security, log collection, alerting, rule proposals.
Primary documentation:
https://documentation.wazuh.com/current/index.html
API / programmatic documentation:
https://documentation.wazuh.com/current/user-manual/api/reference.html
Integration notes:
- Used for alert intake, enrichment context, and draft rule/proposal
writeback.
- Use a read-only Wazuh API user for intake and enrichment.
- Do not grant the engine permission to apply rules or restart Wazuh.
- Wazuh rule proposals should be stored as drafts and promoted only after
human approval and CI validation.
Safety rule:
The engine may propose Wazuh changes, but it must not apply them
autonomously.
SECURITY ONION
Role:
Network security monitoring, alert correlation, OpenSearch-based telemetry.
Primary documentation:
https://docs.securityonion.net/en/stable/
API / programmatic documentation:
OpenSearch API reference:
https://opensearch.org/docs/latest/api-reference/
Integration notes:
- Security Onion provides the SOC telemetry environment.
- Large payloads remain in OpenSearch.
- PostgreSQL stores orchestration state and references only.
- Use read-only OpenSearch credentials for query operations.
Safety rule:
Security Onion/OpenSearch is the raw telemetry store. Postgres is the
orchestration memory store.
SURICATA
Role:
NIDS/IPS alerting and EVE JSON event output.
Primary documentation:
https://docs.suricata.io/en/latest/
API / programmatic documentation:
EVE JSON output:
https://docs.suricata.io/en/latest/output/eve/eve-json-format.html
Unix socket:
https://docs.suricata.io/en/latest/unix-socket.html
Integration notes:
- Suricata is consumed primarily through EVE JSON intake.
- It is not assumed to expose a native REST API.
- Rule reloads and rule application are not automatic.
- Proposed Suricata rules should pass CI and human review before deployment.
Safety rule:
Suricata rule changes are defense changes and must be approval-gated.
THEHIVE
Role:
Case management, observables, analyst workflow.
Primary documentation:
https://docs.thehive.io/
API / programmatic documentation:
https://docs.thehive.io/thehive/api/
Integration notes:
- Used for case creation/update, observable linkage, and handoff visibility.
- The engine can draft enrichment summaries and observables.
- Case creation or updates should be controlled by the orchestrator and
gated by policy.
- TheHive is a useful writeback target for handoff visibility, but it must
not become an autonomous enforcement channel.
Safety rule:
TheHive writes are case-management actions, not autonomous defensive
actions.
PFSENSE
Role:
Firewall, alias tables, network blocking, defensive enforcement.
Primary documentation:
https://docs.netgate.com/pfsense/en/latest/
API / programmatic documentation:
https://docs.netgate.com/pfsense/en/latest/api/index.html
v11.4 verification note:
Stock pfSense CE/Plus may not provide the required REST API out of the box.
Lab verification (R-001) may require the community-maintained
pfSense-pkg-RESTAPI package or equivalent.
API keys must be strictly scoped to alias read/draft endpoints where
possible, for example:
/api/v2/firewall/alias
Interface mutation, package mutation, reboot, and service control endpoints
must be denied.
Integration notes:
- Used for querying tables and drafting aliases/blocklists.
- Applying aliases or pushing blocklists requires approval.
- Use read-only or limited-privilege credentials for table queries.
- Alias creation should be drafted, not applied.
- apply_pfsense_alias and push_blocklist are approval-required actions.
Safety rule:
pfSense mutations are high-impact defensive actions and must remain
human-approved.
--------------------------------------------------------------------------------
M.2 SUPPORTING DATA AND ORCHESTRATION PLATFORMS
--------------------------------------------------------------------------------
POSTGRESQL
Role:
Persistent orchestration memory: IOCs, handoffs, investigations,
corrections, model registry.
Primary documentation:
https://www.postgresql.org/docs/current/
API / reference documentation:
SQL reference:
https://www.postgresql.org/docs/current/sql.html
Notes:
- Stores orchestration state, not raw telemetry.
- handoffs and corrections are append-only.
- The engine role should have only the required SELECT/INSERT privileges.
- UPDATE/DELETE should not be granted on audit tables.
PGVECTOR
Role:
Vector similarity search for semantic recall.
Primary documentation:
https://github.com/pgvector/pgvector
API / reference documentation:
https://github.com/pgvector/pgvector#readme
Notes:
- Stores embeddings for past cases, corrections, and accepted proposals.
- Used with nomic-embed-text 768-dimensional embeddings.
- Top-k recall is injected as inert <memory_context>.
- Index choice is benchmark-selected: sequential scan, HNSW, or IVFFlat.
- HNSW is preferred for dynamic inserts once indexing becomes necessary.
- Time-partitioned index lifecycle is governed by Section 36.
SQLITE
Role:
Ephemeral working memory, quota ledger, task state.
Primary documentation:
https://www.sqlite.org/docs.html
API / reference documentation:
https://www.sqlite.org/lang.html
Notes:
- File-based and ephemeral.
- Not used for durable audit data.
- Local process access only.
OPENSEARCH
Role:
Raw telemetry, alert/document storage, large payload storage.
Primary documentation:
https://opensearch.org/docs/latest/
API / reference documentation:
https://opensearch.org/docs/latest/api-reference/
Notes:
- Raw logs and large artifacts remain here.
- Postgres stores payload_ref pointers only.
- Use read-only query credentials for enrichment operations.
NOMIC-EMBED-TEXT
Role:
Local embedding model for semantic memory.
Primary documentation:
https://huggingface.co/nomic-ai/nomic-embed-text-v1
v11.4/v11.5.1 verification note:
Validate exact model artifact, revision/hash, dimension, normalization,
prefix behavior, and prefix idempotency before production use.
If the selected nomic-family model requires instruction prefixes, enforce
them via a non-bypassable idempotent wrapper:
search_document: <document text>
search_query: <query text>
Notes:
- Used for 768-dimensional embeddings in pgvector.
- Embedding worker may co-reside on the inference GPU if VRAM budget passes.
- Embedding content is treated as untrusted context and still passes the
verifier gate.
GIT / LOCAL DOCUMENTATION REPOSITORY [v11.6]
Role:
Externalized institutional memory for sanitized operational Wiki pages,
shift summaries, incident narratives, and drafted runbooks.
Primary documentation:
https://git-scm.com/doc
Integration notes:
- The orchestrator commits sanitized Markdown.
- The SLM does not have direct write access.
- Commits are recorded in the handoff ledger.
- Normative document edits require human approval.
Safety rule:
Wiki generation is append-only or draft-only and must be sanitized before
commit.
--------------------------------------------------------------------------------
M.3 READABLE INTEGRATION BOUNDARY MAP
--------------------------------------------------------------------------------
Wazuh:
Read:
Alerts, agents, rules, enrichment context.
Draft:
Rule proposals, decoder/list proposals.
Apply / Mutate:
Do not apply rule changes automatically.
Approval required:
Yes.
Security Onion / OpenSearch:
Read:
Alerts, events, dashboards, stored objects.
Draft:
None by default.
Apply / Mutate:
No direct mutation of raw telemetry.
Approval required:
Not applicable.
Suricata:
Read:
EVE JSON, alerts, flow/metadata events.
Draft:
Rule proposals.
Apply / Mutate:
Do not reload rules automatically.
Approval required:
Yes.
TheHive:
Read:
Cases, observables, tasks, case status.
Draft:
Case summaries, observables, enrichment notes.
Apply / Mutate:
Case creation/update must be controlled.
Approval required:
Yes, for operational writes.
pfSense:
Read:
Alias tables, firewall state, interface info.
Draft:
Alias drafts, blocklist drafts.
Apply / Mutate:
Apply alias, push blocklist.
Approval required:
Yes.
PostgreSQL:
Read:
Orchestration memory, handoffs, corrections.
Draft:
New rows via approved adapters.
Apply / Mutate:
Schema changes only through migration/CI.
Approval required:
Yes for schema changes.
SQLite:
Read:
Quota ledger, task state.
Draft:
Task updates.
Apply / Mutate:
Local process-managed.
Approval required:
No, ephemeral only.
Local Wiki / Git documentation repository [v11.6]:
Read:
Existing operational documentation.
Draft:
New append-only pages, lab journal entries, incident narratives.
Apply / Mutate:
Normative document edits require human approval.
Approval required:
Yes for normative changes.
--------------------------------------------------------------------------------
M.4 API AND SERVICE ENDPOINT WORKSHEET
--------------------------------------------------------------------------------
Use this worksheet to record local lab endpoints. Defaults are shown only as
common examples. Adjust for your environment.
Wazuh API:
Typical local endpoint:
https://127.0.0.1:55000
Default port:
55000
Transport:
HTTPS
Lab value:
<fill in>
Access level:
Read-only
Security Onion / OpenSearch:
Typical local endpoint:
https://127.0.0.1:9200
Default port:
9200
Transport:
HTTPS
Lab value:
<fill in>
Access level:
Read-only
TheHive:
Typical local endpoint:
http://127.0.0.1:9000
Default port:
9000
Transport:
HTTP/HTTPS
Lab value:
<fill in>
Access level:
Scoped API key
pfSense API / Web UI:
Typical local endpoint:
https://127.0.0.1 or firewall IP
Default port:
443
Transport:
HTTPS
Lab value:
<fill in>
Access level:
Least privilege
PostgreSQL:
Typical local endpoint:
127.0.0.1:5432
Default port:
5432
Transport:
TCP
Lab value:
<fill in>
Access level:
Limited engine role
SQLite quota ledger:
Typical local endpoint:
engine/quota.db
Default port:
Not applicable
Transport:
File
Lab value:
<fill in>
Access level:
Local process only
Embedding worker:
Typical local endpoint:
Local inference endpoint
Default port:
Varies
Transport:
Local
Lab value:
<fill in>
Access level:
Internal only
Operational recommendation:
For a single-node lab, bind APIs to localhost or a dedicated management
interface whenever possible.
Do not expose Wazuh API, OpenSearch, TheHive, PostgreSQL, or pfSense management
endpoints to untrusted networks.
--------------------------------------------------------------------------------
M.5 CREDENTIAL AND ACCESS GUIDANCE
--------------------------------------------------------------------------------
Wazuh:
Recommended credential type:
API user
Recommended access level:
Read-only for alerts/rules/agents
Notes:
No manager mutation rights.
Security Onion / OpenSearch:
Recommended credential type:
Service account
Recommended access level:
Read-only query access
Notes:
Avoid index deletion rights.
TheHive:
Recommended credential type:
API key or service account
Recommended access level:
Scoped case/observable access
Notes:
Use minimal permissions.
pfSense:
Recommended credential type:
API/admin account
Recommended access level:
Read-only where possible; separate approval account
Notes:
Do not give engine unrestricted firewall admin.
PostgreSQL:
Recommended credential type:
Database role
Recommended access level:
SELECT, INSERT where needed
Notes:
No UPDATE/DELETE on append-only tables.
SQLite:
Recommended credential type:
File permissions
Recommended access level:
Local process only
Notes:
Not network exposed.
PostgreSQL role guidance:
For the orchestration memory database, the engine role should follow the
append-only policy in Section 30:
handoffs and corrections are append-only.
The engine role should have INSERT and SELECT only.
UPDATE and DELETE should not be granted on audit tables.
Retention should be handled by partition drop/archive procedures, not ad hoc
row deletion.
--------------------------------------------------------------------------------
M.6 API SAFETY MATRIX
--------------------------------------------------------------------------------
Read alerts:
Examples:
Wazuh alerts, Suricata EVE, OpenSearch queries.
Allowed:
Yes.
Gating:
Read-only credentials.
Read cases:
Examples:
TheHive case lookup.
Allowed:
Yes.
Gating:
Scoped API key.
Query firewall tables:
Examples:
pfSense alias/table lookup.
Allowed:
Yes.
Gating:
Read-only or limited privilege.
Draft summary:
Examples:
SLM enrichment summary.
Allowed:
Yes.
Gating:
Verifier validation.
Draft alias:
Examples:
pfSense alias draft.
Allowed:
Yes.
Gating:
Stored as draft.
Draft rule:
Examples:
Wazuh/Suricata rule proposal.
Allowed:
Yes.
Gating:
CI + human approval.
Apply firewall alias:
Examples:
pfSense alias apply.
Allowed:
Only with approval.
Gating:
Approval token + audit ledger.
Push blocklist:
Examples:
Firewall/network blocklist push.
Allowed:
Only with approval.
Gating:
Approval token + audit ledger.
Modify raw telemetry:
Examples:
Delete/alter OpenSearch logs.
Allowed:
No.
Gating:
Not allowed.
Autonomous model tuning:
Examples:
Online weight updates.
Allowed:
No.
Gating:
Prohibited by Section 31.
Draft Wiki page [v11.6]:
Examples:
SLM incident narrative, shift summary, lab journal.
Allowed:
Yes.
Gating:
Verifier validation + Section 34 sanitization + ledger recording.
Update normative documentation [v11.6]:
Examples:
Architecture document, safety contract, core runbook.
Allowed:
Only with approval.
Gating:
Draft PR + human merge.
--------------------------------------------------------------------------------
M.7 DOCUMENTATION MIRROR RECOMMENDATIONS
--------------------------------------------------------------------------------
For lab resilience and offline operation, maintain a local documentation mirror.
Suggested directory layout:
docs/vendor/
├── wazuh/
├── security-onion/
├── suricata/
├── thehive/
├── pfsense/
├── opensearch/
├── postgresql/
├── pgvector/
└── sqlite/
Minimum mirrored content:
- Primary user guide
- API reference
- Authentication documentation
- Backup/restore documentation
- Upgrade notes
- Security hardening guide
- Relevant release notes for the deployed version
Recommended naming convention:
docs/vendor/<component>/<component>-<version>-<doc-type>.pdf
docs/vendor/<component>/<component>-<version>-api.html
docs/vendor/<component>/<component>-<version>-release-notes.md
--------------------------------------------------------------------------------
M.8 HUMAN READABILITY QUICK REFERENCE
--------------------------------------------------------------------------------
What the system reads:
- Wazuh alerts
- Suricata EVE JSON
- Security Onion/OpenSearch alert and event data
- TheHive case and observable context
- pfSense tables/status, where permitted
- PostgreSQL orchestration memory
- pgvector similar-case embeddings
What the system drafts:
- Enrichment summaries
- Triage recommendations
- Wazuh rule proposals
- Suricata rule proposals
- TheHive case notes/observables
- pfSense alias drafts
- Earlier-alerting rule proposals
- Defense improvement proposals
- Operational Wiki pages [v11.6]
- Shift summaries [v11.6]
- Incident narratives [v11.6]
- Runbook drafts [v11.6]
What the system never does autonomously:
- Apply firewall changes
- Push blocklists
- Modify Wazuh rules
- Reload Suricata rules
- Alter raw telemetry
- Perform online model weight tuning
- Delete audit ledger entries
- Promote adapters without CI, replay-mix evaluation, canary, and approval
- Shed high-severity alerts silently
- Insert unsanitized telemetry into PostgreSQL
- Double-prefix embedding inputs
- Allow concurrent hash-chain writers to corrupt audit order
- Write directly to Wiki or normative documentation without orchestrator
  validation and sanitization [v11.6]
--------------------------------------------------------------------------------
M.9 MINIMAL READING LIST FOR NEW MAINTAINERS
--------------------------------------------------------------------------------
1. Wazuh Overview and Alerting
https://documentation.wazuh.com/current/index.html
2. Wazuh API Reference
https://documentation.wazuh.com/current/user-manual/api/reference.html
3. Security Onion Documentation
https://docs.securityonion.net/en/stable/
4. OpenSearch API Reference
https://opensearch.org/docs/latest/api-reference/
5. Suricata EVE JSON Output
https://docs.suricata.io/en/latest/output/eve/eve-json-format.html
6. TheHive API Documentation
https://docs.thehive.io/thehive/api/
7. pfSense API Documentation
https://docs.netgate.com/pfsense/en/latest/api/index.html
8. PostgreSQL Documentation
https://www.postgresql.org/docs/current/
9. pgvector README
https://github.com/pgvector/pgvector
10. SQLite Documentation
https://www.sqlite.org/docs.html
--------------------------------------------------------------------------------
M.10 DOCUMENTATION ACCEPTANCE CRITERIA
--------------------------------------------------------------------------------
Before considering the documentation appendix complete for a deployment:
- All listed components have version-pinned documentation links.
- API documentation has been verified against the deployed version.
- Authentication methods are documented for each API.
- Read-only credentials have been created and tested.
- State-changing actions are mapped to approval gates.
- Local endpoint worksheet has been filled in for the lab environment.
- Offline documentation mirror has been archived.
- Appendix M links are reachable from the lab workstation.
- Any deprecated or moved documentation links have been replaced with
archived copies.
--------------------------------------------------------------------------------
M.11 COMPACT LINK INDEX
--------------------------------------------------------------------------------
Wazuh:
Docs:
https://documentation.wazuh.com/current/index.html
API:
https://documentation.wazuh.com/current/user-manual/api/reference.html
Security Onion:
Docs:
https://docs.securityonion.net/en/stable/
API surface:
https://opensearch.org/docs/latest/api-reference/
Suricata:
Docs:
https://docs.suricata.io/en/latest/
EVE JSON:
https://docs.suricata.io/en/latest/output/eve/eve-json-format.html
Unix socket:
https://docs.suricata.io/en/latest/unix-socket.html
TheHive:
Docs:
https://docs.thehive.io/
API:
https://docs.thehive.io/thehive/api/
pfSense:
Docs:
https://docs.netgate.com/pfsense/en/latest/
API:
https://docs.netgate.com/pfsense/en/latest/api/index.html
OpenSearch:
Docs:
https://opensearch.org/docs/latest/
API:
https://opensearch.org/docs/latest/api-reference/
PostgreSQL:
Docs:
https://www.postgresql.org/docs/current/
SQL:
https://www.postgresql.org/docs/current/sql.html
pgvector:
Docs:
https://github.com/pgvector/pgvector
README:
https://github.com/pgvector/pgvector#readme
SQLite:
Docs:
https://www.sqlite.org/docs.html
SQL:
https://www.sqlite.org/lang.html
nomic-embed-text:
Model:
https://huggingface.co/nomic-ai/nomic-embed-text-v1
--------------------------------------------------------------------------------
M.12 VERIFICATION NOTES
--------------------------------------------------------------------------------
All documentation links, API paths, package names, and endpoint behaviors are
version-dependent and must be pinned, mirrored, and validated in the lab before
implementation.
Specific caution areas:
pfSense:
API availability may depend on version, package, or plugin.
Endpoint paths and auth mechanisms must be validated.
Do not assume stock pfSense CE/Plus provides the required REST API.
Wazuh:
RBAC and API behavior must be validated against the deployed version.
Security Onion:
OpenSearch access may be mediated by Security Onion.
Direct OpenSearch API use must be validated.
TheHive:
API behavior may differ across major versions.
Permission model must be validated.
Suricata:
EVE JSON schema and intake behavior depend on version and config.
Embedding model:
Prefix requirements, normalization, dimension behavior, and prefix
idempotency must be validated against the exact model artifact used.


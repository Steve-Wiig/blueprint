# LAB TEST PLAN: SPIKE 2 - READ-ONLY CREDENTIAL PROOF (R-002, R-003, R-004)

## 1. OBJECTIVE
Validate that the LOCAL-SOC-SLM engine can interact with external security appliances (Wazuh, Security Onion, TheHive) using strictly read-only credentials, ensuring no destructive API calls are permitted.

## 2. PREREQUISITES
- Isolated Lab Network (VLAN 99) with no egress to production.
- Baseline hardware: 16GB VRAM GPU, 64GB DDR5 RAM.
- Credentials: 
  - Wazuh: `AKIAEXAMPLE_WAZUH_RO`
  - OpenSearch: `AKIAEXAMPLE_OS_RO`
  - TheHive: `AKIAEXAMPLE_TH_RO`
- Tools: `curl`, `jq`, `python3` (with `requests` library).

## 3. TEST STEPS

### Phase 1: Wazuh API Read-Only Validation
1. Initialize connection: `curl -k -u AKIAEXAMPLE_WAZUH_RO:password -X GET "https://wazuh-manager:55000/"`
2. Attempt GET request for agent list: `curl -k -u AKIAEXAMPLE_WAZUH_RO:password -X GET "https://wazuh-manager:55000/agents?pretty"`
3. Attempt DELETE request (Negative Test): `curl -k -u AKIAEXAMPLE_WAZUH_RO:password -X DELETE "https://wazuh-manager:55000/agents/001"`
4. Verify response code 403/401 for DELETE.

### Phase 2: OpenSearch/Security Onion Read-Only Validation
1. Query index metadata: `curl -k -u AKIAEXAMPLE_OS_RO:password -X GET "https://so-node:9200/_cat/indices"`
2. Execute search query: `curl -k -u AKIAEXAMPLE_OS_RO:password -X POST "https://so-node:9200/wazuh-alerts-*/_search" -d '{"query": {"match_all": {}}}'`
3. Attempt index deletion (Negative Test): `curl -k -u AKIAEXAMPLE_OS_RO:password -X DELETE "https://so-node:9200/wazuh-alerts-001"`
4. Verify response code 403.

### Phase 3: TheHive Read-Only Validation
1. Fetch case list: `curl -k -H "Authorization: Bearer AKIAEXAMPLE_TH_RO" -X GET "https://thehive:9000/api/v1/case"`
2. Attempt case creation (Negative Test): `curl -k -H "Authorization: Bearer AKIAEXAMPLE_TH_RO" -X POST "https://thehive:9000/api/v1/case" -d '{"title": "Test", "description": "Test"}'`
3. Verify response code 403.

## 4. PASS/FAIL CRITERIA
- PASS: All GET requests return 200 OK; all DELETE/POST/PUT requests return 403 Forbidden.
- FAIL: Any destructive request returns 200 OK or 201 Created.
- FAIL: Any GET request returns 401/403 (Credential misconfiguration).

## 5. EXECUTION COMMANDS
- Run validation script: `python3 ./scripts/verify_ro_perms.py --target wazuh --creds ./secrets/wazuh.json`
- Log output: `tee ./logs/spike2_validation.log`
- Exit code 0: Success.
- Exit code 1: Permission violation detected.
- Exit code 2: Configuration error (API unreachable).

## 6. LAB-VERIFY NOTES
- [LAB-VERIFY] Confirm if Security Onion OpenSearch proxy intercepts DELETE requests or if they reach the underlying OpenSearch cluster.
- [LAB-VERIFY] Confirm TheHive 5.x RBAC granularity for 'case-read' vs 'case-write'.
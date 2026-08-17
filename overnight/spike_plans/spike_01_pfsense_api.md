# Spike 1: Firewall API Feasibility (R-001) - Lab Test Plan

## 1. Objective
Validate the integration feasibility between the LOCAL-SOC-SLM Enrichment Engine and the pfSense firewall API. Determine if the environment supports read-only alias management and draft-state validation without autonomous mutation.

## 2. Prerequisites
- Hardware: 16GB VRAM NVIDIA GPU, 64GB DDR5 RAM.
- Software: pfSense CE/Plus instance, `pfSense-pkg-RESTAPI` (v0.6.0+), Python 3.10+ environment.
- Credentials: API Key with `alias-read`, `alias-create`, `alias-update` (scoped to test-only aliases).
- Network: Isolated lab VLAN for firewall management traffic.

## 3. Test Procedure
1. Initialize the local environment: `export SOC_ENV=LAB_TEST_R001`.
2. Verify API connectivity: `curl -k -H "Authorization: AKIAEXAMPLE" https://pfsense-lab/api/v1/firewall/alias`.
3. Execute `test_api_connectivity.py` to confirm 200 OK response.
4. Create a test alias: `python3 scripts/firewall_sync.py --action create --name SOC_TEST_BLOCK --type host --value 192.0.2.1`.
5. Verify alias existence via GET request: `curl -k -H "Authorization: AKIAEXAMPLE" https://pfsense-lab/api/v1/firewall/alias/SOC_TEST_BLOCK`.
6. Attempt unauthorized mutation (e.g., system reboot): `python3 scripts/firewall_sync.py --action reboot`.
7. Verify audit log entry in `logs/soc_audit.log`.
8. Perform cleanup: `python3 scripts/firewall_sync.py --action delete --name SOC_TEST_BLOCK`.

## 4. Pass/Fail Criteria
- PASS: API returns 200/201 for valid read/write operations.
- PASS: Unauthorized mutation attempts return 403 Forbidden.
- PASS: SQLite working state reflects the alias creation status.
- FAIL: API returns 500 Internal Server Error or 401 Unauthorized.
- FAIL: Any autonomous mutation occurs without explicit manual trigger.
- FAIL: Memory usage exceeds 4GB during API polling cycles.

## 5. Execution Commands
- `python3 -m pytest tests/test_firewall_api.py --verbose`
- `grep "ERROR" logs/soc_audit.log` (Must return 0 matches for valid operations)
- `cat /var/log/soc_firewall_sync.json` (Verify schema compliance)

## 6. Exit Codes
- 0: Success, API surface verified.
- 1: Failure, API surface incompatible or security boundary breached.
- 2: Configuration error, credentials or network unreachable.
- 3: Environment missing, hardware baseline not met.

## 7. Notes
- [LAB-VERIFY] Confirm if `pfSense-pkg-RESTAPI` supports atomic alias updates.
- [LAB-VERIFY] Ensure `nominc-embed-text` is not invoked during firewall sync to prevent latency spikes.
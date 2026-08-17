import argparse
import json
import logging
import sys
import requests
from datetime import datetime

# LOCAL-SOC-SLM Blueprint v11.6.0 - Appendix Q.4
# Security Onion Case Writeback Adapter

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def sanitize_input(data):
    if not isinstance(data, dict):
        return {}
    return {str(k)[:64]: str(v)[:2048] for k, v in data.items()}

def write_to_ledger(payload_ref, case_id):
    try:
        with open("handoffs_ledger.log", "a") as f:
            f.write(f"{datetime.utcnow().isoformat()} | {payload_ref} | {case_id}\n")
    except IOError:
        sys.exit(2)

def create_case(api_url, api_key, payload, draft_mode):
    sanitized = sanitize_input(payload)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    
    if draft_mode:
        logging.info(f"DRAFT MODE: Payload sanitized: {sanitized}")
        return "DRAFT_ID_000"

    try:
        response = requests.post(f"{api_url}/api/cases", json=sanitized, headers=headers, timeout=10)
        response.raise_for_status()
        case_id = response.json().get("id")
        return case_id
    except Exception as e:
        logging.error(f"API Failure: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="SO Case Writeback Adapter")
    parser.add_argument("--url", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--payload", required=True, help="JSON string of case data")
    parser.add_argument("--draft", action="store_true")
    
    args = parser.parse_args()

    try:
        data = json.loads(args.payload)
    except json.JSONDecodeError:
        sys.exit(2)

    case_id = create_case(args.url, args.key, data, args.draft)
    
    if not args.draft:
        write_to_ledger(data.get("ref", "N/A"), case_id)
    
    print(f"SUCCESS: {case_id}")
    sys.exit(0)

if __name__ == "__main__":
    main()
import argparse
import sys
import requests
import json
from sanitization_pipeline import sanitize_case_data

def main():
    parser = argparse.ArgumentParser(description="TheHive Case Writeback Adapter v11.6.0")
    parser.add_argument("--case-data", required=True, help="JSON string of case data")
    parser.add_argument("--api-key", required=True, help="TheHive API Key")
    parser.add_argument("--url", required=True, help="TheHive Base URL")
    parser.add_argument("--mode", choices=['draft', 'live'], default='draft', help="Adapter mode")
    
    args = parser.parse_args()

    try:
        raw_data = json.loads(args.case_data)
    except json.JSONDecodeError:
        sys.exit(2)

    sanitized_data = sanitize_case_data(raw_data)
    
    if args.mode == 'draft':
        sanitized_data['status'] = 'Open'
        sanitized_data['tags'] = sanitized_data.get('tags', []) + ['draft-mode']

    headers = {
        "Authorization": f"Bearer {args.api_key}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(
            f"{args.url}/api/case",
            json=sanitized_data,
            headers=headers,
            timeout=30
        )
        
        if response.status_code in [200, 201]:
            case_id = response.json().get('id')
            with open("handoff_log.txt", "a") as f:
                f.write(f"REF:{case_id}|STATUS:SUCCESS|MODE:{args.mode}\n")
            sys.exit(0)
        else:
            sys.exit(1)
            
    except requests.exceptions.RequestException:
        sys.exit(3)

if __name__ == "__main__":
    main()
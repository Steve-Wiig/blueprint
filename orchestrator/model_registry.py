import sqlite3
import hashlib
import json
import yaml
import sys
from typing import Dict, Optional

class ModelRegistryClient:
    def __init__(self, db_path: str, routing_config_path: str):
        self.db_path = db_path
        try:
            with open(routing_config_path, 'r') as f:
                self.routing_config = yaml.safe_load(f)
        except Exception:
            raise ValueError(f"CONFIG ERROR: Could not load routing config: {routing_config_path}")

    def get_adapter(self, task_type: str) -> Dict:
        adapter_id = self.routing_config.get(task_type)
        if not adapter_id:
            return None  # Adapter not found

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT adapter_id, adapter_sha256, status FROM model_registry WHERE adapter_id = ?",
                (adapter_id,)
            )
            row = cursor.fetchone()
            conn.close()

            if not row:
                return None  # Adapter not found

            aid, sha, status = row
            
            if status not in ['canary', 'active', 'retired']:
                return None  # Adapter not found
            
            return {"adapter_id": aid, "sha256": sha, "status": status}
        except Exception:
            return None  # Adapter not found

    def verify_integrity(self, adapter_data: Dict, file_path: str) -> bool:
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest() == adapter_data['sha256']
        except FileNotFoundError:
            return None  # Adapter not found

if __name__ == "__main__":
    # Example usage for LOCAL-SOC-SLM v11.6.0
    client = ModelRegistryClient("orchestration.db", "routing.json")
    adapter = client.get_adapter("triage_analysis")
    
    if adapter['status'] == 'retired':
        sys.exit(1)
        
    if not client.verify_integrity(adapter, f"models/{adapter['adapter_id']}.bin"):
        sys.exit(1)
        
    sys.exit(0)
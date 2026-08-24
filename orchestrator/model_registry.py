import sqlite3
import hashlib
import yaml
from typing import Dict, Optional


class ModelRegistryClient:
    """Client for interacting with the model registry database.

    Manages connections to a SQLite database containing model adapter metadata
    and provides methods for retrieving adapter information and verifying
    file integrity against stored SHA256 hashes.

    Attributes:
        db_path: Path to the SQLite database file.
        routing_config: Dictionary mapping task types to adapter IDs.
    """

    def __init__(self, db_path: str, routing_config_path: str):
        """Initialize the ModelRegistryClient.

        Args:
            db_path: Path to the SQLite database file.
            routing_config_path: Path to the YAML routing configuration file.

        Raises:
            ValueError: If the routing configuration file cannot be loaded.
        """
        self.db_path = db_path
        self._conn: sqlite3.Connection = None
        try:
            with open(routing_config_path, 'r') as f:
                self.routing_config = yaml.safe_load(f)
        except Exception:
            raise ValueError(f"CONFIG ERROR: Could not load routing config: {routing_config_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create a database connection.

        Returns:
            An active sqlite3.Connection with row_factory set to sqlite3.Row.
        """
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def get_adapter(self, task_type: str) -> Optional[Dict]:
        """Retrieve adapter information for a given task type.

        Args:
            task_type: The task type to look up in the routing configuration.

        Returns:
            A dictionary containing adapter_id, sha256, and status if found
            and the status is one of 'canary', 'active', or 'retired'.
            Returns None if no adapter is configured for the task type,
            the adapter is not found in the registry, or the status is invalid.
        """
        adapter_id = self.routing_config.get(task_type)
        if not adapter_id:
            return None

        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT adapter_id, adapter_sha256, status FROM model_registry WHERE adapter_id = ?",
                (adapter_id,)
            )
            row = cursor.fetchone()

            if not row:
                return None

            if row['status'] not in ['canary', 'active', 'retired']:
                return None

            return {"adapter_id": row['adapter_id'], "sha256": row['adapter_sha256'], "status": row['status']}
        except Exception:
            return None

    def verify_integrity(self, adapter_data: Dict, file_path: str) -> bool:
        """Verify the SHA256 integrity of an adapter file.

        Args:
            adapter_data: Dictionary containing the expected 'sha256' hash.
            file_path: Path to the adapter binary file to verify.

        Returns:
            True if the file's SHA256 matches the expected hash, False otherwise.
            Returns None if the file is not found.
        """
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest() == adapter_data['sha256']
        except FileNotFoundError:
            return None

    def close(self):
        """Close the database connection if open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        """Enter the runtime context for the client.

        Returns:
            The ModelRegistryClient instance.
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the runtime context and close the database connection.

        Args:
            exc_type: Exception type if an exception was raised.
            exc_val: Exception value if an exception was raised.
            exc_tb: Exception traceback if an exception was raised.
        """
        self.close()

if __name__ == "__main__":
    import sys
    client = ModelRegistryClient("orchestration.db", "routing.json")
    adapter = client.get_adapter("triage_analysis")
    
    if adapter['status'] == 'retired':
        sys.exit(1)
        
    if not client.verify_integrity(adapter, f"models/{adapter['adapter_id']}.bin"):
        sys.exit(1)
        
    sys.exit(0)
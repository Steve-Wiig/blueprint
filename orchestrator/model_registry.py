import sqlite3
import hashlib
import yaml
from typing import Dict, Optional, Any


class AdapterNotFoundError(Exception):
    """Raised when an adapter is not found in the registry."""
    pass


class InvalidStatusError(Exception):
    """Raised when an adapter has an invalid status."""
    pass


class DatabaseError(Exception):
    """Raised when a database operation fails."""
    pass


class ModelRegistryClient:
    """Client for interacting with the model registry database.

    Manages connections to a SQLite database containing model adapter metadata
    and provides methods for retrieving adapter information and verifying
    file integrity against stored SHA256 hashes.

    This class is not thread-safe. Each thread must create its own instance.
    Sharing an instance across threads requires external synchronization.

    The database connection uses `check_same_thread=False` to allow the
    connection to be used if the instance is passed between threads, but
    concurrent access from multiple threads is not safe without external locking.

    Attributes:
        db_path: Path to the SQLite database file.
        routing_config: Dictionary mapping task types to adapter IDs.
    """

    VALID_STATUSES = {'canary', 'active', 'retired'}

    def __init__(self, db_path: str, routing_config_path: Optional[str] = None, routing_config: Optional[Dict[str, str]] = None):
        """Initialize the ModelRegistryClient.

        Args:
            db_path: Path to the SQLite database file.
            routing_config_path: Path to the YAML routing configuration file.
                Mutually exclusive with routing_config.
            routing_config: Pre-loaded routing configuration dictionary.
                Mutually exclusive with routing_config_path.

        Raises:
            ValueError: If both or neither of routing_config_path and routing_config are provided.

        Note:
            The database connection is established lazily on first use via
            `_get_connection()`. The connection uses `check_same_thread=False`
            to allow the connection to be used if the instance is passed between
            threads, but the class itself is not thread-safe. Each thread should
            create its own instance.
        """
        self.db_path = db_path
        self._conn: sqlite3.Connection = None
        self._routing_config_path = routing_config_path
        self._routing_config: Optional[Dict[str, str]] = routing_config
        self._adapter_cache: Dict[str, Dict[str, Any]] = {}
        self._adapter_id_cache: Dict[str, Dict[str, Any]] = {}

        if routing_config_path is not None and routing_config is not None:
            raise ValueError("Exactly one of routing_config_path or routing_config must be provided")
        if routing_config_path is None and routing_config is None:
            raise ValueError("Exactly one of routing_config_path or routing_config must be provided")

    def load_config(self) -> Dict[str, str]:
        """Load the routing configuration from the YAML file.

        Returns:
            The loaded routing configuration dictionary mapping task types to adapter IDs.

        Raises:
            ValueError: If the routing configuration file cannot be loaded
                or parsed as valid YAML.
            FileNotFoundError: If the routing configuration file does not exist.
            yaml.YAMLError: If the routing configuration contains invalid YAML.
        """
        if self._routing_config is not None:
            return self._routing_config

        if self._routing_config_path is None:
            raise ValueError("No routing config path provided")

        try:
            with open(self._routing_config_path, 'r') as f:
                self._routing_config = yaml.safe_load(f)
        except (FileNotFoundError, PermissionError, yaml.YAMLError, OSError) as e:
            raise ValueError(f"CONFIG ERROR: Could not load routing config: {self._routing_config_path}: {e}")

        self._adapter_cache.clear()
        self._adapter_id_cache.clear()
        return self._routing_config

    @property
    def routing_config(self) -> Dict[str, str]:
        """Get the routing configuration, loading it lazily if needed."""
        if self._routing_config is None:
            self.load_config()
        return self._routing_config

    def initialize_schema(self) -> None:
        """Initialize the database schema by creating required indexes.

        This method should be called explicitly during application setup,
        not as a side effect of getting a connection. It creates the index
        on the adapter_id column for query performance.

        Raises:
            DatabaseError: If a database operation fails during schema initialization.
        """
        try:
            conn = self._connection
            conn.execute("CREATE INDEX IF NOT EXISTS idx_adapter_id ON model_registry(adapter_id)")
            conn.commit()
        except sqlite3.Error as e:
            raise DatabaseError(f"Database error initializing schema: {e}")

    @property
    def _connection(self) -> sqlite3.Connection:
        """Get or create a database connection.

        Returns:
            An active sqlite3.Connection with row_factory set to sqlite3.Row.

        Note:
            This property is not thread-safe. Concurrent access from multiple
            threads may result in multiple connections being created.
            Each thread should use its own ModelRegistryClient instance.
        """
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def get_adapter(self, task_type: str) -> Dict[str, Any]:
        """Retrieve adapter information for a given task type.

        Looks up the adapter ID from the routing configuration, then queries
        the model_registry table for the adapter's metadata. Results are cached
        per task_type to avoid repeated database queries.

        Args:
            task_type: The task type to look up in the routing configuration
                (e.g., "triage_analysis", "threat_classification").

        Returns:
            A dictionary containing the following keys:
                - adapter_id (str): The unique identifier of the adapter.
                - sha256 (str): The expected SHA256 hash of the adapter binary.
                - status (str): The adapter status, one of "canary", "active", or "retired".

        Raises:
            AdapterNotFoundError: If no adapter is configured for the task type
                in the routing configuration, or if the adapter ID is not found
                in the model_registry table.
            InvalidStatusError: If the adapter's status in the registry is not
                one of "canary", "active", or "retired".
            DatabaseError: If a database operation fails (e.g., connection error,
                query execution error, schema mismatch).

        Note:
            This method is not thread-safe. Concurrent calls from multiple threads
            sharing the same instance may result in race conditions.
            Each thread should use its own ModelRegistryClient instance.
        """
        if task_type in self._adapter_cache:
            return self._adapter_cache[task_type]

        adapter_id = self.routing_config.get(task_type)
        if not adapter_id:
            raise AdapterNotFoundError(f"No adapter configured for task type: {task_type}")

        # Check secondary cache keyed by adapter_id to avoid redundant database queries
        # when multiple task_types map to the same adapter_id
        if adapter_id in self._adapter_id_cache:
            result = self._adapter_id_cache[adapter_id]
            self._adapter_cache[task_type] = result
            return result

        try:
            conn = self._connection
            cursor = conn.cursor()
            cursor.execute(
                "SELECT adapter_id, adapter_sha256, status FROM model_registry WHERE adapter_id = ?",
                (adapter_id,)
            )
            row = cursor.fetchone()

            if not row:
                raise AdapterNotFoundError(f"Adapter not found in registry: {adapter_id}")

            if row['status'] not in self.VALID_STATUSES:
                raise InvalidStatusError(f"Invalid adapter status: {row['status']} for adapter: {adapter_id}")

            result = {"adapter_id": row['adapter_id'], "sha256": row['adapter_sha256'], "status": row['status']}
            self._adapter_cache[task_type] = result
            self._adapter_id_cache[adapter_id] = result
            return result
        except sqlite3.Error as e:
            raise DatabaseError(f"Database error retrieving adapter {adapter_id}: {e}")

    def verify_integrity(self, adapter_data: Dict[str, Any], file_path: str) -> Optional[bool]:
        """Verify the SHA256 integrity of an adapter file.

        Computes the SHA256 hash of the file at `file_path` and compares it
        against the expected hash stored in `adapter_data`.

        Args:
            adapter_data: Dictionary containing the expected 'sha256' hash.
                Typically the return value from `get_adapter()`.
            file_path: Path to the adapter binary file to verify.

        Returns:
            True if the file's SHA256 matches the expected hash.
            False if the file exists but the hash does not match.
            None if the file is not found at `file_path` (FileNotFoundError).

        Raises:
            KeyError: If `adapter_data` does not contain a 'sha256' key.
            PermissionError: If the file exists but cannot be read.
            OSError: For other I/O related errors during file reading (e.g., disk errors).

        Note:
            This method reads the file in 4096-byte chunks to handle large
            files efficiently without excessive memory usage.
            This method is thread-safe as it does not access shared state.
            Only FileNotFoundError is caught and returns None; all other exceptions propagate.
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
        """Close the database connection if open.

        This method is idempotent; calling it multiple times has no effect
        after the first call.

        Note:
            This method is not thread-safe. Ensure no other threads are
            using the connection before calling. Each thread should manage
            its own instance lifecycle.
        """
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

        Returns:
            False to propagate any exception that occurred.
        """
        self.close()
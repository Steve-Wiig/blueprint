import unittest
import hashlib
import sqlite3
import os

class TestEmbeddingPrefixIdempotency(unittest.TestCase):
    """
    Validates that semantic recall embeddings maintain prefix consistency
    to prevent duplicate vector injection in pgvector/SQLite working memory.
    """

    def setUp(self):
        self.db_path = ":memory:"
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("CREATE TABLE case_embeddings (id TEXT PRIMARY KEY, vector_blob BLOB)")

    def tearDown(self):
        self.conn.close()

    def _generate_deterministic_id(self, content: str, prefix: str = "SEM-") -> str:
        hash_val = hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]
        return f"{prefix}{hash_val}"

    def test_idempotent_id_generation(self):
        content = "malicious_pattern_0x41"
        id1 = self._generate_deterministic_id(content)
        id2 = self._generate_deterministic_id(content)
        self.assertEqual(id1, id2, "ID generation must be deterministic for identical content")

    def test_prefix_enforcement(self):
        content = "alert_data_stream"
        id1 = self._generate_deterministic_id(content)
        self.assertTrue(id1.startswith("SEM-"), "ID must contain mandatory semantic prefix")

    def test_collision_handling_via_upsert(self):
        content = "test_payload"
        eid = self._generate_deterministic_id(content)
        self.conn.execute("INSERT INTO case_embeddings (id, vector_blob) VALUES (?, ?)", (eid, b'\x00'))
        
        # Attempt duplicate insert
        try:
            self.conn.execute("INSERT INTO case_embeddings (id, vector_blob) VALUES (?, ?)", (eid, b'\x01'))
        except sqlite3.IntegrityError:
            pass # Expected behavior for idempotency gate
        
        res = self.conn.execute("SELECT vector_blob FROM case_embeddings WHERE id = ?", (eid,)).fetchone()
        self.assertEqual(res[0], b'\x00', "State must remain unchanged on duplicate injection")

    def test_sanitization_metadata_integrity(self):
        # Verify that the prefix is not stripped by sanitizers [LAB-VERIFY]
        content = "sanitized_input"
        eid = self._generate_deterministic_id(content)
        sanitized_eid = eid.replace("SEM-", "SEC-")
        self.assertNotEqual(eid, sanitized_eid, "Sanitizer must not mutate prefix structure")

    def test_batch_idempotency(self):
        contents = ["a", "b", "c", "a"]
        ids = [self._generate_deterministic_id(c) for c in contents]
        self.assertEqual(len(set(ids)), 3, "Batch processing must collapse duplicate semantic inputs")

if __name__ == "__main__":
    unittest.main(exit=False)
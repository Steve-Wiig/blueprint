import pytest
import sys
from unittest.mock import MagicMock, patch

# Mocking the module structure for the test environment
class HashChainSealer:
    def __init__(self, db):
        self.db = db
    def seal_chain(self):
        if not self.db.try_lock(): return False
        try:
            rows = self._get_deterministic_rows()
            last_seq = self.db.get_last_seq() or 0
            last_hash = self.db.get_last_hash() or "0" * 64
            for row in rows:
                last_seq += 1
                sealed = self._compute_row(row, last_seq, last_hash)
                self.db.insert_chain_entry(sealed)
                last_hash = sealed['row_hash']
            self.db.commit()
            return True
        except Exception:
            self.db.rollback()
            return False
    def _get_deterministic_rows(self):
        return sorted(self.db.fetch_pending(), key=lambda x: (x['row_ts'], x['row_id']))
    def _compute_row(self, row, seq, prev):
        import hashlib
        payload = f"{seq}{prev}{row['canonical_payload_sha256']}"
        row_hash = hashlib.sha256(payload.encode()).hexdigest()
        return {**row, 'chain_seq': seq, 'previous_hash': prev, 'row_hash': row_hash}

@pytest.fixture
def mock_db():
    db = MagicMock()
    db.try_lock.return_value = True
    return db

def test_deterministic_ordering(mock_db):
    sealer = HashChainSealer(mock_db)
    mock_db.fetch_pending.return_value = [
        {'row_id': 'b', 'row_ts': '2023-01-01 12:00:01'},
        {'row_id': 'a', 'row_ts': '2023-01-01 12:00:00'}
    ]
    ordered = sealer._get_deterministic_rows()
    assert ordered[0]['row_id'] == 'a'
    assert ordered[1]['row_id'] == 'b'

def test_advisory_lock_acquisition(mock_db):
    sealer = HashChainSealer(mock_db)
    sealer.seal_chain()
    mock_db.try_lock.assert_called_once()

def test_chain_seq_increment(mock_db):
    sealer = HashChainSealer(mock_db)
    mock_db.get_last_seq.return_value = 10
    mock_db.fetch_pending.return_value = [{'row_ts': '2023', 'row_id': '1', 'canonical_payload_sha256': 'x'}]
    sealer.seal_chain()
    args = mock_db.insert_chain_entry.call_args[0][0]
    assert args['chain_seq'] == 11

def test_previous_hash_linkage(mock_db):
    sealer = HashChainSealer(mock_db)
    prev_hash = "a" * 64
    mock_db.get_last_hash.return_value = prev_hash
    mock_db.fetch_pending.return_value = [{'row_ts': '2023', 'row_id': '1', 'canonical_payload_sha256': 'x'}]
    sealer.seal_chain()
    args = mock_db.insert_chain_entry.call_args[0][0]
    assert args['previous_hash'] == prev_hash

def test_tamper_detection_logic(mock_db):
    sealer = HashChainSealer(mock_db)
    row = {'canonical_payload_sha256': 'data'}
    h1 = sealer._compute_row(row, 1, '0'*64)['row_hash']
    h2 = sealer._compute_row({'canonical_payload_sha256': 'tampered'}, 1, '0'*64)['row_hash']
    assert h1 != h2

def test_concurrent_sealer_exclusion(mock_db):
    mock_db.try_lock.return_value = False
    sealer = HashChainSealer(mock_db)
    result = sealer.seal_chain()
    assert result is False
    mock_db.insert_chain_entry.assert_not_called()

def test_transaction_rollback_on_failure(mock_db):
    sealer = HashChainSealer(mock_db)
    mock_db.fetch_pending.side_effect = Exception("DB Error")
    result = sealer.seal_chain()
    assert result is False
    mock_db.rollback.assert_called_once()

def test_genesis_hash_usage(mock_db):
    sealer = HashChainSealer(mock_db)
    mock_db.get_last_seq.return_value = None
    mock_db.get_last_hash.return_value = None
    mock_db.fetch_pending.return_value = [{'row_ts': '2023', 'row_id': '1', 'canonical_payload_sha256': 'x'}]
    sealer.seal_chain()
    args = mock_db.insert_chain_entry.call_args[0][0]
    assert args['previous_hash'] == "0" * 64

if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
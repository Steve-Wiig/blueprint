import sys
import pytest

sys.path.insert(0, 'engine')
from intake_eve import execute_in_transaction, execute_with_connection

def test_execute_error_handling():
    with pytest.raises(RuntimeError):
        execute_in_transaction(lambda conn: 1 / 0)
    with pytest.raises(RuntimeError):
        execute_with_connection(lambda conn: 1 / 0)
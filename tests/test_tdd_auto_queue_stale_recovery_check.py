import pytest
from queue_stale_recovery_check import check_stale_queues, recover_stale_items


def test_stale_queue_recovery_check():
    result = check_stale_queues()
    assert result is not None
    recovered = recover_stale_items(result)
    assert isinstance(recovered, int)
    assert recovered >= 0
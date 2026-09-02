import pytest
from vector_partition_index_check import main
def test_runtime_error_preferred_over_sys_exit():
    with pytest.raises(RuntimeError):
        main()
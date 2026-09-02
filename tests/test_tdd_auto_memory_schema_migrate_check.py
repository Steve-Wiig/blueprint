import pytest
import sys
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr
import memory_schema_migrate_check


def test_cli_entry_point_exits_cleanly():
    """Test that the CLI entry point calls sys.exit() with appropriate code."""
    original_argv = sys.argv
    original_exit = sys.exit
    exit_called = []
    exit_code = []

    def mock_exit(code=0):
        exit_called.append(True)
        exit_code.append(code)
        raise SystemExit(code)

    sys.exit = mock_exit
    sys.argv = ["memory_schema_migrate_check.py"]

    try:
        with pytest.raises(SystemExit) as exc_info:
            memory_schema_migrate_check.main()
        assert exc_info.value.code == 0
        assert exit_called
        assert exit_code[0] == 0
    finally:
        sys.argv = original_argv
        sys.exit = original_exit
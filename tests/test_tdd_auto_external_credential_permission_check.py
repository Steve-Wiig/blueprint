import pytest
from unittest.mock import patch, MagicMock
import sys

# Attempt to import the target module
try:
    from external_credential_permission_check import create_connection_pool, get_pool_stats
except ImportError:
    # Module doesn't exist or functions not available - create a failing test
    def test_connection_pool_sizing_ignores_keepalive():
        pytest.fail("Module external_credential_permission_check or required functions not found")
else:
    def test_connection_pool_sizing_ignores_keepalive():
        """Test that connection pool size accounts for keep-alive connections across services."""
        max_workers = 10
        num_services = 3
        
        # Create pool with current implementation (sized to max_workers only)
        pool = create_connection_pool(max_workers=max_workers)
        
        # Simulate keep-alive connections across multiple services
        with patch('external_credential_permission_check.requests.Session') as mock_session:
            mock_adapter = MagicMock()
            mock_session.return_value.mount.return_value = None
            mock_session.return_value.get_adapter.return_value = mock_adapter
            
            # Make requests to different services that would reuse connections
            for service_id in range(num_services):
                for _ in range(max_workers):
                    pool.request('GET', f'https://service{service_id}.example.com/api')
            
            # Check pool statistics
            stats = get_pool_stats(pool)
            
            # BUG: Pool sized only to max_workers (10) but needs max_workers * num_services (30)
            # for proper keep-alive reuse across services
            assert stats['pool_maxsize'] >= max_workers * num_services, \
                f"Pool maxsize {stats['pool_maxsize']} should be >= {max_workers * num_services} " \
                f"to handle keep-alive across {num_services} services with {max_workers} workers each"
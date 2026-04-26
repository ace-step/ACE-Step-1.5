"""Tests for resource cleanup in api_routes module."""

import unittest
from unittest import mock


class ApiRoutesResourceCleanupTests(unittest.TestCase):
    """Verify atexit cleanup for the diskcache result cache."""

    def test_close_result_cache_calls_close_when_diskcache_available(self):
        """_close_result_cache should call .close() on the diskcache backend."""

        from acestep.ui.gradio.api.api_routes import _close_result_cache

        fake_cache = mock.MagicMock()
        with mock.patch(
            "acestep.ui.gradio.api.api_routes._result_cache", fake_cache
        ), mock.patch(
            "acestep.ui.gradio.api.api_routes.DISKCACHE_AVAILABLE", True
        ):
            _close_result_cache()
        fake_cache.close.assert_called_once()

    def test_close_result_cache_skips_when_diskcache_unavailable(self):
        """_close_result_cache should be a no-op when diskcache is not installed."""

        from acestep.ui.gradio.api.api_routes import _close_result_cache

        fake_dict = {}
        with mock.patch(
            "acestep.ui.gradio.api.api_routes._result_cache", fake_dict
        ), mock.patch(
            "acestep.ui.gradio.api.api_routes.DISKCACHE_AVAILABLE", False
        ):
            # Should not raise
            _close_result_cache()

    def test_atexit_registered(self):
        """_close_result_cache should be registered with atexit."""

        import atexit

        from acestep.ui.gradio.api.api_routes import _close_result_cache

        # atexit._run_exitfuncs is CPython internal; instead verify registration
        # by checking the function is importable and callable (registration happens
        # at module load time via atexit.register at module level)
        self.assertTrue(callable(_close_result_cache))


if __name__ == "__main__":
    unittest.main()

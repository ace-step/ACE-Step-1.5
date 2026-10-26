"""Unit tests for ``InitServiceMemoryBasicMixin._get_rss_mb``."""

import platform
import unittest

from acestep.core.generation.handler.init_service_memory_basic import InitServiceMemoryBasicMixin


@unittest.skipUnless(platform.system() == "Windows", "Windows GetProcessMemoryInfo path")
class GetRssMbWindowsTests(unittest.TestCase):
    """The Windows RSS readout returns real numbers and leaves ``ctypes.windll`` alone."""

    def test_returns_current_working_set(self):
        """A running Python process has a working set well above 1 MB, not the old 0.0."""
        self.assertGreater(InitServiceMemoryBasicMixin._get_rss_mb(), 1.0)

    def test_does_not_change_shared_windll_signatures(self):
        """Other ``ctypes.windll`` callers keep the default ``GetCurrentProcess`` return type."""
        import ctypes

        InitServiceMemoryBasicMixin._get_rss_mb()
        self.assertIs(ctypes.windll.kernel32.GetCurrentProcess.restype, ctypes.c_int)


if __name__ == "__main__":
    unittest.main()

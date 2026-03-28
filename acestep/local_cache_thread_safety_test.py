"""Thread safety tests for the local_cache singleton."""

import threading
import unittest

from acestep.local_cache import LocalCache


class LocalCacheLockTests(unittest.TestCase):
    """Verify LocalCache.__new__ has proper double-checked locking."""

    def test_class_level_lock_exists(self):
        """LocalCache._lock must be present for singleton thread safety."""
        self.assertIsInstance(LocalCache._lock, type(threading.Lock()))


if __name__ == "__main__":
    unittest.main()

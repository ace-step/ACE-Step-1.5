"""Thread safety tests for api_routes globals."""

import threading
import unittest

from acestep.ui.gradio.api.api_routes import (
    _api_key_lock,
    _result_cache_lock,
    set_api_key,
    _get_api_key,
    store_result,
    get_result,
    DISKCACHE_AVAILABLE,
)


class ApiKeyLockTests(unittest.TestCase):
    """Verify _api_key reads and writes are synchronized."""

    def test_lock_attributes_exist(self):
        """Module-level locks must be present."""
        self.assertIsInstance(_api_key_lock, type(threading.Lock()))
        self.assertIsInstance(_result_cache_lock, type(threading.Lock()))

    def test_set_and_get_api_key_consistent(self):
        """Concurrent set/get of api_key must not lose updates."""
        set_api_key(None)
        barrier = threading.Barrier(4)
        errors: list[str] = []

        def _writer(value: str) -> None:
            """Set api_key after barrier synchronization."""
            try:
                barrier.wait(timeout=5)
                set_api_key(value)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"writer failed: {exc!r}")

        def _reader() -> None:
            """Read api_key after barrier synchronization."""
            try:
                barrier.wait(timeout=5)
                key = _get_api_key()
                if key is not None and key not in ("key-a", "key-b"):
                    errors.append(f"unexpected key value: {key}")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"reader failed: {exc!r}")

        threads = [
            threading.Thread(target=_writer, args=("key-a",)),
            threading.Thread(target=_writer, args=("key-b",)),
            threading.Thread(target=_reader),
            threading.Thread(target=_reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Race condition detected: {errors}")
        # Final value must be one of the two written keys
        final = _get_api_key()
        self.assertIn(final, ("key-a", "key-b"))
        # Clean up
        set_api_key(None)


class ResultCacheFallbackTests(unittest.TestCase):
    """Verify dict-fallback cache path is thread-safe."""

    @unittest.skipIf(DISKCACHE_AVAILABLE, "Test targets dict fallback only")
    def test_concurrent_store_and_get(self):
        """Concurrent store/get on dict fallback must not raise."""
        barrier = threading.Barrier(8)
        errors: list[str] = []

        def _store(idx: int) -> None:
            """Store a result after barrier synchronization."""
            try:
                barrier.wait(timeout=5)
                store_result(f"task-{idx}", {"idx": idx})
            except Exception as exc:  # noqa: BLE001
                errors.append(f"store failed: {exc!r}")

        def _get(idx: int) -> None:
            """Retrieve a result after barrier synchronization."""
            try:
                barrier.wait(timeout=5)
                get_result(f"task-{idx}")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"get failed: {exc!r}")

        threads = []
        for i in range(4):
            threads.append(threading.Thread(target=_store, args=(i,)))
            threads.append(threading.Thread(target=_get, args=(i,)))
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()

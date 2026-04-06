"""Unit tests for runtime progress relay helpers."""

import unittest

from acestep.core.generation.handler.runtime_progress_relay import RuntimeProgressRelay


class RuntimeProgressRelayTests(unittest.TestCase):
    """Verify runtime progress relay mapping and shutdown behavior."""

    def test_drain_keeps_progress_monotonic(self):
        updates = []
        relay = RuntimeProgressRelay(
            progress=lambda value, desc=None: updates.append((value, desc)),
            start=0.52,
            end=0.79,
        )

        relay.emit_progress(0.68, "estimator")
        relay.enqueue(1, 4, "DiT diffusion...")
        relay.enqueue(4, 4, "DiT diffusion...")

        self.assertTrue(relay.drain())
        self.assertEqual([value for value, _ in updates], sorted(value for value, _ in updates))
        self.assertAlmostEqual(updates[-1][0], 0.79, places=6)

    def test_shutdown_ignores_late_runtime_events(self):
        updates = []
        relay = RuntimeProgressRelay(
            progress=lambda value, desc=None: updates.append((value, desc)),
            start=0.52,
            end=0.79,
        )

        relay.shutdown()
        relay.enqueue(4, 4, "DiT diffusion...")

        self.assertFalse(relay.drain())
        self.assertEqual(updates, [])


if __name__ == "__main__":
    unittest.main()

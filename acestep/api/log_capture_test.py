"""Unit tests for API log capture utilities."""

from __future__ import annotations

import io
import unittest

from acestep.api.log_capture import LogBuffer, StderrLogger, install_log_capture


class _FakeLogger:
    """Minimal fake logger storing added sink callback metadata."""

    def __init__(self):
        self.calls = []

    def add(self, sink, format):
        self.calls.append((sink, format))
        return 1


class LogCaptureTests(unittest.TestCase):
    """Behavior tests for API log buffer and stderr proxy helpers."""

    def test_log_buffer_updates_last_message(self) -> None:
        """Buffer should keep latest non-empty stripped message."""

        buffer = LogBuffer()
        self.assertEqual("Waiting", buffer.last_message)
        buffer.write("   \n")
        self.assertEqual("Waiting", buffer.last_message)
        buffer.write("hello\n")
        self.assertEqual("hello", buffer.last_message)

    def test_stderr_logger_forwards_to_stream_and_buffer(self) -> None:
        """Stderr proxy should write both to original stream and memory buffer."""

        stream = io.StringIO()
        buffer = LogBuffer()
        proxy = StderrLogger(stream, buffer)
        proxy.write("line\n")
        proxy.flush()
        self.assertEqual("line\n", stream.getvalue())
        self.assertEqual("line", buffer.last_message)

    def test_install_log_capture_registers_sink_and_returns_proxy(self) -> None:
        """Installer should register a sink and return connected buffer/proxy."""

        fake_logger = _FakeLogger()
        stream = io.StringIO()
        buffer, proxy = install_log_capture(fake_logger, stream)
        self.assertIsInstance(buffer, LogBuffer)
        self.assertIsInstance(proxy, StderrLogger)
        self.assertEqual(1, len(fake_logger.calls))
        sink, sink_format = fake_logger.calls[0]
        self.assertIn("{level}", sink_format)
        sink("custom message")
        self.assertEqual("custom message", buffer.last_message)


if __name__ == "__main__":
    unittest.main()

"""Unit tests for the ``maybe_compile`` conditional compilation decorator."""

import unittest
from unittest.mock import patch, MagicMock


def _sample_fn(x):
    """Trivial function used as decoration target in tests."""
    return x + 1


class MaybeCompileTests(unittest.TestCase):
    """Verify maybe_compile compiles or skips based on Triton availability."""

    def test_compiles_when_triton_available(self):
        """When Triton is available, the function should be passed to torch.compile."""
        mock_compiled = MagicMock(name="compiled_fn")
        with patch("nanovllm.utils.compat._HAS_TRITON", True), \
             patch("torch.compile", return_value=mock_compiled) as compile_mock:
            from nanovllm.utils.compat import maybe_compile
            result = maybe_compile(_sample_fn)
        compile_mock.assert_called_once_with(_sample_fn)
        self.assertEqual(result, mock_compiled)

    def test_returns_original_when_triton_absent(self):
        """When Triton is absent, the original function should be returned unmodified."""
        with patch("nanovllm.utils.compat._HAS_TRITON", False):
            from nanovllm.utils.compat import maybe_compile
            result = maybe_compile(_sample_fn)
        self.assertIs(result, _sample_fn)

    def test_kwargs_syntax_forwards_compile_args(self):
        """@maybe_compile(dynamic=True) should forward kwargs to torch.compile."""
        mock_compiled = MagicMock(name="compiled_fn")
        with patch("nanovllm.utils.compat._HAS_TRITON", True), \
             patch("torch.compile", return_value=mock_compiled) as compile_mock:
            from nanovllm.utils.compat import maybe_compile
            decorator = maybe_compile(dynamic=True)
            result = decorator(_sample_fn)
        compile_mock.assert_called_once_with(_sample_fn, dynamic=True)
        self.assertEqual(result, mock_compiled)


if __name__ == "__main__":
    unittest.main()

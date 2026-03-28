"""Unit tests for safe shared-memory IPC helpers in model_runner.

Verifies that ``_encode_for_shm`` and ``_decode_from_shm`` correctly
replace ``pickle`` for the shared-memory IPC channel used between
ModelRunner processes in tensor-parallel mode.
"""

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# Root of the nanovllm source tree, resolved relative to this test file.
_NANOVLLM_ROOT = Path(__file__).parent.parent


def _load_sequence_without_torch():
    """Import Sequence directly without triggering the torch-dependent nanovllm package."""
    sp_spec = importlib.util.spec_from_file_location(
        "nanovllm.sampling_params",
        _NANOVLLM_ROOT / "sampling_params.py",
    )
    sp_mod = importlib.util.module_from_spec(sp_spec)
    sys.modules.setdefault("nanovllm.sampling_params", sp_mod)
    sp_spec.loader.exec_module(sp_mod)

    seq_spec = importlib.util.spec_from_file_location(
        "nanovllm.engine.sequence",
        _NANOVLLM_ROOT / "engine" / "sequence.py",
    )
    seq_mod = importlib.util.module_from_spec(seq_spec)
    sys.modules.setdefault("nanovllm.engine.sequence", seq_mod)
    seq_spec.loader.exec_module(seq_mod)

    return seq_mod.Sequence


def _inference_mode_noop(fn=None):
    """Stand-in for torch.inference_mode that simply returns the function unchanged."""
    if fn is None:
        def _decorator(f):
            return f
        return _decorator
    return fn


def _load_shm_helpers(Sequence):
    """Load _encode_for_shm and _decode_from_shm without torch by mocking heavy deps."""
    mock_torch = MagicMock()
    mock_torch.inference_mode = _inference_mode_noop
    mock_torch.set_default_dtype = MagicMock()
    mock_torch.set_default_device = MagicMock()

    stubs = {
        "torch": mock_torch,
        "torch.distributed": MagicMock(),
        "nanovllm.config": MagicMock(),
        "nanovllm.models.qwen3": MagicMock(),
        "nanovllm.layers.sampler": MagicMock(),
        "nanovllm.utils.context": MagicMock(),
        "nanovllm.utils.loader": MagicMock(),
        "nanovllm": MagicMock(),
        "nanovllm.distributed": MagicMock(),
        "acestep.debug_utils": MagicMock(),
    }

    injected = {}
    for name, stub in stubs.items():
        if name not in sys.modules:
            sys.modules[name] = stub
            injected[name] = stub

    try:
        spec = importlib.util.spec_from_file_location(
            "nanovllm.engine.model_runner",
            _NANOVLLM_ROOT / "engine" / "model_runner.py",
        )
        mod = importlib.util.module_from_spec(spec)
        mod.Sequence = Sequence
        spec.loader.exec_module(mod)
    finally:
        for name in injected:
            sys.modules.pop(name, None)

    return mod._encode_for_shm, mod._decode_from_shm, mod


# Load helpers once at module level
_Sequence = _load_sequence_without_torch()
_encode_for_shm, _decode_from_shm, _model_runner_mod = _load_shm_helpers(_Sequence)


def _make_prefill_sequence(token_ids: list) -> object:
    """Return a Sequence whose num_completion_tokens is zero (prefill phase)."""
    return _Sequence(token_ids)


def _make_decode_sequence(token_ids: list) -> object:
    """Return a Sequence that has moved past prefill so last_token is stored."""
    seq = _Sequence(token_ids)
    seq.append_token(99)
    return seq


class TestEncodeDecodeRoundtrip(unittest.TestCase):
    """_encode_for_shm / _decode_from_shm produce correct round-trip results."""

    def test_exit_method_no_args(self):
        """'exit' with no args survives a round-trip."""
        encoded = _encode_for_shm(["exit"])
        decoded = _decode_from_shm(encoded)
        self.assertEqual(decoded, ["exit"])

    def test_simple_string_and_bool(self):
        """Primitive types (str, bool) are preserved."""
        encoded = _encode_for_shm(["run", True])
        decoded = _decode_from_shm(encoded)
        self.assertEqual(decoded[0], "run")
        self.assertIs(decoded[1], True)

    def test_sequence_prefill_roundtrip(self):
        """A prefill-phase Sequence round-trips with correct core attributes."""
        token_ids = [1, 2, 3, 4, 5]
        seq = _make_prefill_sequence(token_ids)
        seq.block_table = [0, 1]
        seq.num_cached_tokens = 0

        encoded = _encode_for_shm(["run", [seq], True])
        decoded = _decode_from_shm(encoded)

        method, seqs, is_prefill = decoded[0], decoded[1], decoded[2]
        self.assertEqual(method, "run")
        self.assertIs(is_prefill, True)
        self.assertEqual(len(seqs), 1)

        out = seqs[0]
        self.assertIsInstance(out, _Sequence)
        self.assertEqual(out.num_tokens, seq.num_tokens)
        self.assertEqual(out.num_prompt_tokens, seq.num_prompt_tokens)
        self.assertEqual(out.num_cached_tokens, seq.num_cached_tokens)
        self.assertEqual(out.block_table, seq.block_table)
        self.assertEqual(out.token_ids, token_ids)

    def test_sequence_decode_roundtrip(self):
        """A decode-phase Sequence round-trips with last_token stored correctly."""
        token_ids = [10, 20, 30]
        seq = _make_decode_sequence(token_ids)
        seq.block_table = [3]

        encoded = _encode_for_shm(["run", [seq], False])
        decoded = _decode_from_shm(encoded)

        out = decoded[1][0]
        self.assertIsInstance(out, _Sequence)
        self.assertEqual(out.num_tokens, seq.num_tokens)
        self.assertEqual(out.num_prompt_tokens, seq.num_prompt_tokens)
        self.assertEqual(out.block_table, [3])
        # For decode sequences, last_token is stored instead of full token_ids
        self.assertEqual(out.last_token, 99)

    def test_multiple_sequences_roundtrip(self):
        """A batch of Sequence objects all survive the round-trip."""
        seqs = [_make_prefill_sequence([i, i + 1]) for i in range(3)]
        for i, s in enumerate(seqs):
            s.block_table = [i]

        encoded = _encode_for_shm(["run", seqs, True])
        decoded = _decode_from_shm(encoded)
        out_seqs = decoded[1]

        self.assertEqual(len(out_seqs), 3)
        for orig, out in zip(seqs, out_seqs):
            self.assertEqual(out.num_tokens, orig.num_tokens)
            self.assertEqual(out.block_table, orig.block_table)

    def test_encoded_bytes_are_valid_utf8_json(self):
        """Encoded bytes must be valid UTF-8 JSON, not a pickle stream."""
        encoded = _encode_for_shm(["exit"])
        # Must not start with the pickle magic bytes (0x80)
        self.assertNotEqual(encoded[0], 0x80)
        # Must be valid JSON
        parsed = json.loads(encoded.decode("utf-8"))
        self.assertIsInstance(parsed, list)

    def test_unsupported_type_raises(self):
        """Passing an unsupported type to _encode_for_shm raises TypeError."""
        with self.assertRaises(TypeError):
            _encode_for_shm(["method", object()])


class TestNoPickleImport(unittest.TestCase):
    """model_runner must not import or use pickle."""

    def test_pickle_not_in_module(self):
        """The pickle module must not be present in model_runner's namespace."""
        self.assertFalse(
            hasattr(_model_runner_mod, "pickle"),
            "model_runner must not import pickle (security: untrusted deserialization)",
        )


if __name__ == "__main__":
    unittest.main()

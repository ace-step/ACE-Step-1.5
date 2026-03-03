"""Unit tests for ``trainer_helpers.resume_checkpoint`` full-mode fallback."""

from __future__ import annotations

import tempfile
import unittest
from types import SimpleNamespace

import torch

from acestep.training_v2 import trainer_helpers


class ResumeCheckpointFullModeTests(unittest.TestCase):
    """Validate full-mode resume behavior when full checkpoint file is absent."""

    def test_full_mode_missing_decoder_state_yields_warning(self) -> None:
        """Missing ``full_decoder_state.pt`` should warn and return ``None``."""
        trainer = SimpleNamespace(
            module=SimpleNamespace(device=torch.device("cpu"), lycoris_net=None),
            training_config=SimpleNamespace(training_mode="full"),
            adapter_type="lora",
        )
        optimizer = SimpleNamespace(load_state_dict=lambda state: None)
        scheduler = SimpleNamespace(load_state_dict=lambda state: None)

        with tempfile.TemporaryDirectory() as tmpdir:
            generator = trainer_helpers.resume_checkpoint(
                trainer,
                tmpdir,
                optimizer,
                scheduler,
            )
            updates = []
            try:
                while True:
                    updates.append(next(generator))
            except StopIteration as stop:
                result = stop.value

        self.assertIsNone(result)
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0].kind, "warn")
        self.assertIn("full_decoder_state.pt not found", updates[0].msg)


if __name__ == "__main__":
    unittest.main()

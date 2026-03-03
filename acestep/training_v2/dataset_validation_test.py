"""Unit tests for training_v2 dataset validation helpers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import torch

from acestep.training_v2.dataset_validation import validate_preprocessed_dataset


class DatasetValidationTest(unittest.TestCase):
    """Covers success and regression paths for dataset validation."""

    def test_validate_dataset_reports_valid_and_invalid_samples(self) -> None:
        """Validator should count valid, invalid, and non-finite samples correctly."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            torch.save(
                {
                    "target_latents": torch.zeros(8, 64),
                    "attention_mask": torch.ones(8),
                    "encoder_hidden_states": torch.zeros(6, 16),
                    "encoder_attention_mask": torch.ones(6),
                    "context_latents": torch.zeros(8, 65),
                },
                root / "ok.pt",
            )
            torch.save(
                {
                    "target_latents": torch.tensor([[float("nan")]]),
                    "attention_mask": torch.ones(1),
                    "encoder_hidden_states": torch.zeros(1, 1),
                    "encoder_attention_mask": torch.ones(1),
                    "context_latents": torch.zeros(1, 1),
                },
                root / "nan.pt",
            )
            torch.save({"target_latents": torch.zeros(4, 64)}, root / "bad.pt")

            report = validate_preprocessed_dataset(str(root))

        self.assertEqual(report["total_samples"], 3)
        self.assertEqual(report["valid_samples"], 2)
        self.assertEqual(report["invalid_samples"], 1)
        self.assertEqual(report["nan_or_inf_samples"], 1)
        self.assertGreaterEqual(len(report["errors"]), 1)


if __name__ == "__main__":
    unittest.main()

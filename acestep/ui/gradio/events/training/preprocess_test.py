"""Unit tests for preprocess.py."""

import os
import json
import tempfile
import unittest
from unittest.mock import MagicMock

from acestep.ui.gradio.events.training.preprocess import (
    load_training_dataset,
    preprocess_dataset,
)


class TestLoadTrainingDataset(unittest.TestCase):
    """Tests for load_training_dataset."""

    def test_empty_path(self):
        result = load_training_dataset("")
        self.assertIn("❌", result)

    def test_nonexistent_path(self):
        result = load_training_dataset("/nonexistent/path/xyz")
        self.assertIn("❌", result)

    def test_with_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = {
                "num_samples": 10,
                "metadata": {"name": "TestDataset", "custom_tag": "test"},
            }
            with open(os.path.join(tmpdir, "manifest.json"), "w") as f:
                json.dump(manifest, f)
            # Create a dummy .pt file
            open(os.path.join(tmpdir, "sample_0.pt"), "w").close()

            result = load_training_dataset(tmpdir)
            self.assertIn("TestDataset", result)
            self.assertIn("10", result)

    def test_without_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create some .pt files
            for i in range(3):
                open(os.path.join(tmpdir, f"sample_{i}.pt"), "w").close()

            result = load_training_dataset(tmpdir)
            self.assertIn("3", result)
            self.assertIn("tensor files", result)

    def test_no_pt_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = load_training_dataset(tmpdir)
            self.assertIn("❌", result)


class TestPreprocessDataset(unittest.TestCase):
    """Tests for preprocess_dataset."""

    def test_none_builder(self):
        result = preprocess_dataset("/out", "lora", MagicMock(), None)
        self.assertIn("❌", result)

    def test_empty_samples(self):
        builder = MagicMock()
        builder.samples = []
        result = preprocess_dataset("/out", "lora", MagicMock(), builder)
        self.assertIn("❌", result)

    def test_no_labeled_samples(self):
        builder = MagicMock()
        builder.samples = [MagicMock()]
        builder.get_labeled_count.return_value = 0
        result = preprocess_dataset("/out", "lora", MagicMock(), builder)
        self.assertIn("❌", result)

    def test_empty_output_dir(self):
        builder = MagicMock()
        builder.samples = [MagicMock()]
        builder.get_labeled_count.return_value = 5
        result = preprocess_dataset("", "lora", MagicMock(), builder)
        self.assertIn("❌", result)

    def test_no_model(self):
        builder = MagicMock()
        builder.samples = [MagicMock()]
        builder.get_labeled_count.return_value = 5
        result = preprocess_dataset("/out", "lora", None, builder)
        self.assertIn("❌", result)


if __name__ == "__main__":
    unittest.main()

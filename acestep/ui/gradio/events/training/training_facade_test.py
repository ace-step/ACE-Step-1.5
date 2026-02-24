"""Unit tests for the training_handlers facade.

Verifies that all expected public symbols are re-exported correctly
through the facade at ``acestep.ui.gradio.events.training_handlers``.
"""

import unittest

from acestep.ui.gradio.events import training_handlers as facade


EXPECTED_SYMBOLS = [
    # training_utils
    "SAFE_TRAINING_ROOT",
    "create_dataset_builder",
    # dataset_ops
    "scan_directory",
    "auto_label_all",
    "get_sample_preview",
    "save_sample_edit",
    "update_settings",
    "save_dataset",
    # preprocess
    "load_existing_dataset_for_preprocess",
    "preprocess_dataset",
    "load_training_dataset",
    # lora_training
    "start_training",
    "stop_training",
    "export_lora",
    # lokr_training
    "start_lokr_training",
    "list_lokr_export_epochs",
    "export_lokr",
]


class TestTrainingFacadeExports(unittest.TestCase):
    """Verify the facade re-exports all expected symbols."""

    def test_all_symbols_present(self):
        for name in EXPECTED_SYMBOLS:
            with self.subTest(symbol=name):
                self.assertTrue(
                    hasattr(facade, name),
                    f"Missing symbol: {name}",
                )

    def test_callable_symbols(self):
        callables = [s for s in EXPECTED_SYMBOLS if s != "SAFE_TRAINING_ROOT"]
        for name in callables:
            with self.subTest(symbol=name):
                self.assertTrue(
                    callable(getattr(facade, name)),
                    f"Symbol not callable: {name}",
                )


if __name__ == "__main__":
    unittest.main()

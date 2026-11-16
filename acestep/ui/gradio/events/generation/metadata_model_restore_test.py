"""Unit tests for metadata_model_restore."""

import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import gradio as gr

from acestep.ui.gradio.events.generation import metadata_model_restore as restore

_DIT_CHOICES = ["acestep-v15-turbo", "acestep-v15-base"]
_LM_CHOICES = ["acestep-5Hz-lm-0.6B", "acestep-5Hz-lm-1.7B"]
_VAE_CHOICES = ["official"]


def _handlers(dit="acestep-v15-turbo", lm="acestep-5Hz-lm-0.6B"):
    """Build fake DiT / LLM handlers with the given loaded models."""
    dit_handler = SimpleNamespace(
        last_init_params={"config_path": dit, "vae_checkpoint": "official"},
        get_available_acestep_v15_models=lambda: list(_DIT_CHOICES),
    )
    llm_handler = SimpleNamespace(
        llm_initialized=True,
        _last_initialize_config={"lm_model_path": lm},
        _lm_full_model_path=None,
        get_available_5hz_lm_models=lambda: list(_LM_CHOICES),
    )
    return dit_handler, llm_handler


class RestoreModelsFromMetadataTests(unittest.TestCase):
    """Verify selector updates built from JSON metadata."""

    def setUp(self):
        """Create a temp dir and patch VAE listing and warnings."""
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        vae_patch = patch.object(restore, "_list_vae_variants", return_value=_VAE_CHOICES)
        vae_patch.start()
        self.addCleanup(vae_patch.stop)
        warn_patch = patch.object(restore.gr, "Warning")
        self.warning = warn_patch.start()
        self.addCleanup(warn_patch.stop)

    def _write(self, data):
        """Write metadata to a temp JSON file and return its path."""
        path = os.path.join(self._tmp.name, "meta.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        return path

    def _restore(self, data, current_dit="acestep-v15-turbo", **loaded):
        """Run restore_models_from_metadata on ``data``."""
        dit_handler, llm_handler = _handlers(**loaded)
        return restore.restore_models_from_metadata(
            self._write(data), current_dit, dit_handler, llm_handler
        )

    def test_old_json_without_models_changes_nothing(self):
        """Old metadata files leave every selector untouched."""
        result = self._restore({"caption": "x", "bpm": 120})
        skip = gr.skip()
        self.assertEqual(result, (skip, skip, skip, False))
        self.warning.assert_not_called()

    def test_same_models_are_selected_without_warning(self):
        """Models equal to the loaded ones are set silently."""
        data = {"dit_model": "acestep-v15-turbo", "lm_model": "acestep-5Hz-lm-0.6B",
                "vae_checkpoint": "official"}
        result = self._restore(data)
        self.assertEqual(result, ("acestep-v15-turbo", "acestep-5Hz-lm-0.6B", "official", False))
        self.warning.assert_not_called()

    def test_different_dit_sets_keep_flag_and_warns(self):
        """A different DiT is selected, flagged and reported."""
        result = self._restore({"dit_model": "acestep-v15-base"})
        self.assertEqual(result[0], "acestep-v15-base")
        self.assertTrue(result[3])
        self.warning.assert_called_once()

    def test_missing_model_is_skipped_with_warning(self):
        """A model that is not in checkpoints is not selected."""
        result = self._restore({"lm_model": "acestep-5Hz-lm-99B"})
        self.assertEqual(result[1], gr.skip())
        self.warning.assert_called_once()

    def test_no_file_changes_nothing(self):
        """A cleared upload gives only skips."""
        dit_handler, llm_handler = _handlers()
        result = restore.restore_models_from_metadata(None, None, dit_handler, llm_handler)
        self.assertEqual(result[3], False)
        self.assertEqual(result[0], gr.skip())


class UpdateModelTypeSettingsKeepingLoadedTests(unittest.TestCase):
    """Verify model-type defaults do not overwrite values loaded from JSON."""

    def test_normal_change_applies_model_defaults(self):
        """Without the flag the original updates are returned unchanged."""
        expected = restore.update_model_type_settings("acestep-v15-base", None)
        result = restore.update_model_type_settings_keeping_loaded("acestep-v15-base", None, False)
        self.assertEqual(result[:-1], tuple(expected))
        self.assertFalse(result[-1])

    def test_after_json_load_keeps_steps_and_shift(self):
        """With the flag, steps and shift keep their value; limits still update."""
        result = restore.update_model_type_settings_keeping_loaded("acestep-v15-base", None, True)
        self.assertNotIn("value", result[0])
        self.assertIn("maximum", result[0])
        self.assertNotIn("value", result[3])
        self.assertFalse(result[-1])


if __name__ == "__main__":
    unittest.main()

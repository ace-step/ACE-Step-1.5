"""Unit tests for model_info.collect_model_info."""

import unittest
from types import SimpleNamespace

from acestep.ui.gradio.events.results.model_info import collect_model_info


def _dit(config_path="checkpoints/acestep-v15-turbo", vae="official"):
    """Build a fake DiT handler with last_init_params."""
    return SimpleNamespace(last_init_params={"config_path": config_path, "vae_checkpoint": vae})


def _llm(initialized=True, lm_path="acestep-5Hz-lm-0.6B"):
    """Build a fake LLM handler."""
    return SimpleNamespace(
        llm_initialized=initialized,
        _last_initialize_config={"lm_model_path": lm_path},
        _lm_full_model_path=None,
    )


class CollectModelInfoTests(unittest.TestCase):
    """Verify model names recorded in saved JSON metadata."""

    def test_returns_dit_lm_and_vae_names(self):
        """Loaded models are reported by folder name."""
        info = collect_model_info(_dit(), _llm())
        self.assertEqual(
            info,
            {
                "dit_model": "acestep-v15-turbo",
                "lm_model": "acestep-5Hz-lm-0.6B",
                "vae_checkpoint": "official",
            },
        )

    def test_lm_is_none_when_not_initialized(self):
        """An LM that is not initialized is not recorded."""
        info = collect_model_info(_dit(), _llm(initialized=False))
        self.assertIsNone(info["lm_model"])

    def test_lm_falls_back_to_full_model_path(self):
        """The full LM path is used when the init config has no model path."""
        llm = _llm(lm_path=None)
        llm._lm_full_model_path = "/models/checkpoints/acestep-5Hz-lm-1.7B/"
        self.assertEqual(collect_model_info(_dit(), llm)["lm_model"], "acestep-5Hz-lm-1.7B")

    def test_all_none_before_service_initialization(self):
        """Handlers that were never initialized give only None values."""
        info = collect_model_info(SimpleNamespace(last_init_params=None), None)
        self.assertEqual(set(info.values()), {None})


if __name__ == "__main__":
    unittest.main()

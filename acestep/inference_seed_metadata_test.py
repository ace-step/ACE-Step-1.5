"""Regression coverage for seeds and batch size in generated audio metadata."""

import unittest
from unittest.mock import MagicMock, patch

import torch

from acestep.core.generation.handler.generate_music_request import GenerateMusicRequestMixin
from acestep.core.generation.handler.task_utils import TaskUtilsMixin
from acestep.inference import GenerationConfig, GenerationParams, generate_music


class SeedResolvingHandler(TaskUtilsMixin, GenerateMusicRequestMixin):
    """Run real seed preparation while replacing model inference with tiny tensors."""

    def __init__(self, batch_limit: int = 8) -> None:
        """Set the effective batch limit and inactive LoRA state."""
        self.batch_limit = batch_limit
        self.batch_size = 2
        self.lora_loaded = False
        self.use_lora = False
        self.lora_scale = 1.0

    def _vram_guard_reduce_batch(self, batch_size: int, **kwargs) -> int:
        """Simulate the hardware-dependent batch cap without allocating a model."""
        return min(batch_size, self.batch_limit)

    def generate_music(self, seed=None, use_random_seed=True, batch_size=None):
        """Resolve real runtime seeds and return one small tensor per output."""
        runtime = self._prepare_generate_music_runtime(
            batch_size=batch_size,
            audio_duration=1.0,
            repainting_end=None,
            seed=seed,
            use_random_seed=use_random_seed,
        )
        return {
            "success": True,
            "status_message": "ok",
            "audios": [
                {"tensor": torch.zeros(2, 16), "sample_rate": 48000}
                for _ in range(runtime["actual_batch_size"])
            ],
            "extra_outputs": {"seed_value": runtime["seed_value_for_ui"]},
        }


class SeedMetadataTests(unittest.TestCase):
    """Audio metadata must describe the seeds and batch actually used by DiT."""

    def _generate(self, config: GenerationConfig, batch_limit: int = 8):
        """Exercise inference with the real seed helpers and no model or file I/O."""
        return generate_music(
            SeedResolvingHandler(batch_limit),
            MagicMock(llm_initialized=False),
            GenerationParams(
                task_type="complete", src_audio="source.wav", enable_normalization=False
            ),
            config,
        )

    def test_random_seeds_are_resolved_once(self) -> None:
        """Random metadata seeds must match the runtime's displayed seeds."""
        with patch(
            "acestep.core.generation.handler.task_utils.random.randint",
            side_effect=[11, 22, 33, 44],
        ):
            result = self._generate(GenerationConfig(batch_size=2, use_random_seed=True))
        self.assertTrue(result.success, result.error)
        self.assertEqual([11, 22], [a["params"]["seed"] for a in result.audios])
        self.assertEqual("11, 22", result.extra_outputs["seed_value"])

    def test_partial_seed_list_keeps_resolved_padding(self) -> None:
        """A missing batch seed must not be randomly filled a second time."""
        with patch(
            "acestep.core.generation.handler.task_utils.random.randint",
            side_effect=[22, 33],
        ):
            result = self._generate(
                GenerationConfig(batch_size=2, seeds=[11], use_random_seed=False)
            )
        self.assertTrue(result.success, result.error)
        self.assertEqual("11, 22", result.extra_outputs["seed_value"])
        self.assertEqual([11, 22], [a["params"]["seed"] for a in result.audios])

    def test_explicit_seeds_remain_unchanged(self) -> None:
        """Fully specified deterministic seeds retain their existing behavior."""
        result = self._generate(
            GenerationConfig(batch_size=2, seeds=[11, 22], use_random_seed=False)
        )
        self.assertTrue(result.success, result.error)
        self.assertEqual("11, 22", result.extra_outputs["seed_value"])
        self.assertEqual([11, 22], [a["params"]["seed"] for a in result.audios])

    def test_metadata_records_effective_batch_size(self) -> None:
        """Persist the actual output batch, including a simulated VRAM reduction."""
        for batch_limit, expected in [(8, 3), (1, 1)]:
            with self.subTest(batch_limit=batch_limit):
                result = self._generate(
                    GenerationConfig(batch_size=3, seeds=[11, 22, 33], use_random_seed=False),
                    batch_limit=batch_limit,
                )
                self.assertTrue(result.success, result.error)
                self.assertEqual(expected, len(result.audios))
                self.assertEqual(
                    [expected] * expected,
                    [a["params"].get("batch_size") for a in result.audios],
                )


if __name__ == "__main__":
    unittest.main()

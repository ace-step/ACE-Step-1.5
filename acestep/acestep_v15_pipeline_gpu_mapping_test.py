"""Unit tests for multi-GPU Gradio CLI flags in the pipeline."""

from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from acestep import acestep_v15_pipeline


class PipelineGpuMappingTests(unittest.TestCase):
    """Verify multi-GPU CLI flags are wired into service initialization."""

    def test_list_gpus_exits_after_printing_inventory(self) -> None:
        """``--list-gpus`` should print inventory and exit without launching UI."""
        with patch.object(sys, "argv", ["acestep", "--list-gpus"]), patch(
            "acestep.gradio_pipeline_cli.format_gpu_list_text",
            return_value="GPU TABLE",
        ) as mock_format, patch(
            "acestep.gradio_pipeline_cli.sys.exit",
            side_effect=SystemExit(0),
        ) as mock_exit, patch(
            "acestep.acestep_v15_pipeline.get_gpu_config",
            return_value=SimpleNamespace(
                gpu_memory_gb=24.0,
                tier="tier6b",
                max_duration_with_lm=480,
                max_duration_without_lm=600,
                max_batch_size_with_lm=8,
                max_batch_size_without_lm=8,
                init_lm_default=True,
                available_lm_models=["acestep-5Hz-lm-0.6B"],
                recommended_backend="vllm",
                lm_backend_restriction=None,
                offload_dit_to_cpu_default=False,
                quantization_default=False,
            ),
        ), patch(
            "acestep.acestep_v15_pipeline.set_global_gpu_config"
        ), patch(
            "acestep.acestep_v15_pipeline.is_mps_platform",
            return_value=False,
        ), patch(
            "acestep.acestep_v15_pipeline.get_i18n"
        ), patch(
            "acestep.gradio_pipeline_cli.available_languages_info",
            return_value=[("en", "English", "English")],
        ), patch(
            "acestep.acestep_v15_pipeline.os.makedirs"
        ):
            with self.assertRaises(SystemExit):
                acestep_v15_pipeline.main()
        mock_format.assert_called_once()
        mock_exit.assert_called_once_with(0)

    def test_gpu_mapping_passed_to_initialize_service(self) -> None:
        """``--gpu-mapping`` must reach DiT init and drive LM device selection."""
        gpu_config = SimpleNamespace(
            gpu_memory_gb=24.0,
            tier="tier6b",
            max_duration_with_lm=480,
            max_duration_without_lm=600,
            max_batch_size_with_lm=8,
            max_batch_size_without_lm=8,
            init_lm_default=True,
            available_lm_models=["acestep-5Hz-lm-0.6B"],
            recommended_backend="vllm",
            lm_backend_restriction=None,
            offload_dit_to_cpu_default=False,
            quantization_default=False,
        )
        dit_handler = MagicMock()
        dit_handler.get_available_acestep_v15_models.return_value = ["acestep-v15-turbo"]
        dit_handler.is_flash_attention_available.return_value = False
        dit_handler.initialize_service.return_value = ("ok", True)
        dit_handler.device_map = SimpleNamespace(lm="cuda:1")

        llm_handler = MagicMock()
        llm_handler.get_available_5hz_lm_models.return_value = ["acestep-5Hz-lm-0.6B"]
        llm_handler.initialize.return_value = ("ok", True)

        demo = MagicMock()
        demo.queue.return_value = demo
        demo.launch.return_value = None
        captured: dict[str, object] = {}

        def _create_demo(init_params=None, language="en"):
            """Capture init_params while returning a stub Gradio demo."""
            captured["init_params"] = init_params
            return demo

        with patch.object(
            sys,
            "argv",
            [
                "acestep",
                "--init_service",
                "true",
                "--init_llm",
                "true",
                "--config_path",
                "acestep-v15-turbo",
                "--gpu-mapping",
                "auto",
            ],
        ), patch.dict(os.environ, {}, clear=True), patch(
            "acestep.acestep_v15_pipeline.get_gpu_config",
            return_value=gpu_config,
        ), patch(
            "acestep.acestep_v15_pipeline.set_global_gpu_config"
        ), patch(
            "acestep.acestep_v15_pipeline.is_mps_platform",
            return_value=False,
        ), patch(
            "acestep.acestep_v15_pipeline.get_i18n"
        ), patch(
            "acestep.gradio_pipeline_cli.available_languages_info",
            return_value=[("en", "English", "English")],
        ), patch(
            "acestep.gradio_pipeline_startup.AceStepHandler",
            return_value=dit_handler,
        ), patch(
            "acestep.gradio_pipeline_startup.LLMHandler",
            return_value=llm_handler,
        ), patch(
            "acestep.acestep_v15_pipeline.create_demo",
            side_effect=_create_demo,
        ), patch(
            "acestep.gradio_pipeline_startup.ensure_lm_model",
            return_value=(True, "ok"),
        ), patch(
            "acestep.acestep_v15_pipeline.os.makedirs"
        ), patch(
            "acestep.gradio_pipeline_startup.log_lm_device_deprecation"
        ):
            acestep_v15_pipeline.main()

        self.assertEqual(
            "auto",
            dit_handler.initialize_service.call_args.kwargs["gpu_mapping"],
        )
        self.assertEqual("cuda:1", llm_handler.initialize.call_args.kwargs["device"])
        self.assertEqual("auto", captured["init_params"]["gpu_mapping"])


if __name__ == "__main__":
    unittest.main()

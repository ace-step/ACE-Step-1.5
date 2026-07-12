"""Device-resolution tests for service_init.init_service_wrapper."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

def _stub_gpu_config(**overrides):
    """Build a MagicMock GPU config with common Gradio defaults."""
    values = dict(
        available_lm_models=["acestep-5Hz-lm-1.7B"],
        lm_backend_restriction=None,
        tier="tier6",
        gpu_memory_gb=24.0,
        max_duration_with_lm=600,
        max_duration_without_lm=600,
        max_batch_size_with_lm=4,
        max_batch_size_without_lm=8,
    )
    values.update(overrides)
    return MagicMock(**values)
class InitServiceWrapperDeviceResolutionTests(unittest.TestCase):
    """Verify auto-device handling and device_map LM placement after DiT init."""

    def _import_module(self):
        """Import service_init lazily to avoid heavy transitive imports."""
        from acestep.ui.gradio.events.generation import service_init

        return service_init

    @patch("acestep.ui.gradio.events.generation.service_init.get_global_gpu_config")
    def test_reinit_without_llm_preserves_resolved_device(self, mock_gpu_config):
        """init_llm=False must not overwrite a previously resolved llm_handler.device."""
        module = self._import_module()
        mock_gpu_config.return_value = _stub_gpu_config()

        dit_handler = MagicMock()
        dit_handler.initialize_service.return_value = ("ok", True)
        dit_handler.model = MagicMock()
        dit_handler.is_turbo_model.return_value = True

        llm_handler = MagicMock()
        llm_handler.llm_initialized = True
        llm_handler.device = "cuda"

        module.init_service_wrapper(
            dit_handler,
            llm_handler,
            "/some/project/checkpoints",
            "acestep-v15-turbo",
            "auto",
            False,
            None,
            "vllm",
            use_flash_attention=False,
            offload_to_cpu=False,
            offload_dit_to_cpu=False,
            compile_model=False,
            quantization=False,
        )

        llm_handler.initialize.assert_not_called()
        self.assertEqual(
            llm_handler.device,
            "cuda",
            "llm_handler.device must remain 'cuda' when init_llm=False, "
            f"got '{llm_handler.device}' instead",
        )

    @patch("acestep.ui.gradio.events.generation.service_init.get_global_gpu_config")
    def test_init_llm_with_auto_device_calls_initialize(self, mock_gpu_config):
        """init_llm=True with device='auto' must pass 'auto' into initialize()."""
        module = self._import_module()
        mock_gpu_config.return_value = _stub_gpu_config()

        dit_handler = MagicMock()
        dit_handler.initialize_service.return_value = ("ok", True)
        dit_handler.model = MagicMock()
        dit_handler.is_turbo_model.return_value = True
        dit_handler.device_map = None

        llm_handler = MagicMock()
        llm_handler.llm_initialized = False
        llm_handler.initialize.return_value = ("[OK] LLM initialized", True)

        module.init_service_wrapper(
            dit_handler,
            llm_handler,
            "/some/project/checkpoints",
            "acestep-v15-turbo",
            "auto",
            True,
            "acestep-5Hz-lm-1.7B",
            "pt",
            use_flash_attention=False,
            offload_to_cpu=False,
            offload_dit_to_cpu=False,
            compile_model=False,
            quantization=False,
        )

        llm_handler.initialize.assert_called_once()
        _, call_kwargs = llm_handler.initialize.call_args
        self.assertEqual(
            call_kwargs.get("device"),
            "auto",
            "initialize() must receive 'auto' so it can resolve to the best device",
        )

    @patch("acestep.ui.gradio.events.generation.service_init.get_global_gpu_config")
    def test_init_llm_uses_device_map_lm_after_dit_init(self, mock_gpu_config):
        """LM device must come from device_map after DiT initialize_service.

        Regression: resolving lm_device before initialize_service left device_map
        empty on first Gradio init, so UI device='auto' collapsed the LM onto
        bare cuda:0 even when ACESTEP_GPU_MAPPING set lm:1.
        """
        module = self._import_module()
        mock_gpu_config.return_value = _stub_gpu_config()

        dit_handler = MagicMock()
        dit_handler.device_map = None

        def _init_service(*_args, **_kwargs):
            """Populate device_map only after DiT initialize_service runs."""
            dit_handler.device_map = MagicMock(lm="cuda:1")
            return ("ok", True)

        dit_handler.initialize_service.side_effect = _init_service
        dit_handler.model = MagicMock()
        dit_handler.is_turbo_model.return_value = True

        llm_handler = MagicMock()
        llm_handler.llm_initialized = False
        llm_handler.initialize.return_value = ("[OK] LLM initialized", True)

        module.init_service_wrapper(
            dit_handler,
            llm_handler,
            "/some/project/checkpoints",
            "acestep-v15-turbo",
            "auto",
            True,
            "acestep-5Hz-lm-1.7B",
            "pt",
            use_flash_attention=False,
            offload_to_cpu=False,
            offload_dit_to_cpu=False,
            compile_model=False,
            quantization=False,
        )

        llm_handler.initialize.assert_called_once()
        _, call_kwargs = llm_handler.initialize.call_args
        self.assertEqual(call_kwargs.get("device"), "cuda:1")

    @patch("acestep.ui.gradio.events.generation.service_init.get_global_gpu_config")
    def test_legacy_cuda_config_forces_pt_backend(self, mock_gpu_config):
        """Legacy CUDA restrictions should override a requested vllm backend."""
        module = self._import_module()
        mock_gpu_config.return_value = _stub_gpu_config(
            available_lm_models=["acestep-5Hz-lm-0.6B"],
            lm_backend_restriction="pt_only",
            recommended_backend="pt",
            tier="tier5",
            gpu_memory_gb=12.0,
            max_duration_with_lm=480,
            max_batch_size_without_lm=4,
        )

        dit_handler = MagicMock()
        dit_handler.initialize_service.return_value = ("ok", True)
        dit_handler.model = MagicMock()
        dit_handler.is_turbo_model.return_value = True

        llm_handler = MagicMock()
        llm_handler.llm_initialized = False
        llm_handler.initialize.return_value = ("ok", True)

        module.init_service_wrapper(
            dit_handler,
            llm_handler,
            "/some/project/checkpoints",
            "acestep-v15-turbo",
            "cuda",
            True,
            "acestep-5Hz-lm-0.6B",
            "vllm",
            use_flash_attention=False,
            offload_to_cpu=False,
            offload_dit_to_cpu=False,
            compile_model=False,
            quantization=False,
        )

        _, call_kwargs = llm_handler.initialize.call_args
        self.assertEqual("pt", call_kwargs.get("backend"))

if __name__ == "__main__":
    unittest.main()

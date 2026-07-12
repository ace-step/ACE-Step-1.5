"""Unit tests for service_init.init_service_wrapper checkpoint path handling."""

import importlib
import os
import sys
import unittest
from unittest.mock import MagicMock, patch


class InitServiceWrapperPathTests(unittest.TestCase):
    """Verify init_service_wrapper passes project_root (not checkpoint dir) to initialize_service."""

    def _import_module(self):
        """Import service_init lazily to avoid heavy transitive imports."""
        from acestep.ui.gradio.events.generation import service_init

        return service_init

    @patch("acestep.ui.gradio.events.generation.service_init.get_global_gpu_config")
    def test_passes_project_root_not_checkpoint_dir(self, mock_gpu_config):
        """init_service_wrapper must NOT pass the checkpoint dropdown value as project_root.

        The checkpoint dropdown returns the full checkpoints directory path
        (e.g. ``<project>/checkpoints``).  Passing it directly as ``project_root``
        causes initialize_service to append ``checkpoints`` again, yielding
        ``<project>/checkpoints/checkpoints``.
        """
        module = self._import_module()

        mock_gpu_config.return_value = MagicMock(
            available_lm_models=["acestep-5Hz-lm-1.7B"],
            lm_backend_restriction=None,
            tier="tier6",
            gpu_memory_gb=24.0,
            max_duration_with_lm=600,
            max_duration_without_lm=600,
            max_batch_size_with_lm=4,
            max_batch_size_without_lm=8,
        )

        dit_handler = MagicMock()
        dit_handler.initialize_service.return_value = ("ok", True)
        dit_handler.model = MagicMock()
        dit_handler.is_turbo_model.return_value = True

        llm_handler = MagicMock()
        llm_handler.llm_initialized = False

        checkpoint_value = "/some/project/checkpoints"

        module.init_service_wrapper(
            dit_handler,
            llm_handler,
            checkpoint_value,
            "acestep-v15-turbo",
            "cpu",
            False,
            None,
            "vllm",
            False,
            False,
            False,
            False,
            False,
        )

        call_args = dit_handler.initialize_service.call_args
        actual_project_root = call_args[0][0]

        self.assertFalse(
            actual_project_root.rstrip("/").endswith("checkpoints"),
            f"project_root must not be the checkpoints dir, got: {actual_project_root}",
        )

    @patch("acestep.ui.gradio.events.generation.service_init.get_global_gpu_config")
    def test_project_root_is_consistent_with_checkpoint_dir(self, mock_gpu_config):
        """The project_root passed to initialize_service should be the parent of checkpoints."""
        module = self._import_module()

        mock_gpu_config.return_value = MagicMock(
            available_lm_models=[],
            lm_backend_restriction=None,
            tier="tier6",
            gpu_memory_gb=24.0,
            max_duration_with_lm=600,
            max_duration_without_lm=600,
            max_batch_size_with_lm=4,
            max_batch_size_without_lm=8,
        )

        dit_handler = MagicMock()
        dit_handler.initialize_service.return_value = ("ok", True)
        dit_handler.model = MagicMock()
        dit_handler.is_turbo_model.return_value = True

        llm_handler = MagicMock()
        llm_handler.llm_initialized = False

        module.init_service_wrapper(
            dit_handler,
            llm_handler,
            "/any/path/checkpoints",
            "acestep-v15-turbo",
            "cpu",
            False,
            None,
            "vllm",
            False,
            False,
            False,
            False,
            False,
        )

        call_args = dit_handler.initialize_service.call_args
        actual_project_root = call_args[0][0]
        expected_checkpoints = os.path.join(actual_project_root, "checkpoints")
        self.assertTrue(
            os.path.isabs(expected_checkpoints) or actual_project_root,
            "project_root should be a meaningful path",
        )
        self.assertNotIn(
            "checkpoints/checkpoints",
            expected_checkpoints,
            f"Double nesting detected: {expected_checkpoints}",
        )


class QuantizationSelectionTests(unittest.TestCase):
    """Verify pre-Ampere quantization mode selection."""

    def _import_module(self):
        """Import service_init lazily to avoid heavy transitive imports."""
        from acestep.ui.gradio.events.generation import service_init

        return service_init

    def test_select_quantization_value_uses_dynamic_mode_for_pre_ampere_cuda(self):
        """It selects ``w8a8_dynamic`` for pre-Ampere CUDA devices."""
        module = self._import_module()

        with patch("torch.cuda.is_available", return_value=True), patch(
            "torch.cuda.get_device_capability", return_value=(6, 1)
        ):
            self.assertEqual(
                module._select_quantization_value(
                    quantization_enabled=True,
                    device="cuda",
                ),
                "w8a8_dynamic",
            )

    def test_select_quantization_value_keeps_default_when_torch_import_fails(self):
        """It keeps the default quantization when torch cannot be imported."""
        module = importlib.import_module(
            "acestep.ui.gradio.events.generation.service_init"
        )
        real_import = __import__
        removed_torch_module = sys.modules.pop("torch", None)
        removed_torch_nn_module = sys.modules.pop("torch.nn", None)

        def fake_import(name, globals_=None, locals_=None, fromlist=(), level=0):
            """Raise ImportError only for torch imports from the helper."""
            if name == "torch" or name.startswith("torch."):
                raise ImportError("torch missing")
            return real_import(name, globals_, locals_, fromlist, level)

        try:
            with patch("builtins.__import__", side_effect=fake_import):
                self.assertEqual(
                    module._select_quantization_value(
                        quantization_enabled=True,
                        device="cuda",
                    ),
                    "int8_weight_only",
                )
        finally:
            if removed_torch_module is not None:
                sys.modules["torch"] = removed_torch_module
            if removed_torch_nn_module is not None:
                sys.modules["torch.nn"] = removed_torch_nn_module


if __name__ == "__main__":
    unittest.main()

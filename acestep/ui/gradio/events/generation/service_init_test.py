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

        # Stub GPU config
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

        # Simulate the checkpoint dropdown value: full path to checkpoints dir
        checkpoint_value = "/some/project/checkpoints"

        module.init_service_wrapper(
            dit_handler,
            llm_handler,
            checkpoint_value,
            "acestep-v15-turbo",
            "cpu",
            False,  # init_llm
            None,  # lm_model_path
            "vllm",  # backend
            False,  # use_flash_attention
            False,  # offload_to_cpu
            False,  # offload_dit_to_cpu
            False,  # compile_model
            False,  # quantization
        )

        # The first positional arg to initialize_service must be the project root,
        # NOT the checkpoints directory.
        call_args = dit_handler.initialize_service.call_args
        actual_project_root = call_args[0][0]

        # It should be computed from __file__, not from the checkpoint dropdown.
        # Critically, it must NOT end with "checkpoints".
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
            "/any/path/checkpoints",  # checkpoint dropdown value (unused now)
            "acestep-v15-turbo",
            "cpu",
            False, None, "vllm", False, False, False, False, False,
        )

        call_args = dit_handler.initialize_service.call_args
        actual_project_root = call_args[0][0]

        # The project_root + "checkpoints" should form a valid checkpoints path
        expected_checkpoints = os.path.join(actual_project_root, "checkpoints")
        self.assertTrue(
            os.path.isabs(expected_checkpoints) or actual_project_root,
            "project_root should be a meaningful path",
        )
        # It should NOT contain double "checkpoints"
        self.assertNotIn(
            "checkpoints/checkpoints",
            expected_checkpoints,
            f"Double nesting detected: {expected_checkpoints}",
        )


class InitServiceWrapperDeviceResolutionTests(unittest.TestCase):
    """Verify that 'auto' device is not written back to llm_handler when init_llm=False.

    Regression test for: Auto-labelling broke after recent update if auto is
    chosen for device.  When the user re-initialises the service without the
    'Init LLM' checkbox ticked, the previously-resolved device (e.g. 'cuda')
    must not be overwritten with the raw UI value 'auto'.
    """

    def _import_module(self):
        """Import service_init lazily to avoid heavy transitive imports."""
        from acestep.ui.gradio.events.generation import service_init
        return service_init

    @patch("acestep.ui.gradio.events.generation.service_init.get_global_gpu_config")
    def test_reinit_without_llm_preserves_resolved_device(self, mock_gpu_config):
        """Calling init_service_wrapper with init_llm=False must not overwrite llm_handler.device.

        Scenario: LLM was previously initialized (llm_initialized=True, device='cuda').
        User re-initialises the service (e.g. to change checkpoint) with init_llm=False
        and device='auto'.  The LLM handler's resolved device must remain 'cuda'.
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

        # Simulate LLM previously initialised with resolved device="cuda"
        llm_handler = MagicMock()
        llm_handler.llm_initialized = True
        llm_handler.device = "cuda"  # previously resolved from "auto" -> "cuda"

        module.init_service_wrapper(
            dit_handler,
            llm_handler,
            "/some/project/checkpoints",
            "acestep-v15-turbo",
            "auto",   # raw UI value -- must NOT overwrite the resolved "cuda"
            False,    # init_llm=False: do not re-initialize LLM
            None,     # lm_model_path
            "vllm",   # backend
            use_flash_attention=False,
            offload_to_cpu=False,
            offload_dit_to_cpu=False,
            compile_model=False,
            quantization=False,
        )

        # llm_handler.initialize must NOT have been called (init_llm=False)
        llm_handler.initialize.assert_not_called()
        # The previously-resolved device must be preserved
        self.assertEqual(
            llm_handler.device,
            "cuda",
            "llm_handler.device must remain 'cuda' when init_llm=False, "
            f"got '{llm_handler.device}' instead",
        )

    @patch("acestep.ui.gradio.events.generation.service_init.get_global_gpu_config")
    def test_init_llm_with_auto_device_calls_initialize(self, mock_gpu_config):
        """When init_llm=True and device='auto', initialize() must be called with 'auto' device.

        The 'auto' -> concrete device resolution happens inside initialize(), so we
        must pass 'auto' through correctly.
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
        llm_handler.initialize.return_value = ("[OK] LLM initialized", True)

        module.init_service_wrapper(
            dit_handler,
            llm_handler,
            "/some/project/checkpoints",
            "acestep-v15-turbo",
            "auto",   # raw UI value
            True,     # init_llm=True
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



class QuantizationSelectionTests(unittest.TestCase):
    """Verify pre-Ampere quantization mode selection."""

    def _import_module(self):
        """Import service_init lazily to avoid heavy transitive imports."""
        from acestep.ui.gradio.events.generation import service_init
        return service_init

    def test_select_quantization_value_uses_dynamic_mode_for_pre_ampere_cuda(self):
        """It selects ``w8a8_dynamic`` for pre-Ampere CUDA devices."""
        module = self._import_module()

        with patch("torch.cuda.is_available", return_value=True), \
                patch("torch.cuda.get_device_capability", return_value=(6, 1)):
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

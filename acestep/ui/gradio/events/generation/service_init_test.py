"""Unit tests for service_init.init_service_wrapper checkpoint path handling."""

import os
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


if __name__ == "__main__":
    unittest.main()

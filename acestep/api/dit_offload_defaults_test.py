"""Regression tests for DiT offload defaults in both API initialization paths."""

import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from acestep.api.http.model_init_service import initialize_models_for_request
from acestep.api.server_utils import env_bool
from acestep.api.startup_model_init import do_model_initialization
from acestep.gpu_config import get_gpu_config


class DitOffloadDefaultsTests(unittest.TestCase):
    """Exercise tier defaults, platform overrides and explicit environment settings."""

    def test_api_initializers_honor_dit_offload_defaults(self) -> None:
        """Both entrypoints should pass the resolved setting to every DiT handler."""
        cases = [
            (8.0, False, None, True),
            (12.0, False, None, True),
            (12.1, False, None, False),
            (16.0, False, None, False),
            (24.0, False, None, False),
            (8.0, True, None, False),
            (0.0, False, None, False),
            (8.0, False, "false", False),
            (24.0, False, "true", True),
        ]
        for memory, mps, override, expected in cases:
            for entrypoint in ("startup", "request"):
                with self.subTest(memory=memory, mps=mps, override=override, path=entrypoint):
                    env = {} if override is None else {"ACESTEP_OFFLOAD_DIT_TO_CPU": override}
                    with patch.dict(os.environ, env, clear=True), patch(
                        "acestep.gpu_config.is_mps_platform", return_value=mps
                    ), patch("acestep.gpu_config.is_legacy_cuda_gpu", return_value=False):
                        config = get_gpu_config(memory)
                        handlers = [MagicMock() for _ in range(3)]
                        for handler in handlers:
                            handler.initialize_service.return_value = ("ok", True)
                        state = SimpleNamespace(
                            gpu_config=config,
                            handler=handlers[0],
                            handler2=handlers[1],
                            handler3=handlers[2],
                            llm_handler=MagicMock(),
                        )
                        kwargs = dict(
                            get_project_root=lambda: "/unused",
                            get_model_name=lambda name: name,
                            ensure_model_downloaded=MagicMock(),
                            env_bool=env_bool,
                        )
                        if entrypoint == "startup":
                            with patch("acestep.api.startup_model_init.os.makedirs"), patch(
                                "acestep.api.startup_model_init.initialize_llm_at_startup"
                            ):
                                do_model_initialization(
                                    app=SimpleNamespace(state=state),
                                    handler=handlers[0],
                                    handler2=handlers[1],
                                    handler3=handlers[2],
                                    llm_handler=state.llm_handler,
                                    config_path2="acestep-v15-base",
                                    config_path3="acestep-v15-sft",
                                    **kwargs,
                                )
                            self.assertEqual(
                                state._service_init_kwargs["offload_dit_to_cpu"], expected
                            )
                        else:
                            with patch("acestep.api.http.model_init_service.os.makedirs"), patch(
                                "acestep.api.http.model_init_service.get_gpu_config",
                                return_value=config,
                            ):
                                for slot in (1, 2, 3):
                                    initialize_models_for_request(
                                        app_state=state,
                                        model_name="acestep-v15-turbo",
                                        init_llm=False,
                                        requested_lm_model_path=None,
                                        slot=slot,
                                        **kwargs,
                                    )
                        for handler in handlers:
                            handler.initialize_service.assert_called_once()
                            self.assertEqual(
                                handler.initialize_service.call_args.kwargs["offload_dit_to_cpu"],
                                expected,
                            )


if __name__ == "__main__":
    unittest.main()

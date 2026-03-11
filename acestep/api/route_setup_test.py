"""Unit tests for API route setup helper wiring."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from acestep.api.route_setup import configure_api_routes


class RouteSetupTests(unittest.TestCase):
    """Behavior tests for middleware and route registration orchestration."""

    @patch("acestep.api.route_setup.register_query_result_route")
    @patch("acestep.api.route_setup.register_release_task_route")
    @patch("acestep.api.route_setup.register_audio_route")
    @patch("acestep.api.route_setup.register_training_api_routes")
    @patch("acestep.api.route_setup.register_reinitialize_route")
    @patch("acestep.api.route_setup.register_lora_routes")
    @patch("acestep.api.route_setup.register_sample_format_routes")
    @patch("acestep.api.route_setup.register_model_service_routes")
    @patch("acestep.api.route_setup.create_openrouter_router")
    def test_configure_api_routes_registers_all_routes_and_middleware(
        self,
        mock_create_openrouter_router,
        mock_register_model_service_routes,
        mock_register_sample_format_routes,
        mock_register_lora_routes,
        mock_register_reinitialize_route,
        mock_register_training_api_routes,
        mock_register_audio_route,
        mock_register_release_task_route,
        mock_register_query_result_route,
    ) -> None:
        """Setup should add CORS, include router, and invoke all route registrars once."""

        app = FastAPI()
        router = APIRouter()
        mock_create_openrouter_router.return_value = router

        configure_api_routes(
            app=app,
            store=object(),
            queue_maxsize=200,
            initial_avg_job_seconds=5.0,
            verify_api_key=MagicMock(),
            verify_token_from_request=MagicMock(),
            wrap_response=MagicMock(),
            get_project_root=MagicMock(return_value="k:/repo"),
            get_model_name=MagicMock(return_value="acestep-v15-turbo"),
            ensure_model_downloaded=MagicMock(return_value="k:/repo/checkpoints/model"),
            env_bool=MagicMock(return_value=False),
            simple_example_data=[],
            custom_example_data=[],
            format_sample=MagicMock(),
            to_int=MagicMock(return_value=None),
            to_float=MagicMock(return_value=None),
            request_parser_cls=MagicMock(),
            request_model_cls=MagicMock(),
            validate_audio_path=MagicMock(return_value=None),
            save_upload_to_temp=MagicMock(),
            default_dit_instruction="instruction",
            lm_default_temperature=0.85,
            lm_default_cfg_scale=2.5,
            lm_default_top_p=0.9,
            map_status=MagicMock(return_value=0),
            result_key_prefix="prefix",
            task_timeout_seconds=3600,
            log_buffer=MagicMock(),
            runtime_start_tensorboard=MagicMock(),
            runtime_stop_tensorboard=MagicMock(),
            runtime_temporary_llm_model=MagicMock(),
            runtime_atomic_write_json=MagicMock(),
            runtime_append_jsonl=MagicMock(),
        )

        self.assertTrue(any(m.cls is CORSMiddleware for m in app.user_middleware))
        mock_create_openrouter_router.assert_called_once()
        mock_register_model_service_routes.assert_called_once()
        mock_register_sample_format_routes.assert_called_once()
        mock_register_lora_routes.assert_called_once()
        mock_register_reinitialize_route.assert_called_once()
        mock_register_training_api_routes.assert_called_once()
        mock_register_audio_route.assert_called_once()
        mock_register_release_task_route.assert_called_once()
        mock_register_query_result_route.assert_called_once()


if __name__ == "__main__":
    unittest.main()

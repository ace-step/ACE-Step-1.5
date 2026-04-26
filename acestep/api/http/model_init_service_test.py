"""Unit tests for blocking model initialization service helpers."""

import threading
import unittest
from types import SimpleNamespace
from unittest import mock

from acestep.api.http.model_init_service import initialize_models_for_request


class _FakeHandler:
    """Fake DiT handler providing initialize_service contract."""

    def initialize_service(self, **_kwargs):
        """Return ``("ok", True)`` to emulate successful DiT initialization."""

        return "ok", True


class _FakeLlm:
    """Fake LLM handler providing initialize contract."""

    def initialize(self, **_kwargs):
        """Return ``("ok", True)`` to emulate successful LLM initialization."""

        return "ok", True


class _FailingLlm:
    """Fake LLM handler that fails initialize for error-path tests."""

    def initialize(self, **_kwargs):
        """Return ``("llm-failed", False)`` for LLM failure-path assertions."""

        return "llm-failed", False


class ModelInitServiceTests(unittest.TestCase):
    """Behavior tests for initialize_models_for_request helper."""

    def test_raises_when_handler_missing(self):
        """Missing handler should preserve legacy AttributeError behavior."""

        state = SimpleNamespace(handler=None, llm_handler=_FakeLlm())
        with mock.patch("acestep.api.http.model_init_service.os.makedirs"):
            with self.assertRaises(AttributeError) as ctx:
                initialize_models_for_request(
                    app_state=state,
                    model_name="acestep-v15-base",
                    init_llm=False,
                    requested_lm_model_path=None,
                    get_project_root=lambda: "/tmp/non-existent",
                    get_model_name=lambda p: str(p).split("/")[-1].split("\\")[-1],
                    ensure_model_downloaded=lambda *_: "",
                    env_bool=lambda *_: False,
                )
        self.assertIn("initialize_service", str(ctx.exception))

    def test_raises_when_init_llm_requested_but_llm_missing(self):
        """Missing llm_handler should preserve legacy AttributeError behavior."""

        state = SimpleNamespace(handler=_FakeHandler(), llm_handler=None, _llm_init_lock=threading.Lock())
        with mock.patch("acestep.api.http.model_init_service.os.makedirs"):
            with self.assertRaises(AttributeError) as ctx:
                initialize_models_for_request(
                    app_state=state,
                    model_name="acestep-v15-base",
                    init_llm=True,
                    requested_lm_model_path="acestep-5Hz-lm-0.6B",
                    get_project_root=lambda: "/tmp/non-existent",
                    get_model_name=lambda p: str(p).split("/")[-1].split("\\")[-1],
                    ensure_model_downloaded=lambda *_: "",
                    env_bool=lambda *_: False,
                )
        self.assertIn("initialize", str(ctx.exception))

    def test_returns_loaded_model_when_dit_init_succeeds(self):
        """Successful DiT-only init should return loaded_model and no LM value."""

        state = SimpleNamespace(
            handler=_FakeHandler(),
            llm_handler=_FakeLlm(),
            _llm_init_lock=threading.Lock(),
            _config_path="",
        )
        with mock.patch("acestep.api.http.model_init_service.os.makedirs"):
            result = initialize_models_for_request(
                app_state=state,
                model_name="acestep-v15-base",
                init_llm=False,
                requested_lm_model_path=None,
                get_project_root=lambda: "/tmp/non-existent",
                get_model_name=lambda p: str(p).split("/")[-1].split("\\")[-1],
                ensure_model_downloaded=lambda *_: "",
                env_bool=lambda *_: False,
            )

        self.assertEqual("acestep-v15-base", result["loaded_model"])
        self.assertIsNone(result["loaded_lm_model"])

    def test_lm_init_failure_sets_state_and_raises(self):
        """LLM init failure should update state flags and raise RuntimeError."""

        state = SimpleNamespace(
            handler=_FakeHandler(),
            llm_handler=_FailingLlm(),
            _llm_init_lock=threading.Lock(),
            _config_path="",
            _llm_initialized=True,
            _llm_init_error=None,
            _llm_lazy_load_disabled=False,
        )

        with mock.patch("acestep.api.http.model_init_service.os.makedirs"):
            with self.assertRaises(RuntimeError) as ctx:
                initialize_models_for_request(
                    app_state=state,
                    model_name="acestep-v15-base",
                    init_llm=True,
                    requested_lm_model_path="acestep-5Hz-lm-0.6B",
                    get_project_root=lambda: "/tmp/non-existent",
                    get_model_name=lambda p: str(p).split("/")[-1].split("\\")[-1],
                    ensure_model_downloaded=lambda *_: "",
                    env_bool=lambda *_: False,
                )

        self.assertIn("LLM init failed", str(ctx.exception))
        self.assertFalse(state._llm_initialized)
        self.assertEqual("llm-failed", state._llm_init_error)

    def test_slot1_default_uses_primary_handler(self):
        """Slot 1 (default) should initialize the primary handler and set _config_path."""

        state = SimpleNamespace(
            handler=_FakeHandler(),
            llm_handler=_FakeLlm(),
            _llm_init_lock=threading.Lock(),
            _config_path="",
            _init_error=None,
        )
        with mock.patch("acestep.api.http.model_init_service.os.makedirs"):
            result = initialize_models_for_request(
                app_state=state,
                model_name="acestep-v15-base",
                init_llm=False,
                requested_lm_model_path=None,
                get_project_root=lambda: "/tmp/non-existent",
                get_model_name=lambda p: str(p).split("/")[-1].split("\\")[-1],
                ensure_model_downloaded=lambda *_: "",
                env_bool=lambda *_: False,
                slot=None,
            )

        self.assertEqual(1, result["slot"])
        self.assertEqual("acestep-v15-base", result["loaded_model"])
        self.assertTrue(state._initialized)
        self.assertEqual("acestep-v15-base", state._config_path)

    def test_slot2_uses_secondary_handler(self):
        """Slot 2 should initialize handler2 and set _config_path2."""

        handler2 = _FakeHandler()
        state = SimpleNamespace(
            handler=_FakeHandler(),
            handler2=handler2,
            llm_handler=_FakeLlm(),
            _llm_init_lock=threading.Lock(),
            _config_path="acestep-v15-turbo",
            _config_path2="",
            _initialized2=False,
            _init_error2=None,
        )
        with mock.patch("acestep.api.http.model_init_service.os.makedirs"):
            result = initialize_models_for_request(
                app_state=state,
                model_name="acestep-v15-base",
                init_llm=False,
                requested_lm_model_path=None,
                get_project_root=lambda: "/tmp/non-existent",
                get_model_name=lambda p: str(p).split("/")[-1].split("\\")[-1],
                ensure_model_downloaded=lambda *_: "",
                env_bool=lambda *_: False,
                slot=2,
            )

        self.assertEqual(2, result["slot"])
        self.assertEqual("acestep-v15-base", result["loaded_model"])
        self.assertTrue(state._initialized2)
        self.assertEqual("acestep-v15-base", state._config_path2)

    def test_slot3_uses_third_handler(self):
        """Slot 3 should initialize handler3 and set _config_path3."""

        handler3 = _FakeHandler()
        state = SimpleNamespace(
            handler=_FakeHandler(),
            handler3=handler3,
            llm_handler=_FakeLlm(),
            _llm_init_lock=threading.Lock(),
            _config_path="acestep-v15-turbo",
            _config_path3="",
            _initialized3=False,
            _init_error3=None,
        )
        with mock.patch("acestep.api.http.model_init_service.os.makedirs"):
            result = initialize_models_for_request(
                app_state=state,
                model_name="acestep-v15-base",
                init_llm=False,
                requested_lm_model_path=None,
                get_project_root=lambda: "/tmp/non-existent",
                get_model_name=lambda p: str(p).split("/")[-1].split("\\")[-1],
                ensure_model_downloaded=lambda *_: "",
                env_bool=lambda *_: False,
                slot=3,
            )

        self.assertEqual(3, result["slot"])
        self.assertEqual("acestep-v15-base", result["loaded_model"])
        self.assertTrue(state._initialized3)
        self.assertEqual("acestep-v15-base", state._config_path3)

    def test_slot2_raises_when_handler_not_constructed(self):
        """Slot 2 should raise RuntimeError when handler2 is None."""

        state = SimpleNamespace(
            handler=_FakeHandler(),
            handler2=None,
            llm_handler=_FakeLlm(),
            _llm_init_lock=threading.Lock(),
            _config_path="",
        )
        with mock.patch("acestep.api.http.model_init_service.os.makedirs"):
            with self.assertRaises(RuntimeError) as ctx:
                initialize_models_for_request(
                    app_state=state,
                    model_name="acestep-v15-base",
                    init_llm=False,
                    requested_lm_model_path=None,
                    get_project_root=lambda: "/tmp/non-existent",
                    get_model_name=lambda p: str(p).split("/")[-1].split("\\")[-1],
                    ensure_model_downloaded=lambda *_: "",
                    env_bool=lambda *_: False,
                    slot=2,
                )
        self.assertIn("Slot 2", str(ctx.exception))
        self.assertIn("ACESTEP_CONFIG_PATH2", str(ctx.exception))

    def test_slot3_raises_when_handler_not_constructed(self):
        """Slot 3 should raise RuntimeError when handler3 is None."""

        state = SimpleNamespace(
            handler=_FakeHandler(),
            handler3=None,
            llm_handler=_FakeLlm(),
            _llm_init_lock=threading.Lock(),
            _config_path="",
        )
        with mock.patch("acestep.api.http.model_init_service.os.makedirs"):
            with self.assertRaises(RuntimeError) as ctx:
                initialize_models_for_request(
                    app_state=state,
                    model_name="acestep-v15-base",
                    init_llm=False,
                    requested_lm_model_path=None,
                    get_project_root=lambda: "/tmp/non-existent",
                    get_model_name=lambda p: str(p).split("/")[-1].split("\\")[-1],
                    ensure_model_downloaded=lambda *_: "",
                    env_bool=lambda *_: False,
                    slot=3,
                )
        self.assertIn("Slot 3", str(ctx.exception))
        self.assertIn("ACESTEP_CONFIG_PATH3", str(ctx.exception))

    def test_init_llm_uses_pt_backend_for_legacy_cuda_gpu(self):
        """Legacy CUDA GPU configs should coerce LM init away from vllm."""

        llm = mock.Mock()
        llm.initialize.return_value = ("ok", True)
        state = SimpleNamespace(
            handler=_FakeHandler(),
            llm_handler=llm,
            _llm_init_lock=threading.Lock(),
            _config_path="",
            _llm_initialized=False,
            _llm_init_error=None,
            _llm_lazy_load_disabled=False,
        )

        gpu_config = SimpleNamespace(
            gpu_memory_gb=12.0,
            offload_to_cpu_default=False,
            recommended_backend="pt",
            lm_backend_restriction="pt_only",
        )

        with mock.patch("acestep.api.http.model_init_service.os.makedirs"), mock.patch(
            "acestep.api.http.model_init_service.get_gpu_config",
            return_value=gpu_config,
        ), mock.patch.dict("os.environ", {"ACESTEP_LM_BACKEND": "vllm"}, clear=True):
            result = initialize_models_for_request(
                app_state=state,
                model_name="acestep-v15-base",
                init_llm=True,
                requested_lm_model_path="acestep-5Hz-lm-0.6B",
                get_project_root=lambda: "/tmp/non-existent",
                get_model_name=lambda p: str(p).split("/")[-1].split("\\")[-1],
                ensure_model_downloaded=lambda *_: "",
                env_bool=lambda *_: False,
            )

        self.assertEqual("acestep-v15-base", result["loaded_model"])
        self.assertEqual("pt", llm.initialize.call_args.kwargs["backend"])


if __name__ == "__main__":
    unittest.main()

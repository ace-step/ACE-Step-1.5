"""Unit tests for API runtime helper utilities."""

from __future__ import annotations

import os
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

from acestep.api.runtime_helpers import (
    append_jsonl,
    atomic_write_json,
    start_tensorboard,
    stop_tensorboard,
    temporary_llm_model,
)


class RuntimeHelpersTests(unittest.TestCase):
    """Behavior tests for extracted runtime helper functions."""

    def test_stop_tensorboard_terminates_and_clears_process(self):
        """Stop helper should terminate process and clear app state pointer."""

        process = mock.Mock()
        app = SimpleNamespace(state=SimpleNamespace(tensorboard_process=process))

        stop_tensorboard(app)

        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=3)
        self.assertIsNone(app.state.tensorboard_process)

    def test_start_tensorboard_starts_process_and_returns_url(self):
        """Start helper should invoke Popen and return URL when startup succeeds."""

        app = SimpleNamespace(state=SimpleNamespace(tensorboard_process=None))
        fake_proc = mock.Mock()
        stop_calls = []

        with mock.patch("acestep.api.runtime_helpers.os.getenv", return_value="6007"), mock.patch(
            "acestep.api.runtime_helpers.sys.prefix", "venv-prefix"
        ), mock.patch("acestep.api.runtime_helpers.sys.base_prefix", "base-prefix"), mock.patch(
            "acestep.api.runtime_helpers.os.path.exists", return_value=False
        ), mock.patch(
            "acestep.api.runtime_helpers.subprocess.Popen", return_value=fake_proc
        ):
            url = start_tensorboard(app, logdir="logs", stop_tensorboard_fn=lambda a: stop_calls.append(a))

        self.assertEqual("http://localhost:6007", url)
        self.assertEqual([app], stop_calls)
        self.assertIs(app.state.tensorboard_process, fake_proc)

    def test_start_tensorboard_returns_none_on_failure(self):
        """Start helper should return None when startup raises an exception."""

        app = SimpleNamespace(state=SimpleNamespace(tensorboard_process=None))
        with mock.patch(
            "acestep.api.runtime_helpers.subprocess.Popen",
            side_effect=RuntimeError("failed"),
        ):
            url = start_tensorboard(app, logdir="logs")
        self.assertIsNone(url)

    def test_temporary_llm_model_noops_when_path_missing(self):
        """Temporary switch helper should no-op when desired model path is empty."""

        app = SimpleNamespace(state=SimpleNamespace(_llm_init_lock=threading.Lock()))
        llm = SimpleNamespace(llm_initialized=True, initialize=mock.Mock(), last_init_params={})

        with temporary_llm_model(
            app=app,
            llm=llm,
            lm_model_path="",
            get_project_root=lambda: "root",
            get_model_name=lambda path: path,
            ensure_model_downloaded=lambda *_: "",
            env_bool=lambda *_: False,
        ):
            pass

        llm.initialize.assert_not_called()

    def test_temporary_llm_model_switches_and_restores(self):
        """Temporary switch helper should initialize target model then restore previous params."""

        app = SimpleNamespace(
            state=SimpleNamespace(
                _llm_init_lock=threading.Lock(),
                _llm_initialized=False,
                _llm_init_error="",
            )
        )
        prev_params = {
            "checkpoint_dir": "old-checkpoints",
            "lm_model_path": "old-model",
            "backend": "vllm",
            "device": "cuda",
            "offload_to_cpu": False,
            "dtype": None,
        }
        llm = SimpleNamespace(
            llm_initialized=True,
            initialize=mock.Mock(return_value=("ok", True)),
            last_init_params=prev_params,
        )
        downloaded = []

        with mock.patch("acestep.api.runtime_helpers.os.makedirs"):
            with temporary_llm_model(
                app=app,
                llm=llm,
                lm_model_path="new-model",
                get_project_root=lambda: "project-root",
                get_model_name=lambda _path: "new-model",
                ensure_model_downloaded=lambda model, checkpoint_dir: downloaded.append((model, checkpoint_dir)),
                env_bool=lambda *_: False,
            ):
                self.assertTrue(app.state._llm_initialized)
                self.assertIsNone(app.state._llm_init_error)

        self.assertEqual([("new-model", os.path.join("project-root", "checkpoints"))], downloaded)
        self.assertEqual(2, llm.initialize.call_count)
        first_call = llm.initialize.call_args_list[0].kwargs
        second_call = llm.initialize.call_args_list[1].kwargs
        self.assertEqual("new-model", first_call["lm_model_path"])
        self.assertEqual(prev_params, second_call)

    def test_atomic_write_json_replaces_target_on_success(self):
        """Atomic write helper should fsync temp file and replace destination path."""

        mock_file = mock.Mock()
        mock_file.fileno.return_value = 99
        mock_context = mock.Mock()
        mock_context.__enter__ = mock.Mock(return_value=mock_file)
        mock_context.__exit__ = mock.Mock(return_value=False)

        with mock.patch("acestep.api.runtime_helpers.os.makedirs"), mock.patch(
            "acestep.api.runtime_helpers.tempfile.mkstemp",
            return_value=(11, "tmp-file.json"),
        ), mock.patch("acestep.api.runtime_helpers.os.fdopen", return_value=mock_context), mock.patch(
            "acestep.api.runtime_helpers.json.dump"
        ), mock.patch(
            "acestep.api.runtime_helpers.os.fsync"
        ) as fsync_mock, mock.patch(
            "acestep.api.runtime_helpers.os.replace"
        ) as replace_mock:
            atomic_write_json("out/data.json", {"ok": True})

        fsync_mock.assert_called_once_with(99)
        replace_mock.assert_called_once_with("tmp-file.json", "out/data.json")

    def test_atomic_write_json_cleans_tmp_file_on_error(self):
        """Atomic write helper should remove temp file and re-raise when replace fails."""

        mock_file = mock.Mock()
        mock_file.fileno.return_value = 99
        mock_context = mock.Mock()
        mock_context.__enter__ = mock.Mock(return_value=mock_file)
        mock_context.__exit__ = mock.Mock(return_value=False)

        with mock.patch("acestep.api.runtime_helpers.os.makedirs"), mock.patch(
            "acestep.api.runtime_helpers.tempfile.mkstemp",
            return_value=(11, "tmp-file.json"),
        ), mock.patch("acestep.api.runtime_helpers.os.fdopen", return_value=mock_context), mock.patch(
            "acestep.api.runtime_helpers.json.dump"
        ), mock.patch(
            "acestep.api.runtime_helpers.os.fsync"
        ), mock.patch(
            "acestep.api.runtime_helpers.os.replace",
            side_effect=RuntimeError("replace failed"),
        ), mock.patch("acestep.api.runtime_helpers.os.remove") as remove_mock:
            with self.assertRaises(RuntimeError):
                atomic_write_json("out/data.json", {"ok": True})

        remove_mock.assert_called_once_with("tmp-file.json")

    def test_append_jsonl_writes_one_line(self):
        """JSONL append helper should append one serialized record plus newline."""

        with mock.patch("acestep.api.runtime_helpers.os.makedirs"), mock.patch(
            "acestep.api.runtime_helpers.json.dumps",
            return_value='{"a": 1}',
        ), mock.patch("builtins.open", mock.mock_open()) as open_mock:
            append_jsonl("out/log.jsonl", {"a": 1})

        open_mock.assert_called_once_with("out/log.jsonl", "a", encoding="utf-8")
        open_mock().write.assert_called_once_with('{"a": 1}\n')


if __name__ == "__main__":
    unittest.main()

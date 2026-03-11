"""Unit tests for API model auto-download helper functions."""

from __future__ import annotations

import os
import types
import unittest
from unittest import mock

from acestep.api import model_download


class ModelDownloadTests(unittest.TestCase):
    """Behavior tests for extracted model download helper module."""

    def test_download_from_huggingface_uses_unified_repo_target_dir(self):
        """Unified repo downloads should target local_dir directly."""

        snapshot_download = mock.Mock(return_value="ok")
        fake_hf = types.SimpleNamespace(snapshot_download=snapshot_download)
        with mock.patch.dict("sys.modules", {"huggingface_hub": fake_hf}):
            out = model_download.download_from_huggingface(
                repo_id=model_download.DEFAULT_REPO_ID,
                local_dir="checkpoints",
                model_name="acestep-v15-turbo",
            )

        snapshot_download.assert_called_once_with(
            repo_id=model_download.DEFAULT_REPO_ID,
            local_dir="checkpoints",
            local_dir_use_symlinks=False,
        )
        self.assertEqual(os.path.join("checkpoints", "acestep-v15-turbo"), out)

    def test_download_from_modelscope_retries_with_cache_dir_on_type_error(self):
        """ModelScope download should retry with cache_dir for compatibility."""

        snapshot_download = mock.Mock(side_effect=[TypeError("bad"), "ok"])
        fake_ms = types.SimpleNamespace(snapshot_download=snapshot_download)
        with mock.patch.dict("sys.modules", {"modelscope": fake_ms}):
            out = model_download.download_from_modelscope(
                repo_id=model_download.DEFAULT_REPO_ID,
                local_dir="checkpoints",
                model_name="acestep-v15-turbo",
            )

        self.assertEqual(2, snapshot_download.call_count)
        first_call = snapshot_download.call_args_list[0].kwargs
        second_call = snapshot_download.call_args_list[1].kwargs
        self.assertEqual(
            {"model_id": model_download.DEFAULT_REPO_ID, "local_dir": "checkpoints"},
            first_call,
        )
        self.assertEqual(
            {"model_id": model_download.DEFAULT_REPO_ID, "cache_dir": "checkpoints"},
            second_call,
        )
        self.assertEqual(os.path.join("checkpoints", "acestep-v15-turbo"), out)

    def test_ensure_model_downloaded_returns_existing_model_path(self):
        """Ensure helper should return existing model path without download attempts."""

        with mock.patch("acestep.api.model_download.os.path.exists", return_value=True), mock.patch(
            "acestep.api.model_download.os.listdir",
            return_value=["weights.safetensors"],
        ), mock.patch("acestep.api.model_download.download_from_huggingface") as hf_mock, mock.patch(
            "acestep.api.model_download.download_from_modelscope"
        ) as ms_mock:
            out = model_download.ensure_model_downloaded("acestep-v15-turbo", "checkpoints")

        self.assertEqual(os.path.join("checkpoints", "acestep-v15-turbo"), out)
        hf_mock.assert_not_called()
        ms_mock.assert_not_called()

    def test_ensure_model_downloaded_uses_huggingface_when_env_prefers_it(self):
        """Ensure helper should honor explicit HuggingFace preference."""

        with mock.patch.dict(os.environ, {"ACESTEP_DOWNLOAD_SOURCE": "huggingface"}, clear=False), mock.patch(
            "acestep.api.model_download.os.path.exists",
            return_value=False,
        ), mock.patch(
            "acestep.api.model_download.download_from_huggingface",
            return_value="hf-path",
        ) as hf_mock, mock.patch(
            "acestep.api.model_download.download_from_modelscope",
            return_value="ms-path",
        ) as ms_mock:
            out = model_download.ensure_model_downloaded("acestep-v15-turbo", "checkpoints")

        self.assertEqual("hf-path", out)
        hf_mock.assert_called_once()
        ms_mock.assert_not_called()

    def test_ensure_model_downloaded_falls_back_to_modelscope_from_huggingface(self):
        """Ensure helper should fallback to ModelScope when HuggingFace fails."""

        with mock.patch.dict(os.environ, {"ACESTEP_DOWNLOAD_SOURCE": ""}, clear=False), mock.patch(
            "acestep.api.model_download.os.path.exists",
            return_value=False,
        ), mock.patch("acestep.api.model_download.can_access_google", return_value=True), mock.patch(
            "acestep.api.model_download.download_from_huggingface",
            side_effect=RuntimeError("hf down"),
        ) as hf_mock, mock.patch(
            "acestep.api.model_download.download_from_modelscope",
            return_value="ms-path",
        ) as ms_mock:
            out = model_download.ensure_model_downloaded("acestep-v15-turbo", "checkpoints")

        self.assertEqual("ms-path", out)
        hf_mock.assert_called_once()
        ms_mock.assert_called_once()

    def test_ensure_model_downloaded_falls_back_to_huggingface_from_modelscope(self):
        """Ensure helper should fallback to HuggingFace when ModelScope fails."""

        with mock.patch.dict(os.environ, {"ACESTEP_DOWNLOAD_SOURCE": ""}, clear=False), mock.patch(
            "acestep.api.model_download.os.path.exists",
            return_value=False,
        ), mock.patch("acestep.api.model_download.can_access_google", return_value=False), mock.patch(
            "acestep.api.model_download.download_from_modelscope",
            side_effect=RuntimeError("ms down"),
        ) as ms_mock, mock.patch(
            "acestep.api.model_download.download_from_huggingface",
            return_value="hf-path",
        ) as hf_mock:
            out = model_download.ensure_model_downloaded("acestep-v15-turbo", "checkpoints")

        self.assertEqual("hf-path", out)
        ms_mock.assert_called_once()
        hf_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()

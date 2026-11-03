"""Tests for the --timestep-mu override in build_configs."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from acestep.training_v2.cli.args import build_root_parser
from acestep.training_v2.cli.config_builder import build_configs


def _parse(ckpt_dir: str, *extra: str):
    """Parse a minimal `fixed` command line pointing at *ckpt_dir*."""
    argv = [
        "fixed", "--checkpoint-dir", ckpt_dir, "--model-variant", "base",
        "--dataset-dir", ckpt_dir, "--output-dir", ckpt_dir, *extra,
    ]
    return build_root_parser().parse_args(argv)


_FAKE_GPU = SimpleNamespace(device="cpu", precision="fp32")


@patch("acestep.training_v2.cli.config_builder.detect_gpu", return_value=_FAKE_GPU)
class TimestepMuOverrideTest(unittest.TestCase):
    """The model config value is used unless --timestep-mu is given."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        model_dir = Path(self.tmp.name) / "acestep-v15-base"
        model_dir.mkdir()
        (model_dir / "config.json").write_text(
            json.dumps({"timestep_mu": -0.4, "timestep_sigma": 1.0})
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_defaults_to_model_config(self, _gpu) -> None:
        _, cfg = build_configs(_parse(self.tmp.name))
        self.assertEqual(cfg.timestep_mu, -0.4)

    def test_override_replaces_model_config(self, _gpu) -> None:
        _, cfg = build_configs(_parse(self.tmp.name, "--timestep-mu", "-0.8"))
        self.assertEqual(cfg.timestep_mu, -0.8)
        self.assertEqual(cfg.timestep_sigma, 1.0)

    def test_vanilla_subcommand_unaffected(self, _gpu) -> None:
        argv = [
            "vanilla", "--checkpoint-dir", self.tmp.name, "--model-variant", "base",
            "--dataset-dir", self.tmp.name, "--output-dir", self.tmp.name,
        ]
        _, cfg = build_configs(build_root_parser().parse_args(argv))
        self.assertEqual(cfg.timestep_mu, -0.4)


if __name__ == "__main__":
    unittest.main()

"""Unit tests for the standalone CLI entrypoint in train_fixed.py.

Verifies that:
- ``build_fixed_standalone_parser`` creates a working argparse parser
- ``main()`` exists in train_fixed.py (verified via source inspection)
- The ``if __name__ == "__main__":`` guard is present in train_fixed.py
- ``build_fixed_standalone_parser`` is exported from common.py
- The parser accepts the same flags as the ``fixed`` subcommand of ``train.py``
- ``_run_preprocess`` rejects calls with missing required arguments

Parser tests do not require torch.  Behavioral tests that import train_fixed
(which transitively imports torch) are separated and will be skipped when
torch is not installed -- consistent with other tests in this package.
"""

import argparse
import ast
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CLI_DIR = Path(__file__).parent


def _parse_source(filename: str) -> ast.Module:
    """Parse a Python source file in the CLI directory and return its AST.

    Args:
        filename: Name of the file relative to the CLI package directory.

    Returns:
        Parsed AST module node for the given source file.
    """
    return ast.parse((_CLI_DIR / filename).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Parser tests (no torch required)
# ---------------------------------------------------------------------------

class TestBuildFixedStandaloneParser(unittest.TestCase):
    """Tests for ``build_fixed_standalone_parser`` in args.py."""

    def _get_parser(self):
        from acestep.training_v2.cli.args import build_fixed_standalone_parser
        return build_fixed_standalone_parser()

    def test_returns_argument_parser(self):
        """``build_fixed_standalone_parser`` returns an ArgumentParser."""
        parser = self._get_parser()
        self.assertIsInstance(parser, argparse.ArgumentParser)

    def test_prog_name_is_module_invocation(self):
        """Parser prog reflects module invocation syntax."""
        parser = self._get_parser()
        self.assertIn("train_fixed", parser.prog)

    def test_accepts_common_training_flags(self):
        """Parser accepts shared training flags like --checkpoint-dir and --dataset-dir."""
        parser = self._get_parser()
        args = parser.parse_args([
            "--checkpoint-dir", "/tmp/ckpt",
            "--dataset-dir", "/tmp/data",
            "--output-dir", "/tmp/out",
        ])
        self.assertEqual(args.checkpoint_dir, "/tmp/ckpt")
        self.assertEqual(args.dataset_dir, "/tmp/data")
        self.assertEqual(args.output_dir, "/tmp/out")

    def test_accepts_fixed_specific_cfg_ratio(self):
        """Parser accepts --cfg-ratio flag specific to the fixed subcommand."""
        parser = self._get_parser()
        args = parser.parse_args([
            "--checkpoint-dir", "/tmp/ckpt",
            "--dataset-dir", "/tmp/data",
            "--output-dir", "/tmp/out",
            "--cfg-ratio", "0.25",
        ])
        self.assertAlmostEqual(args.cfg_ratio, 0.25)

    def test_accepts_plain_and_yes_flags(self):
        """Parser accepts --plain and --yes convenience flags."""
        parser = self._get_parser()
        args = parser.parse_args([
            "--checkpoint-dir", "/tmp/ckpt",
            "--dataset-dir", "/tmp/data",
            "--output-dir", "/tmp/out",
            "--plain",
            "--yes",
        ])
        self.assertTrue(args.plain)
        self.assertTrue(args.yes)

    def test_accepts_preprocess_mode(self):
        """Parser accepts --preprocess flag for preprocessing mode."""
        parser = self._get_parser()
        args = parser.parse_args([
            "--checkpoint-dir", "/tmp/ckpt",
            "--dataset-dir", "/tmp/data",
            "--output-dir", "/tmp/out",
            "--preprocess",
            "--audio-dir", "/tmp/audio",
            "--tensor-output", "/tmp/tensors",
        ])
        self.assertTrue(args.preprocess)
        self.assertEqual(args.audio_dir, "/tmp/audio")
        self.assertEqual(args.tensor_output, "/tmp/tensors")


# ---------------------------------------------------------------------------
# Source-inspection tests (no torch required)
# ---------------------------------------------------------------------------

class TestTrainFixedSourceStructure(unittest.TestCase):
    """Structural tests using AST inspection -- no torch required."""

    def _func_names(self) -> set:
        tree = _parse_source("train_fixed.py")
        return {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}

    def test_main_function_defined_in_source(self):
        """``main`` function is defined in train_fixed.py."""
        self.assertIn("main", self._func_names())

    def test_run_preprocess_helper_defined_in_source(self):
        """``_run_preprocess`` helper is defined in train_fixed.py."""
        self.assertIn("_run_preprocess", self._func_names())

    def test_module_has_main_guard(self):
        """train_fixed.py contains the ``if __name__ == '__main__'`` guard."""
        src = (_CLI_DIR / "train_fixed.py").read_text(encoding="utf-8")
        self.assertIn('if __name__ == "__main__"', src)

    def test_common_exports_build_fixed_standalone_parser(self):
        """``build_fixed_standalone_parser`` is imported (and re-exported) in common.py."""
        tree = _parse_source("common.py")
        found = any(
            isinstance(node, ast.ImportFrom) and
            any(alias.name == "build_fixed_standalone_parser" for alias in node.names)
            for node in ast.walk(tree)
        )
        self.assertTrue(found, "build_fixed_standalone_parser should be re-exported from common.py")

    def test_build_fixed_standalone_parser_in_args(self):
        """``build_fixed_standalone_parser`` is defined as a function in args.py."""
        tree = _parse_source("args.py")
        func_names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        self.assertIn("build_fixed_standalone_parser", func_names)


# ---------------------------------------------------------------------------
# Behavioral tests (require torch -- skipped when torch is absent)
# ---------------------------------------------------------------------------

def _has_torch() -> bool:
    try:
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


@unittest.skipUnless(_has_torch(), "torch not installed -- skipping behavioral tests")
class TestTrainFixedMainBehavior(unittest.TestCase):
    """Behavioral tests for main() and _run_preprocess() -- require torch."""

    def test_main_routes_preprocess(self):
        """When --preprocess is passed, main() calls _run_preprocess."""
        from acestep.training_v2.cli import train_fixed

        preprocess_mock = MagicMock(return_value=0)
        run_fixed_mock = MagicMock(return_value=0)

        test_argv = [
            "train_fixed",
            "--checkpoint-dir", "/tmp/ckpt",
            "--dataset-dir", "/tmp/data",
            "--output-dir", "/tmp/out",
            "--preprocess",
            "--audio-dir", "/tmp/audio",
            "--tensor-output", "/tmp/tensors",
        ]

        with patch.object(train_fixed, "_run_preprocess", preprocess_mock), \
             patch.object(train_fixed, "run_fixed", run_fixed_mock), \
             patch.object(sys, "argv", test_argv):
            result = train_fixed.main()

        preprocess_mock.assert_called_once()
        run_fixed_mock.assert_not_called()
        self.assertEqual(result, 0)

    def test_main_sets_subcommand_fixed(self):
        """main() sets args.subcommand to 'fixed' before calling run_fixed."""
        from acestep.training_v2.cli import train_fixed

        captured_args = []

        def capture_run_fixed(args):
            captured_args.append(args)
            return 0

        validate_mock = MagicMock(return_value=True)
        test_argv = [
            "train_fixed",
            "--checkpoint-dir", "/tmp/ckpt",
            "--dataset-dir", "/tmp/data",
            "--output-dir", "/tmp/out",
        ]

        with patch.object(train_fixed, "run_fixed", side_effect=capture_run_fixed), \
             patch("acestep.training_v2.cli.train_fixed.validate_paths", validate_mock), \
             patch.object(sys, "argv", test_argv):
            train_fixed.main()

        self.assertEqual(len(captured_args), 1)
        self.assertEqual(captured_args[0].subcommand, "fixed")

    def test_main_validates_paths_before_run_fixed(self):
        """main() returns 1 without calling run_fixed when validate_paths fails."""
        from acestep.training_v2.cli import train_fixed

        run_fixed_mock = MagicMock(return_value=0)
        validate_mock = MagicMock(return_value=False)
        test_argv = [
            "train_fixed",
            "--checkpoint-dir", "/nonexistent",
            "--dataset-dir", "/tmp/data",
            "--output-dir", "/tmp/out",
        ]

        with patch.object(train_fixed, "run_fixed", run_fixed_mock), \
             patch("acestep.training_v2.cli.train_fixed.validate_paths", validate_mock), \
             patch.object(sys, "argv", test_argv):
            result = train_fixed.main()

        run_fixed_mock.assert_not_called()
        self.assertEqual(result, 1)

    def test_run_preprocess_returns_1_without_audio_dir(self):
        """_run_preprocess returns 1 when both audio_dir and dataset_json are None."""
        from acestep.training_v2.cli.train_fixed import _run_preprocess
        args = argparse.Namespace(
            audio_dir=None, dataset_json=None,
            tensor_output="/tmp/tensors", checkpoint_dir="/tmp/ckpt",
            model_variant="turbo", max_duration=240.0,
            device="auto", precision="auto",
        )
        self.assertEqual(_run_preprocess(args), 1)

    def test_run_preprocess_returns_1_without_tensor_output(self):
        """_run_preprocess returns 1 when tensor_output is None."""
        from acestep.training_v2.cli.train_fixed import _run_preprocess
        args = argparse.Namespace(
            audio_dir="/tmp/audio", dataset_json=None,
            tensor_output=None, checkpoint_dir="/tmp/ckpt",
            model_variant="turbo", max_duration=240.0,
            device="auto", precision="auto",
        )
        self.assertEqual(_run_preprocess(args), 1)


if __name__ == "__main__":
    unittest.main()

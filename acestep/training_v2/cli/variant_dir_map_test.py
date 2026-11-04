"""Tests that CLI variant aliases (including XL) resolve to checkpoint folders."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from acestep.training_v2.cli.args import VARIANT_DIR_MAP
from acestep.training_v2.cli.config_builder import _resolve_model_config_path
from acestep.training_v2.cli.validation import validate_paths
from acestep.training_v2.model_loader import _VARIANT_DIR


class VariantDirMapTest(unittest.TestCase):
    """--model-variant xl_base must find acestep-v15-xl-base like base does."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for name in ("acestep-v15-base", "acestep-v15-xl-base"):
            (self.root / name).mkdir()
            (self.root / name / "config.json").write_text(json.dumps({"timestep_mu": -0.4}))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _validate(self, variant: str) -> SimpleNamespace:
        args = SimpleNamespace(
            checkpoint_dir=str(self.root), model_variant=variant,
            dataset_dir=None, resume_from=None,
        )
        self.assertTrue(validate_paths(args), variant)
        return args

    def test_xl_base_alias_resolves(self) -> None:
        args = self._validate("xl_base")
        self.assertEqual(args.model_dir, self.root / "acestep-v15-xl-base")
        self.assertEqual(
            _resolve_model_config_path(self.root, "xl_base"),
            self.root / "acestep-v15-xl-base" / "config.json",
        )

    def test_base_alias_unchanged(self) -> None:
        self.assertEqual(self._validate("base").model_dir, self.root / "acestep-v15-base")

    def test_literal_folder_name_still_works(self) -> None:
        args = self._validate("acestep-v15-xl-base")
        self.assertEqual(args.model_dir, self.root / "acestep-v15-xl-base")

    def test_cli_map_matches_model_loader(self) -> None:
        self.assertEqual(VARIANT_DIR_MAP, _VARIANT_DIR)


if __name__ == "__main__":
    unittest.main()

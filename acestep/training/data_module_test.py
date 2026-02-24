"""Tests for path-sanitisation in data_module.

Covers the safe_path integration in PreprocessedTensorDataset and
load_dataset_from_json that guards against path-traversal attacks
(CodeQL: uncontrolled data used in path expression).
"""

import os
import json
import tempfile
import unittest

from acestep.training.path_safety import safe_path, set_safe_root
from acestep.training.data_module import (
    PreprocessedTensorDataset,
    load_dataset_from_json,
)


class SafePathTests(unittest.TestCase):
    """Tests for safe_path from path_safety module."""

    def test_valid_directory(self):
        with tempfile.TemporaryDirectory() as d:
            parent = os.path.dirname(os.path.realpath(d))
            set_safe_root(parent)
            result = safe_path(d)
            self.assertEqual(result, os.path.realpath(d))

    def test_traversal_raises(self):
        with tempfile.TemporaryDirectory() as d:
            set_safe_root(d)
            with self.assertRaises(ValueError):
                safe_path("../../etc/passwd", base=d)

    def test_absolute_path_outside_raises(self):
        with tempfile.TemporaryDirectory() as d:
            set_safe_root(d)
            with self.assertRaises(ValueError):
                safe_path("/etc/passwd", base=d)

    def test_normal_child(self):
        with tempfile.TemporaryDirectory() as d:
            base = os.path.realpath(d)
            result = safe_path("foo.pt", base=base)
            self.assertEqual(result, os.path.join(base, "foo.pt"))

    def test_absolute_path_inside_allowed(self):
        with tempfile.TemporaryDirectory() as d:
            base = os.path.realpath(d)
            child = os.path.join(base, "sub", "file.pt")
            result = safe_path(child, base=base)
            self.assertEqual(result, child)


class PreprocessedTensorDatasetPathSafetyTests(unittest.TestCase):
    """Tests that PreprocessedTensorDataset rejects traversal paths."""

    def setUp(self):
        # Allow /tmp paths during tests
        set_safe_root(tempfile.gettempdir())

    def test_manifest_traversal_paths_skipped(self):
        """Paths in manifest.json that escape tensor_dir are ignored."""
        with tempfile.TemporaryDirectory() as d:
            # Create a manifest with one good and one bad path
            good_pt = os.path.join(d, "good.pt")
            open(good_pt, "wb").close()  # touch

            manifest = {
                "samples": [
                    "good.pt",
                    "../../etc/passwd",
                ]
            }
            with open(os.path.join(d, "manifest.json"), "w") as f:
                json.dump(manifest, f)

            ds = PreprocessedTensorDataset(d)
            # Only the safe path should survive
            self.assertEqual(len(ds.valid_paths), 1)
            self.assertTrue(ds.valid_paths[0].endswith("good.pt"))

    def test_fallback_scan_only_finds_pt_files(self):
        """Without manifest, only .pt files inside tensor_dir are found."""
        with tempfile.TemporaryDirectory() as d:
            for name in ["a.pt", "b.pt", "c.txt"]:
                open(os.path.join(d, name), "wb").close()

            ds = PreprocessedTensorDataset(d)
            self.assertEqual(len(ds.valid_paths), 2)

    def test_nonexistent_dir_raises(self):
        with self.assertRaises(ValueError):
            PreprocessedTensorDataset("/tmp/nonexistent_xyz_12345")

    def test_manifest_relative_to_tensor_dir(self):
        """Manifest with paths relative to tensor_dir loads correctly."""
        with tempfile.TemporaryDirectory() as d:
            for name in ["a.pt", "b.pt"]:
                open(os.path.join(d, name), "wb").close()

            manifest = {"samples": ["a.pt", "b.pt"]}
            with open(os.path.join(d, "manifest.json"), "w") as f:
                json.dump(manifest, f)

            ds = PreprocessedTensorDataset(d)
            self.assertEqual(len(ds.valid_paths), 2)

    def test_manifest_legacy_cwd_relative_paths(self):
        """Legacy manifest with CWD-relative paths resolves via fallback."""
        with tempfile.TemporaryDirectory() as root:
            set_safe_root(root)
            tensor_dir = os.path.join(root, "sub", "tensors")
            os.makedirs(tensor_dir)
            pt_file = os.path.join(tensor_dir, "sample.pt")
            open(pt_file, "wb").close()

            # Legacy manifest stored the full CWD-relative path
            legacy_rel = os.path.relpath(pt_file, root)
            manifest = {"samples": [legacy_rel]}
            with open(os.path.join(tensor_dir, "manifest.json"), "w") as f:
                json.dump(manifest, f)

            ds = PreprocessedTensorDataset(tensor_dir)
            self.assertEqual(len(ds.valid_paths), 1)
            self.assertEqual(
                os.path.realpath(ds.valid_paths[0]),
                os.path.realpath(pt_file),
            )


class SaveManifestTests(unittest.TestCase):
    """Tests for save_manifest path normalisation."""

    def test_paths_stored_relative_to_output_dir(self):
        """save_manifest converts absolute/CWD-relative paths to dir-relative."""
        from acestep.training.dataset_builder_modules.preprocess_manifest import (
            save_manifest,
        )
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as d:
            metadata = SimpleNamespace(to_dict=lambda: {"name": "test"})
            # Simulate paths that preprocess_to_tensors produces
            output_paths = [
                os.path.join(d, "a.pt"),
                os.path.join(d, "b.pt"),
            ]
            save_manifest(d, metadata, output_paths)
            with open(os.path.join(d, "manifest.json")) as f:
                manifest = json.load(f)
            # Paths should be just filenames (relative to d)
            self.assertEqual(manifest["samples"], ["a.pt", "b.pt"])
            self.assertEqual(manifest["num_samples"], 2)

    def test_cwd_relative_input_normalised(self):
        """CWD-relative input paths are normalised to dir-relative."""
        from acestep.training.dataset_builder_modules.preprocess_manifest import (
            save_manifest,
        )
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as d:
            metadata = SimpleNamespace(to_dict=lambda: {"name": "test"})
            # Paths like "./subdir/a.pt" relative to CWD
            cwd_rel = os.path.relpath(os.path.join(d, "x.pt"))
            save_manifest(d, metadata, [cwd_rel])
            with open(os.path.join(d, "manifest.json")) as f:
                manifest = json.load(f)
            self.assertEqual(manifest["samples"], ["x.pt"])


class LoadDatasetFromJsonTests(unittest.TestCase):
    """Tests for load_dataset_from_json path validation."""

    def setUp(self):
        set_safe_root(tempfile.gettempdir())

    def test_nonexistent_file_raises(self):
        with self.assertRaises(ValueError):
            load_dataset_from_json("/tmp/nonexistent_file.json")

    def test_valid_json(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"metadata": {"v": 1}, "samples": [{"a": 1}]}, f)
            path = f.name
        try:
            samples, meta = load_dataset_from_json(path)
            self.assertEqual(len(samples), 1)
            self.assertEqual(meta["v"], 1)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()

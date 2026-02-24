import json
import os
from typing import List


def save_manifest(output_dir: str, metadata, output_paths: List[str]) -> str:
    """Save manifest.json listing all preprocessed samples.

    Paths are stored **relative to output_dir** (typically just filenames)
    so that ``PreprocessedTensorDataset`` can resolve them correctly via
    ``safe_path(rel, base=tensor_dir)``.

    Args:
        output_dir: Directory where the manifest and .pt files live.
        metadata: Dataset metadata object with a ``to_dict`` method.
        output_paths: Absolute or CWD-relative paths to .pt files.

    Returns:
        Path to the written manifest.json.
    """
    abs_output_dir = os.path.abspath(output_dir)
    relative_paths = [
        os.path.relpath(os.path.abspath(p), abs_output_dir)
        for p in output_paths
    ]
    manifest = {
        "metadata": metadata.to_dict(),
        "samples": relative_paths,
        "num_samples": len(relative_paths),
    }
    manifest_path = os.path.join(output_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return manifest_path
